"""
ResolveAI V2 — Response Validation & Safety Hard Gate Tests
===========================================================
Consolidates:
  1. ValidationService unit checks:
     - Structural JSON leak validation
     - Security order leak validation
     - Tool truthfulness validation
     - Action truthfulness validation
     - Semantic grounding validation
     - Valid response validation
  2. Safety Hard Gate integration with ConversationService:
     - Valid response allows TTS streaming
     - Invalid/escalated response blocks TTS streaming
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from app.ai.validation.models import (
    ResponseValidationContext,
    ValidationResult,
    ValidationStatus,
    ValidationViolation,
    ToolResultContext,
)
from app.ai.validation.service import ValidationService
from app.conversations.service import ConversationService
from app.voice.streaming_providers import MockStreamingTTSProvider
from app.conversations.models import Conversation
from app.shared.models import ConversationStatus, WorkflowState


# ============================================================================
# Section 1: ValidationService Core Rule Checks
# ============================================================================

@pytest.mark.asyncio
async def test_structural_validation():
    ctx = ResponseValidationContext(
        conversation_id=1, customer_id=1, user_message="hello",
        draft_response="{\n\"decision\": \"RESOLVE\",\n\"reason\": \"test\"\n}"
    )
    result = await ValidationService.validate_response(ctx)
    assert result.status == ValidationStatus.REGENERATE
    assert any("JSON" in v.violation_type for v in result.violations)


@pytest.mark.asyncio
async def test_security_leak():
    ctx = ResponseValidationContext(
        conversation_id=1, customer_id=1, user_message="status",
        draft_response="Here is the status for ORD-777",
        authorized_order_ids=["ORD-123"]
    )
    result = await ValidationService.validate_response(ctx)
    assert result.status == ValidationStatus.ESCALATE
    assert result.violations[0].check_name == "SECURITY"


@pytest.mark.asyncio
async def test_tool_truthfulness():
    tr = ToolResultContext(tool_name="cancel_order", success=False, error_code="NOT_FOUND")
    ctx = ResponseValidationContext(
        conversation_id=1, customer_id=1, user_message="cancel",
        draft_response="Your order was cancelled successfully.",
        tool_results=[tr]
    )
    result = await ValidationService.validate_response(ctx)
    assert result.status == ValidationStatus.REGENERATE
    assert result.violations[0].check_name == "TOOL_TRUTHFULNESS"


@pytest.mark.asyncio
async def test_action_truthfulness():
    ctx = ResponseValidationContext(
        conversation_id=1, customer_id=1, user_message="refund",
        draft_response="I have issued a refund to your card.",
        tool_results=[]
    )
    result = await ValidationService.validate_response(ctx)
    assert result.status == ValidationStatus.REGENERATE
    assert result.violations[0].check_name == "ACTION_TRUTHFULNESS"


@pytest.mark.asyncio
async def test_semantic_grounding_timeout_or_fail():
    ctx = ResponseValidationContext(
        conversation_id=1, customer_id=1, user_message="policy",
        draft_response="We offer 90-day returns. FAIL_SEMANTIC_GROUNDING",
        rag_context=[{"content": "We offer 30-day returns."}]
    )
    result = await ValidationService.validate_response(ctx)
    assert result.status == ValidationStatus.REGENERATE
    assert result.violations[0].check_name == "GROUNDING"


@pytest.mark.asyncio
async def test_valid_response():
    ctx = ResponseValidationContext(
        conversation_id=1, customer_id=1, user_message="hi",
        draft_response="Hello! How can I help you today?",
        detected_intent="GREETING"
    )
    result = await ValidationService.validate_response(ctx)
    assert result.status == ValidationStatus.VALID


# ============================================================================
# Section 2: Safety Hard Gate Integration with TTS & Handoff
# ============================================================================

@pytest.mark.asyncio
async def test_valid_response_invokes_tts():
    MockStreamingTTSProvider.reset()
    
    svc = ConversationService()
    
    db = AsyncMock()
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_result.scalars.return_value = mock_scalars
    db.execute.return_value = mock_result
    
    convo = Conversation(id=1, customer_id=1, status=ConversationStatus.ACTIVE, workflow_state=WorkflowState.IDLE)
    
    spoken_phrases = []
    
    async def mock_tts_callback(text):
        spoken_phrases.append(text)
        
    with patch("app.ai.validation.service.ValidationService.validate_response") as mock_validate:
        with patch("app.conversations.service.MessageService.create_message"):
            with patch("app.websockets.manager.manager.send_to_conversation_participants"):
                mock_validate.return_value = ValidationResult(status=ValidationStatus.VALID)
                
                svc.ai_provider = AsyncMock()
                if hasattr(svc.ai_provider, "process_voice_turn"):
                    del svc.ai_provider.process_voice_turn
                svc.ai_provider.analyze = AsyncMock(return_value={"intent": "TEST", "decision_state": "RESOLVE", "entities": {}})
                svc.ai_provider.generate_response = AsyncMock(return_value="This is a valid response")
                
                await svc._trigger_ai_response(
                    db=db, 
                    conversation=convo, 
                    latest_message="Hello", 
                    tts_callback=mock_tts_callback
                )
                
                await asyncio.sleep(0.01)
                assert any("valid response" in t.lower() for t in spoken_phrases)


@pytest.mark.asyncio
async def test_invalid_response_never_invokes_tts():
    MockStreamingTTSProvider.reset()
    
    svc = ConversationService()
    db = AsyncMock()
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_result.scalars.return_value = mock_scalars
    db.execute.return_value = mock_result
    
    convo = Conversation(id=1, customer_id=1, status=ConversationStatus.ACTIVE, workflow_state=WorkflowState.IDLE)
    
    spoken_phrases = []
    
    async def mock_tts_callback(text):
        spoken_phrases.append(text)
        
    with patch("app.ai.validation.service.ValidationService.validate_response") as mock_validate:
        with patch("app.conversations.service.MessageService.create_message"):
            with patch("app.websockets.manager.manager.send_to_conversation_participants"):
                with patch("app.conversations.service.select"):
                    mock_validate.return_value = ValidationResult(
                        status=ValidationStatus.ESCALATE,
                        violations=[ValidationViolation(check_name="SECURITY", violation_type="LEAK", reason="Bad")]
                    )
                    
                    svc.ai_provider = AsyncMock()
                    if hasattr(svc.ai_provider, "process_voice_turn"):
                        del svc.ai_provider.process_voice_turn
                    svc.ai_provider.analyze = AsyncMock(return_value={"intent": "TEST", "decision_state": "RESOLVE", "entities": {}})
                    svc.ai_provider.generate_response = AsyncMock(return_value="This is a bad response")
                    
                    await svc._trigger_ai_response(
                        db=db, 
                        conversation=convo, 
                        latest_message="Hello", 
                        tts_callback=mock_tts_callback
                    )
                    
                    await asyncio.sleep(0.01)
                    assert not any("bad response" in t.lower() for t in spoken_phrases)
