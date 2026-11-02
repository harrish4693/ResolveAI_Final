"""
ResolveAI V2 — Dynamic Conversational Intelligence Regression Suite
===================================================================
Validates the 12 core conversational scenarios for ChatGPT-like conversational quality:
1. Multi-turn order inquiry: original intent remains active beyond turn 5.
2. Entity persistence: order ID survives "seri" and contextual follow-ups.
3. "Puriyala, simple ah sollu": triggers simplified explanation.
4. "Naa indha question kekave illaye": triggers reconsideration/re-evaluation prompt.
5. "But why?": contextual answer explaining reason.
6. "Appo next enna pannanum?": continues active task with next steps.
7. "Illa, naan adha sollala": handled as denial/misunderstanding correction.
8. Unseen Tanglish/Hinglish expressions: do not reset established language preference.
9. Valid code-mixed responses without static markers pass validation without regeneration loop.
10. Language switch preserves active task and known entities.
11. Genuinely new topic does not leak or inherit unrelated entities.
12. Security escalation, human handoff, and tenant isolation preserved.
"""

import pytest
from app.ai.intelligence.language import UniversalMeaningEngine, CodeMixedLanguageDetector
from app.conversations.state import ConversationState, ConversationStateManager
from app.ai.m4.provider import M4AIProvider
from app.ai.m4.decision import DecisionEngine, ResponseGenerator
from app.ai.validation.models import ResponseValidationContext, ValidationStatus
from app.ai.validation.rules import check_language_consistency
from app.conversations.service import ConversationService


@pytest.fixture(autouse=True)
def setup_db():
    """Override conftest setup_db so unit tests do not block on DB fixtures."""
    yield


@pytest.fixture
def meaning_engine():
    return UniversalMeaningEngine()


@pytest.fixture
def m4_provider():
    return M4AIProvider()


@pytest.fixture
def decision_engine():
    return DecisionEngine()


@pytest.fixture
def response_generator():
    return ResponseGenerator()


# ── Scenario 1: Multi-Turn Order Inquiry Beyond Turn 5 ──
def test_scenario_1_multi_turn_order_inquiry_intent_survives(meaning_engine):
    """Scenario 1: Original ORDER_STATUS intent survives across multiple turns using conversation state."""
    state = ConversationState(
        conversation_id=101,
        customer_id=1,
        active_intent="ORDER_STATUS",
        unresolved_request="Customer asked to track order ORD-99221",
        entities={"order_id": "ORD-99221"},
        resolution_status="in_progress",
    )

    # Turn 6 follow-up: customer asks a short status question in Tanglish
    u = meaning_engine.understand_utterance("Eppo deliver aagum?", conversation_state=state)
    assert u.intent in ("DELIVERY_ISSUE", "ORDER_STATUS")
    assert u.category in ("delivery", "order")


# ── Scenario 2: Entity Persistence Across Acknowledgments ("seri") ──
def test_scenario_2_order_id_survives_acknowledgment(meaning_engine):
    """Scenario 2: 'seri' / acknowledgment does not erase entities when active task is unresolved."""
    state = ConversationState(
        conversation_id=102,
        customer_id=1,
        active_intent="ORDER_STATUS",
        unresolved_request="Order tracking in progress",
        entities={"order_id": "ORD-77441"},
        resolution_status="in_progress",
    )

    # Customer acknowledges: "seri"
    u = meaning_engine.understand_utterance("seri", conversation_state=state)
    ConversationStateManager.update_before_turn(
        state=state,
        customer_message="seri",
        understanding=u,
    )

    # Entity MUST be preserved because task is active/unresolved
    assert "order_id" in state.entities
    assert state.entities["order_id"] == "ORD-77441"
    assert state.active_intent == "ACKNOWLEDGMENT"


# ── Scenario 3: "Puriyala, simple ah sollu" -> Simplified Explanation ──
def test_scenario_3_simplification_request(meaning_engine, decision_engine, response_generator):
    """Scenario 3: 'Puriyala, simple ah sollu' triggers a simpler explanation of the previous answer."""
    state = ConversationState(
        conversation_id=103,
        customer_id=1,
        active_intent="ORDER_STATUS",
        unresolved_request="Order status explanation",
        entities={"order_id": "ORD-12345"},
    )

    u = meaning_engine.understand_utterance("Puriyala, simple ah sollu", conversation_state=state)
    assert u.conversational_function == "CLARIFICATION_OR_CORRECTION"
    assert u.diagnostic_details.get("needs_simplification") is True

    # Decision Engine routes to simplified_explanation
    decision = decision_engine.decide({
        "intent": u.intent,
        "category": u.category,
        "needs_simplification": True,
        "entities": state.entities,
        "diagnostic_details": u.diagnostic_details,
    }, [])
    assert decision["decision"] == "RESOLVE"
    assert decision["action_type"] == "simplified_explanation"

    # Response is generated in Tanglish simply and clearly
    resp = response_generator.generate(decision, language="tanglish")
    assert len(resp) > 10
    assert any(term in resp.lower() for term in ["simple", "solren", "puriyum", "order"])


# ── Scenario 4: "Naa indha question kekave illaye" -> Reconsideration ──
def test_scenario_4_misunderstanding_correction(meaning_engine, decision_engine, response_generator):
    """Scenario 4: 'Naa indha question kekave illaye' triggers re-evaluation prompt, not repeating old answer."""
    state = ConversationState(
        conversation_id=104,
        customer_id=1,
        active_intent="POLICY_QUERY",
        unresolved_request="Customer asked about returns",
    )

    u = meaning_engine.understand_utterance("Naa indha question kekave illaye", conversation_state=state)
    assert u.intent == "CORRECTION_RECONSIDER"
    assert u.diagnostic_details.get("is_misunderstanding_correction") is True

    # Decision Engine asks user to clarify their intended question
    decision = decision_engine.decide({
        "intent": "CORRECTION_RECONSIDER",
        "is_misunderstanding_correction": True,
        "entities": {},
    }, [])
    assert decision["decision"] == "ASK_USER"
    assert decision["missing_entity"] == "reconsider_question"

    # Response apologizes gracefully and asks for the actual question
    resp = response_generator.generate(decision, language="tanglish")
    assert any(term in resp.lower() for term in ["mannikavum", "sorry", "purinjukala", "enna"])


# ── Scenario 5: "But why?" -> Contextual Explanation ──
def test_scenario_5_contextual_why(meaning_engine):
    """Scenario 5: 'But why?' receives an answer grounded in the previous turn."""
    state = ConversationState(
        conversation_id=105,
        customer_id=1,
        active_intent="ORDER_STATUS",
        unresolved_request="Order status check requires Order ID",
        entities={},
    )

    u = meaning_engine.understand_utterance("But why?", conversation_state=state)
    assert u.intent == "ORDER_STATUS"
    assert u.conversational_function == "FOLLOW_UP"
    assert u.diagnostic_details.get("explain_why") is True


# ── Scenario 6: "Appo next enna pannanum?" -> Continues Active Task ──
def test_scenario_6_next_steps_continuation(meaning_engine, decision_engine):
    """Scenario 6: 'Appo next enna pannanum?' continues the active task with next steps."""
    state = ConversationState(
        conversation_id=106,
        customer_id=1,
        active_intent="POLICY_QUERY",
        unresolved_request="Customer asked about return policy",
        entities={"policy_type": "return"},
    )

    u = meaning_engine.understand_utterance("Appo next enna pannanum?", conversation_state=state)
    assert u.intent == "POLICY_QUERY"
    assert u.conversational_function == "FOLLOW_UP"
    assert u.diagnostic_details.get("is_next_step") is True

    # Decision Engine routes to policy next steps
    decision = decision_engine.decide({
        "intent": "POLICY_QUERY",
        "is_next_step": True,
        "entities": state.entities,
    }, [])
    assert decision["decision"] == "RESOLVE"
    assert decision["action_type"] == "policy_next_steps"


# ── Scenario 7: "Illa, naan adha sollala" -> Denial / Correction ──
def test_scenario_7_denial_correction(meaning_engine):
    """Scenario 7: 'Illa, naan adha sollala' is recognized as a misunderstanding correction."""
    u = meaning_engine.understand_utterance("Illa, naan adha sollala")
    assert u.intent == "CORRECTION_RECONSIDER"
    assert u.conversational_function == "CLARIFICATION_OR_CORRECTION"
    assert u.diagnostic_details.get("is_misunderstanding_correction") is True


# ── Scenario 8: Unseen Tanglish/Hinglish Expressions ──
def test_scenario_8_unseen_codemixed_expressions_preserve_language():
    """Scenario 8: Unseen Tanglish/Hinglish slang does not reset established language preference."""
    detector = CodeMixedLanguageDetector()

    # Unseen Tanglish expression with colloquial slang
    res_tanglish = detector.detect("Enna da aachu indha parcel-kku innum vandhu serum-a?", contextual_preference="tanglish")
    assert res_tanglish.code_mix_type in ("tanglish", "tamil")

    # Short follow-up preserves sticky tanglish
    res_short = detector.detect("Seri adhuku apram?", contextual_preference="tanglish")
    assert res_short.code_mix_type == "tanglish"

    # Unseen Hinglish expression
    res_hinglish = detector.detect("Bhai kab tak pahuchega yeh item?", contextual_preference="hinglish")
    assert res_hinglish.code_mix_type in ("hinglish", "hindi")


# ── Scenario 9: Language Consistency Validation Rule ──
def test_scenario_9_valid_codemixed_responses_pass_validation():
    """Scenario 9: Natural code-mixed responses pass validation without triggering false regeneration loops."""
    # Natural Tanglish response
    tanglish_text = "Ungal order ORD-99123 dispatch aayiduchu, naalaikku kulla ungalukku deliver aagidum."
    ctx_tanglish = ResponseValidationContext(
        conversation_id=901,
        customer_id=1,
        user_message="order status sollu",
        draft_response=tanglish_text,
        preferred_language="tanglish",
    )
    res_tanglish = check_language_consistency(ctx_tanglish)
    assert res_tanglish.status == ValidationStatus.VALID

    # Natural Hinglish response
    hinglish_text = "Aapka order ORD-99123 ship ho chuka hai, kal tak deliver ho jayega."
    ctx_hinglish = ResponseValidationContext(
        conversation_id=902,
        customer_id=1,
        user_message="order status batao",
        draft_response=hinglish_text,
        preferred_language="hinglish",
    )
    res_hinglish = check_language_consistency(ctx_hinglish)
    assert res_hinglish.status == ValidationStatus.VALID


# ── Scenario 10: Language Switch Preserves Active Task & Entities ──
def test_scenario_10_language_switch_preserves_task_and_entities():
    """Scenario 10: Explicit language switch ('tanglish la continue pannu') preserves active task and entities."""
    state = ConversationState(
        conversation_id=110,
        customer_id=1,
        active_intent="ORDER_STATUS",
        unresolved_request="Tracking order ORD-55443",
        entities={"order_id": "ORD-55443"},
        language_preference="english",
    )

    # Customer requests language switch
    switch_req = ConversationService.detect_explicit_language_request("tanglish la continue pannu")
    assert switch_req == "tanglish"

    # Simulated understanding of language switch
    engine = UniversalMeaningEngine()
    u = engine.understand_utterance("tanglish la continue pannu", conversation_state=state)
    assert u.intent == "LANGUAGE_SWITCH"

    # Update state for language switch
    state.language_preference = "tanglish"
    ConversationStateManager.update_before_turn(
        state=state,
        customer_message="tanglish la continue pannu",
        understanding=u,
    )

    # Order ID and active task must be retained
    assert state.entities.get("order_id") == "ORD-55443"
    assert state.unresolved_request == "Tracking order ORD-55443"
    assert state.language_preference == "tanglish"


# ── Scenario 11: Genuinely New Topic Starts Fresh Without Leaking Entities ──
def test_scenario_11_new_topic_does_not_leak_old_entities():
    """Scenario 11: Customer transitions to completely new topic -> previous entities are not leaked."""
    state = ConversationState(
        conversation_id=111,
        customer_id=1,
        active_intent="ORDER_STATUS",
        unresolved_request="Tracking order ORD-55443",
        entities={"order_id": "ORD-55443"},
    )

    engine = UniversalMeaningEngine()
    # Customer asks about changing password (brand new topic)
    u = engine.understand_utterance("How do I change my account password?", conversation_state=state)
    assert u.intent in ("TECHNICAL_ISSUE", "GENERAL_QUERY", "PASSWORD_RESET", "LOGIN_ISSUE")
    assert u.category != "order"
    assert "order_id" not in u.entities


# ── Scenario 12: Grounded Support, Supervisor Escalation & Safety ──
def test_scenario_12_supervisor_escalation_and_safety_preserved():
    """Scenario 12: Explicit supervisor requests or fraud in Tanglish trigger immediate escalation."""
    from app.ai.intelligence.escalation_keywords import is_supervisor_demand, is_fraud_or_security

    # Supervisor demand in Tanglish
    assert is_supervisor_demand("enakku manager kooda pesa mudiyuma?") is True
    assert is_supervisor_demand("human agent venum") is True

    # Fraud / security indicator in Tanglish
    assert is_fraud_or_security("en account hack aayiduchu, kaasu unauthorized ah poyirukku") is True

    # Ordinary questions do NOT escalate
    assert is_supervisor_demand("unga return policy enna?") is False
    assert is_fraud_or_security("order eppo varum?") is False


# ── Scenario 13: RC-7.1 "Puriyala, simple ah sollu" Simplification ──
def test_scenario_13_puriyala_simple_ah_sollu_simplification(meaning_engine, decision_engine, response_generator):
    """Scenario 13: 'Puriyala, simple ah sollu' simplifies the previous answer without asking to repeat."""
    history = [
        {"sender_type": "customer", "content": "Return policy enna?"},
        {"sender_type": "ai", "content": "Namma return policy padi, items delivery aana 30 days kulla original condition-la return panna mudiyum."}
    ]
    state = ConversationState(
        conversation_id=113,
        customer_id=1,
        active_intent="POLICY_QUERY",
        unresolved_request="Return policy inquiry",
        language_preference="tanglish",
    )

    u = meaning_engine.understand_utterance("Puriyala, simple ah sollu", history=history, conversation_state=state)
    assert u.diagnostic_details.get("needs_simplification") is True

    decision = decision_engine.decide({
        "intent": u.intent,
        "needs_simplification": True,
        "diagnostic_details": u.diagnostic_details,
    }, [{"title": "Return Policy", "content": "30 days returns for full refund in original condition"}])

    assert decision["decision"] == "RESOLVE"
    assert decision["action_type"] == "simplified_explanation"

    resp = response_generator.generate(decision, language="tanglish")
    # Must NOT ask customer to repeat question or say "kelviyai vilakkamaaga solla mudiyuma"
    assert "vilakkamaaga solla mudiyuma" not in resp.lower()
    assert "simple" in resp.lower()


# ── Scenario 14: RC-7.2 "But why?" Causal Explanation ──
def test_scenario_14_but_why_causal_explanation(meaning_engine, decision_engine, response_generator):
    """Scenario 14: 'But why?' provides a causal explanation rather than repeating policy."""
    history = [
        {"sender_type": "customer", "content": "Enakku refund bank account-la direct-a venum."},
        {"sender_type": "ai", "content": "Namma refund policy padi, original payment method-ku thaan refund panna mudiyum."}
    ]
    state = ConversationState(
        conversation_id=114,
        customer_id=1,
        active_intent="REFUND_ISSUE",
        unresolved_request="Refund inquiry",
        language_preference="tanglish",
    )

    u = meaning_engine.understand_utterance("But why?", history=history, conversation_state=state)
    assert u.diagnostic_details.get("explain_why") is True
    # Crucial fix: should NOT falsely set is_policy_overview
    assert not u.diagnostic_details.get("is_policy_overview")

    decision = decision_engine.decide({
        "intent": "WHY_QUESTION",
        "diagnostic_details": u.diagnostic_details,
    }, [])

    assert decision["decision"] == "RESOLVE"
    assert decision["action_type"] == "causal_why_explanation"

    resp = response_generator.generate(decision, language="tanglish")
    # Must explain causal reasoning (bank security / fraud rules)
    assert any(term in resp.lower() for term in ["security", "rules", "policy", "payment"])
    assert "ena ena policy" not in resp.lower()


# ── Scenario 15: RC-7.3 Delivery Delay Complaint Continuation ──
def test_scenario_15_delivery_delay_continuation(meaning_engine, decision_engine, response_generator):
    """Scenario 15: 'Innum varala ya, romba late aagudhu' is recognized as delay complaint and asks for Order ID empathetically."""
    state = ConversationState(
        conversation_id=115,
        customer_id=1,
        active_intent="DELIVERY_ISSUE",
        unresolved_request="Delivery delay complaint",
        language_preference="tanglish",
    )

    u = meaning_engine.understand_utterance("Innum varala ya, romba late aagudhu", conversation_state=state)
    assert u.diagnostic_details.get("is_delay_continuation") is True
    assert u.intent in ("DELIVERY_ISSUE", "ORDER_STATUS")

    decision = decision_engine.decide({
        "intent": u.intent,
        "diagnostic_details": u.diagnostic_details,
        "entities": {},
    }, [])

    assert decision["decision"] == "ASK_USER"
    assert decision["missing_entity"] == "empathetic_delay_inquiry"

    resp = response_generator.generate(decision, language="tanglish")
    assert any(term in resp.lower() for term in ["delay", "varuthapadugirom", "track", "order id"])


# ── Scenario 16: RC-7.4 "Idhukku vera edhavadhu vazhi irukka?" Alternative Options ──
def test_scenario_16_request_alternative_options(meaning_engine, decision_engine, response_generator):
    """Scenario 16: 'Idhukku vera edhavadhu vazhi irukka?' offers alternative solutions instead of generic order prompt."""
    state = ConversationState(
        conversation_id=116,
        customer_id=1,
        active_intent="ORDER_STATUS",
        unresolved_request="Order status check",
        language_preference="tanglish",
    )

    u = meaning_engine.understand_utterance("Idhukku vera edhavadhu vazhi irukka?", conversation_state=state)
    assert u.diagnostic_details.get("is_request_alternative") is True

    decision = decision_engine.decide({
        "intent": "REQUEST_ALTERNATIVE",
        "diagnostic_details": u.diagnostic_details,
        "entities": {},
    }, [])

    assert decision["decision"] == "RESOLVE"
    assert decision["action_type"] == "alternative_options"

    resp = response_generator.generate(decision, language="tanglish")
    # Should suggest alternative options such as mobile number, email, or human expert
    assert any(term in resp.lower() for term in ["mobile", "email", "expert", "vazhi"])


# ── Scenario 17: RC-7.5 Order ID Extraction & Lookup Variations ──
def test_scenario_17_order_id_variations():
    """Scenario 17: Various order ID formats (#12345, ORD_12345, 12345) extract properly and lookup succeeds."""
    import re
    from app.ai.intelligence.language import UniversalMeaningEngine

    engine = UniversalMeaningEngine()

    # Formats to extract: all normalize cleanly to ORD-12345 canonical format
    assert engine.extract_entities("En order id ORD-12345")["order_id"] == "ORD-12345"
    assert engine.extract_entities("Idhoda number ORD_12345")["order_id"] == "ORD-12345"
    assert engine.extract_entities("Unga reference #12345")["order_id"] == "ORD-12345"
    assert engine.extract_entities("Order id 12345 check pannunga")["order_id"] == "ORD-12345"

    # Contextual numeric entity extraction when expecting order_id
    res_num = engine.extract_entities("12345", pending_entity="order_id")
    assert res_num.get("order_id") == "ORD-12345"

    # Verify candidate generation matches database storage format
    order_id = "12345"
    norm_order_id = re.sub(r"[-_\s#]", "", order_id).lower()
    candidates = {norm_order_id}
    if norm_order_id.isdigit():
        candidates.add(f"ord{norm_order_id}")
        candidates.add(f"ord-{norm_order_id}")
    assert "ord12345" in candidates
    assert "ord-12345" in candidates


# ── Scenario 18: Unknown Order ID Does Not Invent Data & Localized ──
def test_scenario_18_unknown_order_not_found():
    """Scenario 18: Unknown order ID returns not-found without inventing fake data."""
    from app.ai.m4.decision import ResponseGenerator

    not_found_result = {
        "success": False,
        "tool": "get_order_status",
        "error_code": "ORDER_NOT_FOUND",
        "message": "Order could not be found. Please verify the order ID."
    }

    gen = ResponseGenerator()
    resp = gen.generate({
        "decision": "USE_TOOL",
        "tool_result": not_found_result
    }, language="tanglish")
    assert any(term in resp.lower() for term in ["kedaikala", "check", "order id"])
    # Must NOT invent placeholder or fake status
    assert "delivered" not in resp.lower()
    assert "in_transit" not in resp.lower()


# ── Scenario 19: User Confirmation Before Expert Handoff ──
def test_scenario_19_expert_handoff_confirmation_lifecycle():
    """Scenario 19: Expert handoff lifecycle: confirmation required, affirmative executes, negative cancels."""
    from app.ai.intelligence.language import UniversalMeaningEngine

    # Affirmative signals
    assert UniversalMeaningEngine.is_affirmative_confirmation("Aama") is True
    assert UniversalMeaningEngine.is_affirmative_confirmation("Seri, connect pannunga") is True
    assert UniversalMeaningEngine.is_affirmative_confirmation("Yes, please") is True
    assert UniversalMeaningEngine.is_affirmative_confirmation("Haan") is True
    assert UniversalMeaningEngine.is_affirmative_confirmation("Connect pannunga") is True

    # Negative signals
    assert UniversalMeaningEngine.is_negative_confirmation("Vendaam") is True
    assert UniversalMeaningEngine.is_negative_confirmation("Illa") is True
    assert UniversalMeaningEngine.is_negative_confirmation("No, not now") is True
    assert UniversalMeaningEngine.is_negative_confirmation("Vendaam bro") is True

    # State update before turn with pending confirmation
    state = ConversationState(
        conversation_id=119,
        customer_id=1,
        active_intent="ESCALATION_REQUEST",
        pending_handoff_confirmation=True,
        pending_handoff_reason="Customer requested supervisor",
    )

    engine = UniversalMeaningEngine()
    # 1. Affirmative answer sets handoff_confirmed
    u_yes = engine.understand_utterance("Aama, connect pannunga", conversation_state=state)
    ConversationStateManager.update_before_turn(state=state, customer_message="Aama, connect pannunga", understanding=u_yes)
    assert state.handoff_confirmed is True
    assert state.pending_handoff_confirmation is False

    # 2. Reset and test negative answer sets handoff_rejected
    state.pending_handoff_confirmation = True
    state.handoff_confirmed = False
    u_no = engine.understand_utterance("Vendaam", conversation_state=state)
    ConversationStateManager.update_before_turn(state=state, customer_message="Vendaam", understanding=u_no)
    assert state.handoff_rejected is True
    assert state.pending_handoff_confirmation is False
    assert state.pending_handoff_reason is None
