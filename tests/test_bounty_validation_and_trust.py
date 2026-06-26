import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from memanto.app.core import MemoryRecord, ValidationPolicy
from memanto.app.services.memory_write_service import MemoryWriteService
from memanto.app.services.memory_read_service import MemoryReadService


def test_core_to_moorcheh_document_uses_computed_confidence():
    """Verify that to_moorcheh_document uses compute_confidence() instead of raw self.confidence"""
    memory = MemoryRecord(
        type="preference",
        title="test-pref",
        content="I prefer light mode",
        scope_type="agent",
        scope_id="agent-abc",
        actor_id="user-123",
        source="user",
        confidence=0.9,
    )
    
    # Manually flag contradiction to trigger dynamic confidence adjustment
    memory.detect_contradiction()
    
    doc = memory.to_moorcheh_document()
    
    # Expected confidence should be the penalized computed confidence: 0.9 * 0.3 = 0.27
    assert doc["confidence"] == 0.27
    assert doc["confidence"] != 0.9


def test_write_service_enforces_validation_policy():
    """Verify write service properly uses ValidationPolicy and registers provisional storage"""
    client = MagicMock()
    client.documents.upload.return_value = {"status": "success"}
    
    write_service = MemoryWriteService(client)
    
    # Storing a critical memory (fact) with default/medium confidence without context
    memory = MemoryRecord(
        type="fact",
        title="test-fact",
        content="This is a test fact",
        scope_type="agent",
        scope_id="agent-abc",
        actor_id="user-123",
        source="user",
        confidence=0.8,
    )
    
    result = write_service.store_memory(memory)
    
    # It should have run validation, noticed it requires confirmation,
    # downgraded status to provisional, capped confidence to 0.5, and set TTL.
    assert result["action"] == "store_provisional"
    assert result["memory_status"] == "provisional"
    assert result["confidence"] == 0.5


def test_read_service_adds_computed_trust_metrics():
    """Verify read service formats document and appends computed_confidence and trust_score"""
    client = MagicMock()
    read_service = MemoryReadService(client)
    
    # Reconstructed item from Moorcheh
    item = {
        "id": "mem-123",
        "text": "[FACT] test-fact\n\nThis is a test fact",
        "metadata": {
            "memory_type": "fact",
            "scope_type": "agent",
            "scope_id": "agent-abc",
            "actor_id": "user-123",
            "source": "user",
            "confidence": 0.9,
            "status": "active",
            "provenance": "explicit_statement",
            "validation_count": 2,
            "contradiction_detected": False,
            "created_at": datetime.utcnow().isoformat(),
        }
    }
    
    formatted = read_service._format_memory_item(item)
    
    assert "computed_confidence" in formatted
    assert "trust_score" in formatted
    assert formatted["computed_confidence"] == 0.96  # 0.9 * 1.0 + 2 * 0.03
    assert formatted["trust_score"]["trust_level"] == "high"


def test_timezone_aware_created_at_does_not_raise_error():
    """Verify that timezone-aware created_at timestamps do not raise TypeError in compute_confidence or trust_score"""
    memory = MemoryRecord(
        type="preference",
        title="test-pref",
        content="I prefer dark mode",
        scope_type="agent",
        scope_id="agent-abc",
        actor_id="user-123",
        source="user",
        confidence=0.9,
        created_at=datetime.fromisoformat("2026-06-26T12:00:00+00:00")
    )
    
    # Should not raise TypeError: can't subtract offset-naive and offset-aware datetimes
    assert memory.compute_confidence() == 0.9
    assert memory.trust_score()["age_days"] >= 0

