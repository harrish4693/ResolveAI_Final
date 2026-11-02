"""
ResolveAI V2 — LLM Providers & Core AI Decisions Test Suite
===========================================================
Consolidates:
  1. OpenAI Provider analysis, structured generation, error handling & fallbacks
  2. Gemini Provider structured output, transient error retries, and auth failure
  3. AI routing, human takeover stops, and safety override behavior
  4. Core Deterministic Decision Engine intent-to-action routing
"""
import pytest
import json
from unittest.mock import patch, AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from openai import AuthenticationError, APITimeoutError
from google.genai.errors import APIError, ClientError

from app.ai.openai_provider import OpenAIProvider, AnalysisSchema as OpenAIAnalysisSchema, DecisionSchema as OpenAIDecisionSchema
from app.ai.gemini_provider import GeminiProvider
from app.ai.schemas import AnalysisSchema as GeminiAnalysisSchema, DecisionSchema as GeminiDecisionSchema
from app.ai.m4.analysis import IntentClassifier
from app.ai.m4.decision import DecisionEngine
from app.conversations.models import Conversation
from app.shared.models import WorkflowState


# ============================================================================
# Section 1: OpenAI Provider Tests
# ============================================================================

@pytest.fixture
def openai_provider():
    provider = OpenAIProvider()
    provider.api_key = "test_key"
    return provider


@pytest.mark.asyncio
async def test_openai_generate_response_fallback_on_failure():
    provider = OpenAIProvider()
    provider.client = AsyncMock()
    analysis = {"intent": "GENERAL_QUERY", "entities": {}}
    context = {"history": []}
    
    with patch("app.ai.openai_provider.OpenAIProvider.generate_structured", new_callable=AsyncMock) as mock_parse:
        mock_parse.side_effect = APITimeoutError(request=None)
        
        response = await provider.generate_response(analysis, [], context)
        
        assert response == "I'm currently experiencing technical difficulties. I will escalate your issue to a human expert."
        assert analysis.get("decision_state") == "ESCALATE"


@pytest.mark.asyncio
async def test_openai_analyze_fallback_on_failure():
    provider = OpenAIProvider()
    provider.client = AsyncMock()
    
    with patch("app.ai.openai_provider.OpenAIProvider.generate_structured", new_callable=AsyncMock) as mock_parse:
        mock_parse.side_effect = APITimeoutError(request=None)
        
        analysis = await provider.analyze("Hello", {})
        
        assert analysis["intent"] == "GENERAL_QUERY"
        assert analysis["language"] == "English"
        assert analysis["priority"] == "MEDIUM"
        assert analysis["sentiment"] == "neutral"


@pytest.mark.asyncio
async def test_openai_generate_response_auth_error_fails_fast():
    provider = OpenAIProvider()
    provider.client = AsyncMock()
    analysis = {"intent": "GENERAL_QUERY", "entities": {}}
    context = {"history": []}
    
    with patch("app.ai.openai_provider.OpenAIProvider.generate_structured", new_callable=AsyncMock) as mock_parse:
        import httpx
        mock_response = httpx.Response(status_code=401, request=httpx.Request("POST", "url"))
        mock_parse.side_effect = AuthenticationError("Auth missing", response=mock_response, body=None)
        
        with pytest.raises(AuthenticationError):
            await provider.generate_response(analysis, [], context)


@pytest.mark.asyncio
async def test_openai_analyze_success(openai_provider):
    mock_response = OpenAIAnalysisSchema(
        intent="PAYMENT_ISSUE",
        sentiment="negative",
        priority="HIGH",
        language="English",
        entities={"transaction_id": "TXN123"}
    )
    
    with patch("app.ai.openai_provider.OpenAIProvider.generate_structured", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = mock_response
        
        result = await openai_provider.analyze("My payment failed for TXN123", {"history": []})
        
        assert result["intent"] == "PAYMENT_ISSUE"
        assert result["entities"]["transaction_id"] == "TXN123"


@pytest.mark.asyncio
async def test_openai_analyze_malformed_json_fallback(openai_provider):
    with patch("app.ai.openai_provider.OpenAIProvider.generate_structured", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = Exception("API error")
        
        result = await openai_provider.analyze("Hi", {"history": []})
        
        assert result["intent"] == "GENERAL_QUERY"
        assert result["priority"] == "MEDIUM"


@pytest.mark.asyncio
async def test_openai_generate_response_success(openai_provider):
    mock_response = OpenAIDecisionSchema(
        decision="USE_TOOL",
        response_text="I can check that for you.",
        tool_name="check_transaction",
        tool_args={"transaction_id": "TXN123"},
        reason="Checking status",
        confidence=0.95
    )
    
    with patch("app.ai.openai_provider.OpenAIProvider.generate_structured", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = mock_response
        
        analysis = {"intent": "PAYMENT_ISSUE", "entities": {"transaction_id": "TXN123"}}
        response_text = await openai_provider.generate_response(analysis, [], {"history": []})
        
        assert response_text == "I can check that for you." or "One moment" in response_text
        assert analysis["decision_state"] == "USE_TOOL"
        assert analysis["tool_name"] == "check_transaction"
        assert analysis["tool_args"]["transaction_id"] == "TXN123"


@pytest.mark.asyncio
async def test_openai_generate_response_failure_escalates(openai_provider):
    with patch("app.ai.openai_provider.OpenAIProvider.generate_structured", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = Exception("OpenAI API Down")
        
        analysis = {"intent": "PAYMENT_ISSUE", "entities": {}}
        response_text = await openai_provider.generate_response(analysis, [], {"history": []})
        
        assert "technical difficulties" in response_text
        assert analysis["decision_state"] == "ESCALATE"


@pytest.mark.asyncio
async def test_ai_stops_after_human_takeover(db_session, test_user_a):
    from app.conversations.router import add_message
    from app.conversations.schemas import ConversationMessageCreate
    
    convo = Conversation(customer_id=test_user_a.id, workflow_state=WorkflowState.WAITING_FOR_EXPERT)
    db_session.add(convo)
    await db_session.commit()
    
    msg_data = ConversationMessageCreate(content="Hello human")
    
    with patch("app.conversations.router.conversation_service.process_customer_message", new_callable=AsyncMock) as mock_process:
        await add_message(convo.id, msg_data, current_user=test_user_a, db=db_session)
        mock_process.assert_not_called()


# ============================================================================
# Section 2: Gemini Provider Tests
# ============================================================================

@pytest.fixture
def mock_gemini_settings(monkeypatch):
    monkeypatch.setattr("app.ai.gemini_provider.settings.gemini_api_key", "test_key")
    monkeypatch.setattr("app.ai.gemini_provider.settings.gemini_model", "gemini-2.5-flash")


@pytest.mark.asyncio
async def test_gemini_generate_structured_success(mock_gemini_settings):
    provider = GeminiProvider()
    
    mock_client = MagicMock()
    mock_aio = AsyncMock()
    mock_models = AsyncMock()
    
    mock_response = MagicMock()
    mock_response.text = '```json\n{"intent": "PAYMENT_ISSUE", "sentiment": "negative", "priority": "HIGH", "language": "en", "entities": {}}\n```'
    
    mock_models.generate_content.return_value = mock_response
    mock_aio.models = mock_models
    mock_client.aio = mock_aio
    provider.client = mock_client
    
    messages = [{"role": "user", "content": "My payment failed!"}]
    result = await provider.generate_structured(messages, GeminiAnalysisSchema)
    
    assert isinstance(result, GeminiAnalysisSchema)
    assert result.intent == "PAYMENT_ISSUE"
    assert result.sentiment == "negative"


@pytest.mark.asyncio
async def test_gemini_generate_structured_retries_api_error(mock_gemini_settings):
    provider = GeminiProvider()
    
    mock_client = MagicMock()
    mock_aio = AsyncMock()
    mock_models = AsyncMock()
    
    mock_response = MagicMock()
    mock_response.text = '{"intent": "GENERAL_QUERY", "sentiment": "neutral", "priority": "LOW", "language": "en", "entities": {}}'
    
    mock_models.generate_content.side_effect = [
        APIError(code=500, response_json={"message": "Transient error 1"}),
        APIError(code=500, response_json={"message": "Transient error 2"}),
        mock_response
    ]
    
    mock_aio.models = mock_models
    mock_client.aio = mock_aio
    provider.client = mock_client
    
    messages = [{"role": "user", "content": "Hi"}]
    provider.generate_structured.retry.wait.wait_fixed = 0.01 
    
    result = await provider.generate_structured(messages, GeminiAnalysisSchema)
    assert isinstance(result, GeminiAnalysisSchema)
    assert mock_models.generate_content.call_count == 3


@pytest.mark.asyncio
async def test_gemini_auth_error_no_retry(mock_gemini_settings):
    provider = GeminiProvider()
    
    mock_client = MagicMock()
    mock_aio = AsyncMock()
    mock_models = AsyncMock()
    
    mock_models.generate_content.side_effect = ClientError(code=401, response_json={"message": "401 Unauthorized"})
    
    mock_aio.models = mock_models
    mock_client.aio = mock_aio
    provider.client = mock_client
    
    messages = [{"role": "user", "content": "Hi"}]
    
    with pytest.raises(ClientError):
        await provider.generate_structured(messages, GeminiAnalysisSchema)
        
    assert mock_models.generate_content.call_count == 1


@pytest.mark.asyncio
async def test_gemini_analyze_fallback(mock_gemini_settings):
    provider = GeminiProvider()
    
    mock_client = MagicMock()
    mock_aio = AsyncMock()
    mock_models = AsyncMock()
    
    mock_response = MagicMock()
    mock_response.text = 'invalid json'
    mock_models.generate_content.return_value = mock_response
    
    mock_aio.models = mock_models
    mock_client.aio = mock_aio
    provider.client = mock_client
    
    provider.generate_structured.retry.wait.wait_fixed = 0.01
    
    result = await provider.analyze("My payment failed", {})
    assert result["intent"] == "GENERAL_QUERY"
    assert result["language"] == "en"


@pytest.mark.asyncio
async def test_gemini_generate_response_escalation(mock_gemini_settings):
    provider = GeminiProvider()
    mock_client = MagicMock()
    mock_aio = AsyncMock()
    mock_models = AsyncMock()
    
    mock_response = MagicMock()
    mock_response.text = '{"decision": "RESOLVE", "response_text": "I fixed it", "tool_name": null, "tool_args": {}, "reason": "test", "confidence": 0.9}'
    mock_models.generate_content.return_value = mock_response
    
    mock_aio.models = mock_models
    mock_client.aio = mock_aio
    provider.client = mock_client
    
    analysis = {"intent": "SECURITY_ISSUE"}
    response = await provider.generate_response(analysis, [], {})
    
    assert response == "I fixed it"
    assert analysis["decision_state"] == "ESCALATE"


@pytest.mark.asyncio
async def test_gemini_normal_payment_issue_not_escalate(mock_gemini_settings):
    provider = GeminiProvider()
    mock_client = MagicMock()
    mock_aio = AsyncMock()
    mock_models = AsyncMock()
    
    mock_response = MagicMock()
    mock_response.text = '```json\n{"decision": "RESOLVE", "response_text": "I can help you with your payment.", "tool_name": null, "tool_args": {}, "reason": "Test", "confidence": 0.9}\n```'
    mock_models.generate_content.return_value = mock_response
    mock_aio.models = mock_models
    mock_client.aio = mock_aio
    provider.client = mock_client
    
    analysis = {"intent": "PAYMENT_ISSUE"}
    response = await provider.generate_response(analysis, [], {})
    assert analysis["decision_state"] == "RESOLVE"
    assert response == "I can help you with your payment."


@pytest.mark.asyncio
async def test_gemini_normal_delivery_query_not_escalate(mock_gemini_settings):
    provider = GeminiProvider()
    mock_client = MagicMock()
    mock_aio = AsyncMock()
    mock_models = AsyncMock()
    
    mock_response = MagicMock()
    mock_response.text = '```json\n{"decision": "RESOLVE", "response_text": "Your order is on the way.", "tool_name": null, "tool_args": {}, "reason": "Test", "confidence": 0.9}\n```'
    mock_models.generate_content.return_value = mock_response
    mock_aio.models = mock_models
    mock_client.aio = mock_aio
    provider.client = mock_client
    
    analysis = {"intent": "DELIVERY_ISSUE"}
    response = await provider.generate_response(analysis, [], {})
    assert analysis["decision_state"] == "RESOLVE"
    assert response == "Your order is on the way."


@pytest.mark.asyncio
async def test_gemini_high_risk_issue_escalates(mock_gemini_settings):
    provider = GeminiProvider()
    mock_client = MagicMock()
    mock_aio = AsyncMock()
    mock_models = AsyncMock()
    
    mock_response = MagicMock()
    mock_response.text = '{"decision": "RESOLVE", "response_text": "Let me fix your hacked account.", "tool_name": null, "tool_args": {}, "reason": "Test", "confidence": 0.9}'
    mock_models.generate_content.return_value = mock_response
    mock_aio.models = mock_models
    mock_client.aio = mock_aio
    provider.client = mock_client
    
    analysis = {"intent": "SECURITY_ISSUE"}
    response = await provider.generate_response(analysis, [], {})
    assert analysis["decision_state"] == "ESCALATE"


@pytest.mark.asyncio
async def test_gemini_missing_information_ask_user(mock_gemini_settings):
    provider = GeminiProvider()
    mock_client = MagicMock()
    mock_aio = AsyncMock()
    mock_models = AsyncMock()
    
    mock_response = MagicMock()
    mock_response.text = '```json\n{"decision": "ASK_USER", "response_text": "Please provide your order ID.", "tool_name": null, "tool_args": {}, "reason": "Missing order ID", "confidence": 0.9}\n```'
    mock_models.generate_content.return_value = mock_response
    mock_aio.models = mock_models
    mock_client.aio = mock_aio
    provider.client = mock_client
    
    analysis = {"intent": "GENERAL_QUERY"}
    response = await provider.generate_response(analysis, [], {})
    assert analysis["decision_state"] == "ASK_USER"
    assert response == "Please provide your order ID."


# ============================================================================
# Section 3: Deterministic AI Decisions (M4 Decisions Without RAG)
# ============================================================================

def test_greeting_no_rag():
    classifier = IntentClassifier()
    decision_engine = DecisionEngine()
    
    intent = classifier.classify("Hi")
    assert intent == "GREETING"
    
    analysis = {"intent": intent, "entities": {}}
    decision = decision_engine.decide(analysis, [])
    assert decision["decision"] == "ASK_USER"
    assert decision["missing_entity"] == "greeting"


def test_hello_can_you_help_me_no_rag():
    classifier = IntentClassifier()
    decision_engine = DecisionEngine()
    
    intent = classifier.classify("Hello, can you help me?")
    assert intent == "GREETING"
    
    analysis = {"intent": intent, "entities": {}}
    decision = decision_engine.decide(analysis, [])
    assert decision["decision"] == "ASK_USER"
    assert decision["missing_entity"] == "greeting"


def test_my_payment_failed_no_rag():
    classifier = IntentClassifier()
    decision_engine = DecisionEngine()
    
    intent = classifier.classify("My payment failed")
    assert intent == "PAYMENT_ISSUE"
    
    analysis = {"intent": intent, "entities": {}}
    decision = decision_engine.decide(analysis, [])
    assert decision["decision"] == "ASK_USER"
    assert decision["missing_entity"] == "transaction_id"


def test_refund_issue_no_rag():
    classifier = IntentClassifier()
    decision_engine = DecisionEngine()
    
    intent = classifier.classify("I want a refund")
    assert intent == "REFUND_ISSUE"
    
    analysis = {"intent": intent, "entities": {}}
    decision = decision_engine.decide(analysis, [])
    assert decision["decision"] == "ESCALATE"


def test_unknown_intent_no_rag():
    decision_engine = DecisionEngine()
    analysis = {"intent": "SOME_UNKNOWN_INTENT", "entities": {}}
    decision = decision_engine.decide(analysis, [])
    assert decision["decision"] == "ESCALATE"
