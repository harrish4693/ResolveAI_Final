"""
Standalone test runner for intelligence layer tests.
Runs without database/conftest dependencies.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime, timezone, timedelta

passed = 0
failed = 0
errors = []

def test(name):
    """Decorator to register and run a test."""
    def decorator(fn):
        global passed, failed
        try:
            fn()
            passed += 1
            print(f"  PASSED  {name}")
        except Exception as e:
            failed += 1
            errors.append((name, str(e)))
            print(f"  FAILED  {name}: {e}")
        return fn
    return decorator


# ==============================================================================
# CAPABILITY 1: Resolution Confidence Scoring
# ==============================================================================
print("\n=== Capability 1: Resolution Confidence Scoring ===")

from app.ai.intelligence.confidence import ResolutionConfidenceScorer

@test("high_confidence_greeting")
def _():
    scorer = ResolutionConfidenceScorer()
    analysis = {"intent": "GREETING", "entities": {}, "sentiment": "NEUTRAL", "priority": "LOW"}
    context = {"rag_results": [{"score": 0.6, "title": "FAQ", "content": "Welcome"}]}
    result = scorer.score(analysis, context)
    assert result.overall >= 70, f"Expected >= 70, got {result.overall}"
    assert result.recommendation == "RESOLVE"

@test("low_confidence_security")
def _():
    scorer = ResolutionConfidenceScorer()
    analysis = {"intent": "SECURITY_ISSUE", "entities": {}, "sentiment": "NEGATIVE", "priority": "CRITICAL"}
    result = scorer.score(analysis, {"rag_results": []})
    assert result.overall < 50, f"Expected < 50, got {result.overall}"
    assert result.recommendation == "ESCALATE"

@test("payment_with_entities_moderate")
def _():
    scorer = ResolutionConfidenceScorer()
    analysis = {"intent": "PAYMENT_ISSUE", "entities": {"transaction_id": "TXN123"}, "sentiment": "NEUTRAL", "priority": "MEDIUM"}
    context = {"rag_results": [{"score": 0.4, "title": "Payment FAQ"}]}
    result = scorer.score(analysis, context)
    assert result.overall >= 50, f"Expected >= 50, got {result.overall}"
    assert result.factors.context_completeness == 1.0

@test("missing_entities_lower_confidence")
def _():
    scorer = ResolutionConfidenceScorer()
    analysis = {"intent": "PAYMENT_ISSUE", "entities": {}, "priority": "LOW"}
    result = scorer.score(analysis, {"rag_results": [{"score": 0.3}]})
    assert result.factors.context_completeness == 0.0

@test("rag_improves_knowledge_availability")
def _():
    scorer = ResolutionConfidenceScorer()
    analysis = {"intent": "GENERAL_QUERY", "entities": {}, "priority": "LOW"}
    r1 = scorer.score(analysis, {"rag_results": [{"score": 0.7}]})
    r2 = scorer.score(analysis, {"rag_results": []})
    assert r1.factors.knowledge_availability > r2.factors.knowledge_availability

@test("positive_memory_boosts_confidence")
def _():
    scorer = ResolutionConfidenceScorer()
    analysis = {"intent": "GENERAL_QUERY", "entities": {}, "priority": "LOW"}
    context = {"rag_results": [], "relevant_memories": ["Issue was resolved successfully"]}
    result = scorer.score(analysis, context)
    assert result.factors.historical_success > 0.5

@test("negative_memory_lowers_confidence")
def _():
    scorer = ResolutionConfidenceScorer()
    context = {"rag_results": [], "relevant_memories": ["Previous attempt failed", "Issue unresolved"]}
    result = scorer.score({"intent": "GENERAL_QUERY", "entities": {}, "priority": "LOW"}, context)
    assert result.factors.historical_success < 0.5

@test("score_bounded_0_100")
def _():
    scorer = ResolutionConfidenceScorer()
    for intent in ["GREETING", "SECURITY_ISSUE", "PAYMENT_ISSUE", "DELIVERY_ISSUE"]:
        result = scorer.score({"intent": intent, "entities": {}, "priority": "LOW"}, {"rag_results": []})
        assert 0 <= result.overall <= 100, f"Score {result.overall} out of bounds for {intent}"

@test("critical_priority_increases_risk")
def _():
    scorer = ResolutionConfidenceScorer()
    r_crit = scorer.score({"intent": "PAYMENT_ISSUE", "entities": {}, "priority": "CRITICAL"}, {"rag_results": []})
    r_low = scorer.score({"intent": "PAYMENT_ISSUE", "entities": {}, "priority": "LOW"}, {"rag_results": []})
    assert r_crit.factors.risk_level < r_low.factors.risk_level


# ==============================================================================
# CAPABILITY 2: RAG Quality Verification
# ==============================================================================
print("\n=== Capability 2: RAG Quality Verification ===")

from app.ai.intelligence.rag_quality import RAGQualityVerifier, QueryPreprocessor

@test("good_rag_results_high_grade")
def _():
    v = RAGQualityVerifier()
    results = [{"id": 1, "title": "Payment Policy", "content": "Refund within 30 days", "score": 0.8, "category": "payment"}]
    q = v.verify("How to get a refund?", results, "PAYMENT_ISSUE")
    assert q.is_relevant
    assert q.quality_grade in ("A", "B")

@test("empty_results_grade_f")
def _():
    v = RAGQualityVerifier()
    q = v.verify("Where is my order?", [], "DELIVERY_ISSUE")
    assert not q.is_relevant
    assert q.quality_grade == "F"

@test("contradiction_detected")
def _():
    v = RAGQualityVerifier()
    results = [
        {"id": 1, "title": "R1", "content": "Items are eligible for refund", "score": 0.5},
        {"id": 2, "title": "R2", "content": "All items are non-refundable", "score": 0.4},
    ]
    q = v.verify("Can I get a refund?", results)
    assert q.has_contradiction

@test("no_contradiction_consistent")
def _():
    v = RAGQualityVerifier()
    results = [
        {"id": 1, "title": "D", "content": "Standard delivery takes 5-7 days", "score": 0.6},
        {"id": 2, "title": "S", "content": "Express delivery takes 1-2 days", "score": 0.5},
    ]
    q = v.verify("How long is delivery?", results)
    assert not q.has_contradiction

@test("source_verified")
def _():
    v = RAGQualityVerifier()
    q = v.verify("test", [{"id": 1, "title": "FAQ", "content": "Answer", "score": 0.5}])
    assert q.source_verified

@test("query_preprocessor")
def _():
    pp = QueryPreprocessor()
    result = pp.preprocess("Where is my order?", "DELIVERY_ISSUE", {"order_id": "ORD123"})
    assert "delivery issue" in result.lower()
    assert "ORD123" in result

@test("deduplication")
def _():
    pp = QueryPreprocessor()
    results = [{"id": 1, "title": "FAQ1"}, {"id": 1, "title": "FAQ1"}, {"id": 2, "title": "FAQ2"}]
    unique = pp.deduplicate_results(results)
    assert len(unique) == 2


# ==============================================================================
# CAPABILITY 3: Conversation Context Management
# ==============================================================================
print("\n=== Capability 3: Conversation Context Management ===")

from app.ai.intelligence.context import ConversationContextManager, ContextEnricher, ContextSummarizer

@test("build_context_window")
def _():
    mgr = ConversationContextManager(max_tokens=100)
    msgs = [{"sender_type": "customer", "content": "Hello"}, {"sender_type": "ai", "content": "Hi!"}]
    w = mgr.build_context_window(msgs)
    assert len(w.messages) == 2
    assert not w.is_truncated

@test("context_truncation")
def _():
    mgr = ConversationContextManager(max_tokens=20)
    msgs = [{"sender_type": "customer", "content": "x" * 100}, {"sender_type": "ai", "content": "y" * 100}, {"sender_type": "customer", "content": "z" * 20}]
    w = mgr.build_context_window(msgs)
    assert w.is_truncated
    assert len(w.messages) < 3

@test("empty_context")
def _():
    mgr = ConversationContextManager()
    w = mgr.build_context_window([])
    assert len(w.messages) == 0

@test("full_enrichment")
def _():
    e = ContextEnricher()
    r = e.enrich(
        conversation_history=[{"sender_type": "customer", "content": "Help"}],
        customer_memories=["Previous issue"], related_tickets=[{"id": 1}],
        rag_results=[{"title": "FAQ"}],
    )
    assert r.enrichment_score >= 0.7

@test("handoff_summary")
def _():
    s = ContextSummarizer()
    history = [{"sender_type": "customer", "content": "Double charged!"}, {"sender_type": "ai", "content": "Checking..."}]
    summary = s.summarize_for_handoff(history, {"entities": {"txn": "TXN123"}, "sentiment": "NEGATIVE"})
    assert summary["issue_description"] == "Double charged!"
    assert summary["sentiment"] == "NEGATIVE"

@test("context_stats")
def _():
    s = ContextSummarizer()
    stats = s.get_context_stats([{"sender_type": "customer", "content": "Hi"}, {"sender_type": "ai", "content": "Hello"}])
    assert stats["total_messages"] == 2
    assert stats["customer_messages"] == 1


# ==============================================================================
# CAPABILITY 4: Tool Decision Analysis
# ==============================================================================
print("\n=== Capability 4: Tool Decision Analysis ===")

from app.ai.intelligence.tool_decision import ToolAnalyzer, ToolAuthorizationChecker

@test("payment_recommends_transaction_tool")
def _():
    a = ToolAnalyzer()
    r = a.analyze(intent="PAYMENT_ISSUE", entities={"transaction_id": "TXN123"}, decision_state="USE_TOOL")
    assert r.should_use_tool
    assert r.best_tool in ("check_transaction", "get_order_status")

@test("delivery_recommends_order_tool")
def _():
    a = ToolAnalyzer()
    r = a.analyze(intent="DELIVERY_ISSUE", entities={"order_id": "ORD123"}, decision_state="USE_TOOL")
    assert r.should_use_tool
    assert r.best_tool == "get_order_status"

@test("missing_params_flagged")
def _():
    a = ToolAnalyzer()
    r = a.analyze(intent="PAYMENT_ISSUE", entities={})
    has_missing = any(rec.missing_parameters for rec in r.recommendations)
    assert has_missing

@test("greeting_no_tool")
def _():
    a = ToolAnalyzer()
    r = a.analyze(intent="GREETING", entities={})
    assert not r.should_use_tool

@test("security_recommends_human")
def _():
    a = ToolAnalyzer()
    r = a.analyze(intent="SECURITY_ISSUE", entities={}, decision_state="USE_TOOL")
    assert r.best_tool == "request_human_support"

@test("customer_authorized_for_order")
def _():
    c = ToolAuthorizationChecker()
    assert c.check_authorization("customer", "get_order_status")["authorized"]

@test("customer_not_for_update_ticket")
def _():
    c = ToolAuthorizationChecker()
    assert not c.check_authorization("customer", "update_ticket_info")["authorized"]

@test("admin_authorized_for_all")
def _():
    c = ToolAuthorizationChecker()
    for tool in ["get_order_status", "update_ticket_info", "request_human_support"]:
        assert c.check_authorization("admin", tool)["authorized"]

@test("expert_has_more_tools")
def _():
    c = ToolAuthorizationChecker()
    assert len(c.get_available_tools("expert")) >= len(c.get_available_tools("customer"))


# ==============================================================================
# CAPABILITY 5: Resolution vs Escalation Intelligence
# ==============================================================================
print("\n=== Capability 5: Escalation Decision Engine ===")

from app.ai.intelligence.escalation import EscalationDecisionEngine

@test("security_always_escalates")
def _():
    e = EscalationDecisionEngine()
    r = e.evaluate({"intent": "SECURITY_ISSUE", "entities": {}, "sentiment": "NEGATIVE", "priority": "HIGH"}, {"rag_results": []})
    assert r.decision.value == "ESCALATE"

@test("critical_priority_escalates")
def _():
    e = EscalationDecisionEngine()
    r = e.evaluate({"intent": "PAYMENT_ISSUE", "entities": {}, "priority": "CRITICAL"}, {"rag_results": []})
    assert r.decision.value == "ESCALATE"

@test("simple_greeting_resolves")
def _():
    e = EscalationDecisionEngine()
    r = e.evaluate({"intent": "GREETING", "entities": {}, "sentiment": "NEUTRAL", "priority": "LOW"}, {"rag_results": [{"score": 0.7, "title": "FAQ"}]})
    assert r.decision.value == "RESOLVE"

@test("refund_needs_confirmation")
def _():
    e = EscalationDecisionEngine()
    r = e.evaluate({"intent": "REFUND_ISSUE", "entities": {"txn": "T1"}, "sentiment": "NEUTRAL", "priority": "MEDIUM"}, {"rag_results": [{"score": 0.5}]})
    assert r.decision.value in ("CONFIRM", "ESCALATE")

@test("frustrated_customer_escalated")
def _():
    e = EscalationDecisionEngine()
    r = e.evaluate({"intent": "PAYMENT_ISSUE", "entities": {}, "sentiment": "NEGATIVE", "priority": "MEDIUM"}, {"rag_results": []})
    assert r.decision.value == "ESCALATE"

@test("repeated_attempts_escalate")
def _():
    e = EscalationDecisionEngine()
    r = e.evaluate({"intent": "GENERAL_QUERY", "entities": {}, "priority": "LOW"}, {"rag_results": [{"score": 0.5}], "attempt_count": 5})
    assert r.decision.value == "ESCALATE"

@test("escalation_context_populated")
def _():
    e = EscalationDecisionEngine()
    r = e.evaluate({"intent": "PAYMENT_ISSUE", "entities": {"txn": "T1"}, "sentiment": "NEGATIVE", "priority": "HIGH"}, {"rag_results": []})
    assert r.context.recommended_specialization == "Payments/Finance"


# ==============================================================================
# CAPABILITY 6: Code-Mixed Language / Tanglish
# ==============================================================================
print("\n=== Capability 6: Code-Mixed Language ===")

from app.ai.intelligence.language import CodeMixedLanguageDetector, IndianLanguageNormalizer, CodeMixedIntentExtractor

@test("pure_english_detected")
def _():
    d = CodeMixedLanguageDetector()
    r = d.detect("I need help with my order please")
    assert r.primary_language == "en"
    assert not r.is_code_mixed

@test("tanglish_romanized_detected")
def _():
    d = CodeMixedLanguageDetector()
    r = d.detect("Bro my payment irukku but delivery illa da")
    assert r.is_code_mixed
    assert r.code_mix_type == "tanglish"

@test("tamil_script_detected")
def _():
    d = CodeMixedLanguageDetector()
    r = d.detect("எனது ஆர்டர் எங்கே?")
    assert r.primary_language == "ta"
    assert "tamil" in r.script_types

@test("hindi_script_detected")
def _():
    d = CodeMixedLanguageDetector()
    r = d.detect("मेरा ऑर्डर कहाँ है?")
    assert r.primary_language == "hi"
    assert "devanagari" in r.script_types

@test("mixed_tamil_english_detected")
def _():
    d = CodeMixedLanguageDetector()
    r = d.detect("My order எங்கே இருக்கு?")
    assert r.is_code_mixed
    assert r.primary_language == "ta"
    assert "en" in r.mixed_with

@test("hinglish_romanized")
def _():
    d = CodeMixedLanguageDetector()
    r = d.detect("Mera order nahi aaya hai bhai")
    assert r.is_code_mixed
    assert r.code_mix_type == "hinglish"

@test("tanglish_normalization")
def _():
    n = IndianLanguageNormalizer()
    r = n.normalize("payment irukku but delivery illa")
    assert "is" in r.normalized
    assert "not" in r.normalized
    assert len(r.detected_slang) > 0

@test("empty_normalization")
def _():
    n = IndianLanguageNormalizer()
    r = n.normalize("")
    assert r.normalized == ""

@test("tanglish_payment_intent")
def _():
    e = CodeMixedIntentExtractor()
    r = e.extract_intent("Bro my panam deducted but order illa")
    assert r["intent"] == "PAYMENT_ISSUE"
    assert r["is_code_mixed"]

@test("tanglish_delivery_with_entity")
def _():
    e = CodeMixedIntentExtractor()
    r = e.extract_intent("Order eppo varum da? ORD456")
    assert r["intent"] == "DELIVERY_ISSUE"
    assert "ORD456" in str(r["entities"])

@test("entity_from_mixed_message")
def _():
    e = CodeMixedIntentExtractor()
    r = e.extract_intent("TXN789 transaction check pannunga")
    assert "TXN789" in str(r["entities"])


# ==============================================================================
# CAPABILITY 7: Resolution Failure Prediction
# ==============================================================================
print("\n=== Capability 7: Failure Prediction ===")

from app.ai.intelligence.failure_prediction import FailurePredictor, FrustrationDetector, ResolutionAttemptTracker

@test("calm_customer_low_frustration")
def _():
    d = FrustrationDetector()
    f = d.estimate_frustration("Could you help me check my order?", [])
    assert f < 0.3

@test("angry_customer_high_frustration")
def _():
    d = FrustrationDetector()
    f = d.estimate_frustration("This is TERRIBLE! I am FED UP with your useless service!!!", [{"content": "x"}] * 8)
    assert f > 0.5

@test("escalation_request_detected")
def _():
    d = FrustrationDetector()
    f = d.estimate_frustration("I want to talk to a real person", [{"content": "x"}] * 4)
    assert f > 0.2

@test("all_caps_shouting")
def _():
    d = FrustrationDetector()
    f = d.estimate_frustration("WHERE IS MY ORDER WHY IS NOBODY HELPING", [])
    assert f > 0.1

@test("low_risk_prediction")
def _():
    p = FailurePredictor()
    r = p.predict({"intent": "GREETING", "entities": {}, "sentiment": "NEUTRAL", "original_message": "Hello"}, {"rag_results": [{"score": 0.5}], "history": []})
    assert r.probability < 0.4
    assert not r.should_escalate_early

@test("high_risk_security_prediction")
def _():
    p = FailurePredictor()
    r = p.predict({"intent": "SECURITY_ISSUE", "entities": {}, "sentiment": "NEGATIVE", "original_message": "My account was hacked! This is TERRIBLE and RIDICULOUS! I am FED UP! Talk to someone!!!"}, {"rag_results": [], "history": [{"content": "x"}] * 10})
    assert r.probability > 0.4

@test("repeated_failures_increase")
def _():
    p = FailurePredictor()
    t = ResolutionAttemptTracker()
    for _ in range(3):
        t.track_attempt(1, "rag", False, "No results")
    r = p.predict({"intent": "GENERAL_QUERY", "entities": {}, "original_message": "Help"}, {"rag_results": [], "history": []}, t, 1)
    assert r.probability > 0.3

@test("attempt_tracker_operations")
def _():
    t = ResolutionAttemptTracker()
    t.track_attempt(1, "rag", True)
    t.track_attempt(1, "tool", False, "ERR")
    assert t.get_attempt_count(1) == 2
    assert t.get_failure_count(1) == 1
    assert t.get_success_rate(1) == 0.5
    t.clear(1)
    assert t.get_attempt_count(1) == 0


# ==============================================================================
# CAPABILITY 8: Cross-Ticket Incident Discovery
# ==============================================================================
print("\n=== Capability 8: Incident Discovery ===")

from app.ai.intelligence.incidents import IncidentDetector, TicketSimilarityAnalyzer, TicketSnapshot

@test("identical_tickets_high_similarity")
def _():
    a = TicketSimilarityAnalyzer()
    now = datetime.now(timezone.utc)
    ta = TicketSnapshot(ticket_id=1, subject="Payment failed", category="payment", intent="PAYMENT_ISSUE", created_at=now)
    tb = TicketSnapshot(ticket_id=2, subject="Payment failed", category="payment", intent="PAYMENT_ISSUE", created_at=now + timedelta(minutes=5))
    s = a.compute_similarity(ta, tb)
    assert s.overall > 0.7

@test("unrelated_tickets_low_similarity")
def _():
    a = TicketSimilarityAnalyzer()
    now = datetime.now(timezone.utc)
    ta = TicketSnapshot(ticket_id=1, subject="Payment failed", category="payment", intent="PAYMENT_ISSUE", created_at=now)
    tb = TicketSnapshot(ticket_id=2, subject="Login not working", category="account", intent="LOGIN_ISSUE", created_at=now + timedelta(days=30))
    s = a.compute_similarity(ta, tb)
    assert s.overall < 0.4

@test("detect_payment_incident")
def _():
    d = IncidentDetector()
    now = datetime.now(timezone.utc)
    tickets = [
        TicketSnapshot(ticket_id=i, subject="Payment gateway error", category="payment",
                      intent="PAYMENT_ISSUE", created_at=now + timedelta(minutes=i * 5),
                      customer_id=100 + i, tenant_id="t1")
        for i in range(5)
    ]
    incidents = d.detect_incidents(tickets, tenant_id="t1")
    assert len(incidents) >= 1
    assert incidents[0].affected_customer_count >= 2

@test("single_ticket_no_incident")
def _():
    d = IncidentDetector()
    tickets = [TicketSnapshot(ticket_id=1, subject="Help", tenant_id="t1")]
    assert len(d.detect_incidents(tickets, "t1")) == 0

@test("tenant_isolation_incidents")
def _():
    d = IncidentDetector()
    now = datetime.now(timezone.utc)
    tickets = [
        TicketSnapshot(ticket_id=1, subject="Payment error", category="payment", intent="PAYMENT_ISSUE", created_at=now, tenant_id="a"),
        TicketSnapshot(ticket_id=2, subject="Payment error", category="payment", intent="PAYMENT_ISSUE", created_at=now, tenant_id="b"),
    ]
    assert len(d.detect_incidents(tickets, "a")) == 0  # 1 ticket per tenant
    assert len(d.detect_incidents(tickets, "b")) == 0

@test("severity_scales_with_count")
def _():
    d = IncidentDetector()
    now = datetime.now(timezone.utc)
    tickets = [
        TicketSnapshot(ticket_id=i, subject="Payment gateway error", category="payment",
                      intent="PAYMENT_ISSUE", created_at=now + timedelta(minutes=i),
                      customer_id=100 + i, tenant_id="t")
        for i in range(6)
    ]
    incidents = d.detect_incidents(tickets, "t")
    assert len(incidents) >= 1
    assert incidents[0].severity in ("HIGH", "CRITICAL")


# ==============================================================================
# CAPABILITY 9: Adaptive Autonomy Engine
# ==============================================================================
print("\n=== Capability 9: Adaptive Autonomy ===")

from app.ai.intelligence.autonomy import AutonomyLevelDeterminer, AutonomyAdapter

@test("greeting_automatic")
def _():
    d = AutonomyLevelDeterminer()
    r = d.determine_level({"intent": "GREETING", "entities": {}, "sentiment": "NEUTRAL", "priority": "LOW"}, {"rag_results": [{"score": 0.7, "title": "FAQ"}]})
    assert r.level.value == "AUTOMATIC"

@test("security_escalates")
def _():
    d = AutonomyLevelDeterminer()
    r = d.determine_level({"intent": "SECURITY_ISSUE", "entities": {}, "priority": "HIGH"}, {"rag_results": []})
    assert r.level.value == "ESCALATE"

@test("critical_escalates")
def _():
    d = AutonomyLevelDeterminer()
    r = d.determine_level({"intent": "GENERAL_QUERY", "entities": {}, "priority": "CRITICAL"}, {"rag_results": []})
    assert r.level.value == "ESCALATE"

@test("max_attempts_escalates")
def _():
    d = AutonomyLevelDeterminer()
    r = d.determine_level({"intent": "GENERAL_QUERY", "entities": {}, "priority": "LOW"}, {"rag_results": [{"score": 0.9}], "attempt_count": 5})
    assert r.level.value == "ESCALATE"

@test("high_risk_tool_requires_confirmation")
def _():
    d = AutonomyLevelDeterminer()
    r = d.determine_level({"intent": "REFUND_ISSUE", "entities": {}, "priority": "MEDIUM", "decision_state": "USE_TOOL", "tool_name": "create_refund_request"}, {"rag_results": [{"score": 0.5}]})
    assert r.level.value == "CONFIRMATION_REQUIRED"

@test("adapter_high_success_lowers_threshold")
def _():
    a = AutonomyAdapter()
    for _ in range(10):
        a.record_outcome("GENERAL_QUERY", True)
    t = a.get_adjusted_thresholds("GENERAL_QUERY")
    assert t.auto_resolve_min_confidence < 75.0

@test("adapter_low_success_raises_threshold")
def _():
    a = AutonomyAdapter()
    for _ in range(10):
        a.record_outcome("PAYMENT_ISSUE", False)
    t = a.get_adjusted_thresholds("PAYMENT_ISSUE")
    assert t.auto_resolve_min_confidence > 75.0

@test("adapter_unknown_neutral")
def _():
    a = AutonomyAdapter()
    assert a.get_success_rate("UNKNOWN") is None


# ==============================================================================
# CAPABILITY 10: Intelligent Expert Routing
# ==============================================================================
print("\n=== Capability 10: Expert Routing ===")

from app.ai.intelligence.routing import ExpertMatcher, RoutingDecisionEngine, ExpertProfile, RoutingCase

def _make_experts():
    return [
        ExpertProfile(expert_id=1, name="PaymentExpert", expertise_areas=["Payments/Finance"],
                     proficiency_levels={"Payments/Finance": 5}, current_workload=1, max_concurrent=5,
                     is_available=True, satisfaction_rating=4.8, total_resolved=200),
        ExpertProfile(expert_id=2, name="SecurityExpert", expertise_areas=["Security", "Account/Auth"],
                     proficiency_levels={"Security": 5, "Account/Auth": 4}, current_workload=3, max_concurrent=5,
                     is_available=True, satisfaction_rating=4.5, total_resolved=150),
        ExpertProfile(expert_id=3, name="GeneralExpert", expertise_areas=["General Support"],
                     proficiency_levels={"General Support": 3}, current_workload=0, max_concurrent=5,
                     is_available=True, satisfaction_rating=3.5, total_resolved=50),
    ]

@test("payment_routed_to_payment_expert")
def _():
    m = ExpertMatcher()
    d = m.match(RoutingCase(category="Payments/Finance", priority="HIGH"), _make_experts())
    assert d.primary_expert_id == 1

@test("security_routed_to_security_expert")
def _():
    m = ExpertMatcher()
    d = m.match(RoutingCase(category="Security", priority="CRITICAL"), _make_experts())
    assert d.primary_expert_id == 2

@test("no_experts_handled")
def _():
    m = ExpertMatcher()
    d = m.match(RoutingCase(category="General Support"), [])
    assert d.primary_expert_id is None
    assert d.estimated_wait_minutes > 0

@test("fallback_selected")
def _():
    m = ExpertMatcher()
    d = m.match(RoutingCase(category="Payments/Finance"), _make_experts())
    assert d.primary_expert_id is not None
    assert d.fallback_expert_id is not None
    assert d.primary_expert_id != d.fallback_expert_id

@test("unavailable_expert_not_primary")
def _():
    m = ExpertMatcher()
    experts = [
        ExpertProfile(expert_id=1, expertise_areas=["Payments/Finance"], proficiency_levels={"Payments/Finance": 5}, is_available=False, max_concurrent=5, current_workload=0),
        ExpertProfile(expert_id=2, expertise_areas=["Payments/Finance", "General Support"], proficiency_levels={"Payments/Finance": 3, "General Support": 3}, is_available=True, max_concurrent=5, current_workload=0, satisfaction_rating=4.0, total_resolved=50),
    ]
    d = m.match(RoutingCase(category="Payments/Finance"), experts)
    assert d.primary_expert_id == 2

@test("overloaded_expert_penalized")
def _():
    m = ExpertMatcher()
    experts = [
        ExpertProfile(expert_id=1, expertise_areas=["Payments/Finance"], proficiency_levels={"Payments/Finance": 5}, is_available=True, max_concurrent=5, current_workload=5, satisfaction_rating=5.0, total_resolved=200),
        ExpertProfile(expert_id=2, expertise_areas=["Payments/Finance"], proficiency_levels={"Payments/Finance": 4}, is_available=True, max_concurrent=5, current_workload=0, satisfaction_rating=4.0, total_resolved=100),
    ]
    d = m.match(RoutingCase(category="Payments/Finance"), experts)
    assert d.primary_expert_id == 2

@test("load_balanced_routing")
def _():
    e = RoutingDecisionEngine()
    experts = [
        ExpertProfile(expert_id=1, expertise_areas=["General Support"], proficiency_levels={"General Support": 4}, is_available=True, max_concurrent=5, current_workload=4, satisfaction_rating=4.5, total_resolved=100),
        ExpertProfile(expert_id=2, expertise_areas=["General Support"], proficiency_levels={"General Support": 3}, is_available=True, max_concurrent=5, current_workload=0, satisfaction_rating=4.0, total_resolved=80),
    ]
    d = e.route(RoutingCase(category="General Support", priority="LOW"), experts)
    assert d.primary_expert_id == 2


# ==============================================================================
# SUMMARY
# ==============================================================================
print(f"\n{'='*60}")
print(f"RESULTS: {passed} passed, {failed} failed")
print(f"{'='*60}")

if errors:
    print("\nFAILURES:")
    for name, err in errors:
        print(f"  - {name}: {err}")

sys.exit(0 if failed == 0 else 1)
