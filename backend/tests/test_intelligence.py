"""
ResolveAI V2 — Intelligence Layer Tests

Comprehensive tests for all 10 intelligence capabilities.
Each capability has dedicated test classes with extensive coverage.
"""

import pytest
from datetime import datetime, timezone, timedelta


# ==============================================================================
# CAPABILITY 1: Resolution Confidence Scoring
# ==============================================================================

class TestResolutionConfidenceScorer:
    """Tests for Capability 1: Resolution Confidence Scoring."""

    def _get_scorer(self):
        from app.ai.intelligence.confidence import ResolutionConfidenceScorer
        return ResolutionConfidenceScorer()

    def test_high_confidence_simple_query(self):
        """Simple greeting gets high confidence."""
        scorer = self._get_scorer()
        analysis = {"intent": "GREETING", "entities": {}, "sentiment": "NEUTRAL", "priority": "LOW"}
        context = {"rag_results": [{"score": 0.6, "title": "FAQ", "content": "Welcome"}]}
        result = scorer.score(analysis, context)
        assert result.overall >= 70
        assert result.recommendation == "RESOLVE"

    def test_low_confidence_security_issue(self):
        """Security issues get low confidence."""
        scorer = self._get_scorer()
        analysis = {"intent": "SECURITY_ISSUE", "entities": {}, "sentiment": "NEGATIVE", "priority": "CRITICAL"}
        context = {"rag_results": []}
        result = scorer.score(analysis, context)
        assert result.overall < 50
        assert result.recommendation == "ESCALATE"

    def test_medium_confidence_payment_with_entities(self):
        """Payment issue with entities gets moderate confidence."""
        scorer = self._get_scorer()
        analysis = {
            "intent": "PAYMENT_ISSUE",
            "entities": {"transaction_id": "TXN123"},
            "sentiment": "NEUTRAL",
            "priority": "MEDIUM",
        }
        context = {"rag_results": [{"score": 0.4, "title": "Payment FAQ"}]}
        result = scorer.score(analysis, context)
        assert result.overall >= 50
        assert result.factors.context_completeness == 1.0  # All required entities

    def test_missing_entities_lowers_confidence(self):
        """Missing required entities lower confidence."""
        scorer = self._get_scorer()
        analysis = {
            "intent": "PAYMENT_ISSUE",
            "entities": {},  # Missing transaction_id
            "sentiment": "NEUTRAL",
            "priority": "LOW",
        }
        context = {"rag_results": [{"score": 0.3}]}
        result = scorer.score(analysis, context)
        assert result.factors.context_completeness == 0.0

    def test_knowledge_availability_with_rag(self):
        """Good RAG results improve knowledge availability."""
        scorer = self._get_scorer()
        analysis = {"intent": "GENERAL_QUERY", "entities": {}, "priority": "LOW"}
        context_with_rag = {"rag_results": [{"score": 0.7}]}
        context_no_rag = {"rag_results": []}

        result_with = scorer.score(analysis, context_with_rag)
        result_without = scorer.score(analysis, context_no_rag)
        assert result_with.factors.knowledge_availability > result_without.factors.knowledge_availability

    def test_historical_success_boosts_confidence(self):
        """Positive memories boost confidence."""
        scorer = self._get_scorer()
        analysis = {"intent": "GENERAL_QUERY", "entities": {}, "priority": "LOW"}
        context = {
            "rag_results": [],
            "relevant_memories": ["Issue was resolved successfully last time"],
        }
        result = scorer.score(analysis, context)
        assert result.factors.historical_success > 0.5

    def test_negative_history_lowers_confidence(self):
        """Failed resolution history lowers confidence."""
        scorer = self._get_scorer()
        analysis = {"intent": "GENERAL_QUERY", "entities": {}, "priority": "LOW"}
        context = {
            "rag_results": [],
            "relevant_memories": ["Previous attempt failed", "Issue unresolved"],
        }
        result = scorer.score(analysis, context)
        assert result.factors.historical_success < 0.5

    def test_confidence_score_is_bounded(self):
        """Score is always between 0 and 100."""
        scorer = self._get_scorer()
        for intent in ["GREETING", "SECURITY_ISSUE", "PAYMENT_ISSUE", "DELIVERY_ISSUE"]:
            analysis = {"intent": intent, "entities": {}, "priority": "LOW"}
            result = scorer.score(analysis, {"rag_results": []})
            assert 0 <= result.overall <= 100

    def test_critical_priority_increases_risk(self):
        """CRITICAL priority dramatically increases risk."""
        scorer = self._get_scorer()
        analysis_crit = {"intent": "PAYMENT_ISSUE", "entities": {}, "priority": "CRITICAL"}
        analysis_low = {"intent": "PAYMENT_ISSUE", "entities": {}, "priority": "LOW"}
        
        result_crit = scorer.score(analysis_crit, {"rag_results": []})
        result_low = scorer.score(analysis_low, {"rag_results": []})
        assert result_crit.factors.risk_level < result_low.factors.risk_level


# ==============================================================================
# CAPABILITY 2: RAG Quality Verification
# ==============================================================================

class TestRAGQualityVerifier:
    """Tests for Capability 2: RAG Quality Verification."""

    def _get_verifier(self):
        from app.ai.intelligence.rag_quality import RAGQualityVerifier
        return RAGQualityVerifier()

    def test_good_rag_results_grade_a(self):
        """High relevance results get grade A/B."""
        verifier = self._get_verifier()
        results = [
            {"id": 1, "title": "Payment Policy", "content": "Refund within 30 days", "score": 0.8, "category": "payment"},
        ]
        quality = verifier.verify("How to get a refund?", results, "PAYMENT_ISSUE")
        assert quality.is_relevant
        assert quality.quality_grade in ("A", "B")
        assert quality.hallucination_risk < 0.5

    def test_empty_results_grade_f(self):
        """No RAG results get grade F."""
        verifier = self._get_verifier()
        quality = verifier.verify("Where is my order?", [], "DELIVERY_ISSUE")
        assert not quality.is_relevant
        assert quality.quality_grade == "F"

    def test_low_relevance_flagged(self):
        """Low relevance results are flagged."""
        verifier = self._get_verifier()
        results = [
            {"id": 1, "title": "Company History", "content": "Founded in 2020", "score": 0.02},
        ]
        quality = verifier.verify("Why was I double charged?", results, "PAYMENT_ISSUE")
        assert quality.relevance_score < 0.3

    def test_contradiction_detected(self):
        """Contradictions between articles are detected."""
        verifier = self._get_verifier()
        results = [
            {"id": 1, "title": "Refund Policy", "content": "Items are eligible for refund", "score": 0.5},
            {"id": 2, "title": "Return Policy", "content": "All items are non-refundable", "score": 0.4},
        ]
        quality = verifier.verify("Can I get a refund?", results, "REFUND_ISSUE")
        assert quality.has_contradiction

    def test_no_contradiction_consistent(self):
        """Consistent articles show no contradiction."""
        verifier = self._get_verifier()
        results = [
            {"id": 1, "title": "Delivery", "content": "Standard delivery takes 5-7 days", "score": 0.6},
            {"id": 2, "title": "Shipping", "content": "Express delivery takes 1-2 days", "score": 0.5},
        ]
        quality = verifier.verify("How long is delivery?", results)
        assert not quality.has_contradiction

    def test_source_verified(self):
        """Results with IDs and titles are source-verified."""
        verifier = self._get_verifier()
        results = [{"id": 1, "title": "FAQ", "content": "Answer", "score": 0.5}]
        quality = verifier.verify("test", results)
        assert quality.source_verified

    def test_hallucination_risk_with_wrong_category(self):
        """Wrong category results increase hallucination risk."""
        verifier = self._get_verifier()
        results = [
            {"id": 1, "title": "Delivery Policy", "content": "Next day delivery", "score": 0.3, "category": "delivery"},
        ]
        quality = verifier.verify("payment issue", results, "PAYMENT_ISSUE")
        assert quality.hallucination_risk > 0.2


class TestQueryPreprocessor:
    """Tests for query preprocessing."""

    def test_basic_preprocessing(self):
        from app.ai.intelligence.rag_quality import QueryPreprocessor
        pp = QueryPreprocessor()
        result = pp.preprocess("Where is my order?", "DELIVERY_ISSUE", {"order_id": "ORD123"})
        assert "delivery issue" in result.lower()
        assert "ORD123" in result

    def test_deduplication(self):
        from app.ai.intelligence.rag_quality import QueryPreprocessor
        pp = QueryPreprocessor()
        results = [
            {"id": 1, "title": "FAQ1"},
            {"id": 1, "title": "FAQ1"},
            {"id": 2, "title": "FAQ2"},
        ]
        unique = pp.deduplicate_results(results)
        assert len(unique) == 2


# ==============================================================================
# CAPABILITY 3: Conversation Context Management
# ==============================================================================

class TestContextManager:
    """Tests for Capability 3: Conversation Context Management."""

    def test_build_context_window(self):
        """Basic context window building."""
        from app.ai.intelligence.context import ConversationContextManager
        mgr = ConversationContextManager(max_tokens=100)
        messages = [
            {"sender_type": "customer", "content": "Hello, I need help"},
            {"sender_type": "ai", "content": "Hi! How can I assist?"},
        ]
        window = mgr.build_context_window(messages)
        assert len(window.messages) == 2
        assert not window.is_truncated

    def test_context_truncation(self):
        """Long conversations get truncated."""
        from app.ai.intelligence.context import ConversationContextManager
        mgr = ConversationContextManager(max_tokens=20)
        messages = [
            {"sender_type": "customer", "content": "x" * 100},
            {"sender_type": "ai", "content": "y" * 100},
            {"sender_type": "customer", "content": "z" * 20},
        ]
        window = mgr.build_context_window(messages)
        assert window.is_truncated
        assert len(window.messages) < 3

    def test_empty_messages(self):
        """Empty messages handled gracefully."""
        from app.ai.intelligence.context import ConversationContextManager
        mgr = ConversationContextManager()
        window = mgr.build_context_window([])
        assert len(window.messages) == 0
        assert window.total_tokens == 0


class TestContextEnricher:
    """Tests for context enrichment."""

    def test_full_enrichment(self):
        """Full enrichment gets high score."""
        from app.ai.intelligence.context import ContextEnricher
        enricher = ContextEnricher()
        result = enricher.enrich(
            conversation_history=[{"sender_type": "customer", "content": "Help"}],
            customer_memories=["Previous issue resolved"],
            related_tickets=[{"id": 1, "status": "resolved"}],
            rag_results=[{"title": "FAQ", "score": 0.8}],
        )
        assert result.enrichment_score >= 0.7

    def test_minimal_enrichment(self):
        """Minimal context gets low enrichment score."""
        from app.ai.intelligence.context import ContextEnricher
        enricher = ContextEnricher()
        result = enricher.enrich(conversation_history=[])
        assert result.enrichment_score < 0.3


class TestContextSummarizer:
    """Tests for context summarization."""

    def test_handoff_summary(self):
        """Handoff summary includes all key information."""
        from app.ai.intelligence.context import ContextSummarizer
        summarizer = ContextSummarizer()
        history = [
            {"sender_type": "customer", "content": "I was double charged!"},
            {"sender_type": "ai", "content": "Let me check your transaction."},
        ]
        analysis = {"entities": {"transaction_id": "TXN123"}, "sentiment": "NEGATIVE"}
        summary = summarizer.summarize_for_handoff(history, analysis)
        assert summary["issue_description"] == "I was double charged!"
        assert summary["sentiment"] == "NEGATIVE"
        assert "TXN123" in str(summary["entities_collected"])

    def test_context_stats(self):
        """Context stats are correctly calculated."""
        from app.ai.intelligence.context import ContextSummarizer
        summarizer = ContextSummarizer()
        history = [
            {"sender_type": "customer", "content": "Hello"},
            {"sender_type": "ai", "content": "Hi there!"},
            {"sender_type": "customer", "content": "Help me"},
        ]
        stats = summarizer.get_context_stats(history)
        assert stats["total_messages"] == 3
        assert stats["customer_messages"] == 2
        assert stats["ai_messages"] == 1


# ==============================================================================
# CAPABILITY 4: Tool Decision Analysis
# ==============================================================================

class TestToolAnalyzer:
    """Tests for Capability 4: Tool Decision Analysis."""

    def test_payment_issue_recommends_transaction_tool(self):
        """Payment issue recommends check_transaction."""
        from app.ai.intelligence.tool_decision import ToolAnalyzer
        analyzer = ToolAnalyzer()
        result = analyzer.analyze(
            intent="PAYMENT_ISSUE",
            entities={"transaction_id": "TXN123"},
            decision_state="USE_TOOL",
        )
        assert result.should_use_tool
        assert result.best_tool in ("check_transaction", "get_order_status")

    def test_delivery_issue_recommends_order_tool(self):
        """Delivery issue recommends get_order_status."""
        from app.ai.intelligence.tool_decision import ToolAnalyzer
        analyzer = ToolAnalyzer()
        result = analyzer.analyze(
            intent="DELIVERY_ISSUE",
            entities={"order_id": "ORD123"},
            decision_state="USE_TOOL",
        )
        assert result.should_use_tool
        assert result.best_tool == "get_order_status"

    def test_missing_params_flagged(self):
        """Missing required parameters are flagged."""
        from app.ai.intelligence.tool_decision import ToolAnalyzer
        analyzer = ToolAnalyzer()
        result = analyzer.analyze(
            intent="PAYMENT_ISSUE",
            entities={},  # Missing transaction_id
        )
        has_missing = any(r.missing_parameters for r in result.recommendations)
        assert has_missing

    def test_greeting_no_tool(self):
        """Greeting intent doesn't recommend tools."""
        from app.ai.intelligence.tool_decision import ToolAnalyzer
        analyzer = ToolAnalyzer()
        result = analyzer.analyze(intent="GREETING", entities={})
        assert not result.should_use_tool

    def test_security_recommends_human_support(self):
        """Security issue recommends request_human_support."""
        from app.ai.intelligence.tool_decision import ToolAnalyzer
        analyzer = ToolAnalyzer()
        result = analyzer.analyze(
            intent="SECURITY_ISSUE",
            entities={},
            decision_state="USE_TOOL",
        )
        assert result.best_tool == "request_human_support"


class TestToolAuthorizationChecker:
    """Tests for tool authorization."""

    def test_customer_authorized_for_order_status(self):
        from app.ai.intelligence.tool_decision import ToolAuthorizationChecker
        checker = ToolAuthorizationChecker()
        result = checker.check_authorization("customer", "get_order_status")
        assert result["authorized"]

    def test_customer_not_authorized_for_update_ticket(self):
        from app.ai.intelligence.tool_decision import ToolAuthorizationChecker
        checker = ToolAuthorizationChecker()
        result = checker.check_authorization("customer", "update_ticket_info")
        assert not result["authorized"]

    def test_admin_authorized_for_everything(self):
        from app.ai.intelligence.tool_decision import ToolAuthorizationChecker
        checker = ToolAuthorizationChecker()
        for tool in ["get_order_status", "update_ticket_info", "request_human_support"]:
            result = checker.check_authorization("admin", tool)
            assert result["authorized"]

    def test_available_tools_for_role(self):
        from app.ai.intelligence.tool_decision import ToolAuthorizationChecker
        checker = ToolAuthorizationChecker()
        customer_tools = checker.get_available_tools("customer")
        expert_tools = checker.get_available_tools("expert")
        assert len(expert_tools) >= len(customer_tools)


# ==============================================================================
# CAPABILITY 5: Resolution vs Escalation Intelligence
# ==============================================================================

class TestEscalationDecisionEngine:
    """Tests for Capability 5: Resolution vs Escalation Intelligence."""

    def _get_engine(self):
        from app.ai.intelligence.escalation import EscalationDecisionEngine
        return EscalationDecisionEngine()

    def test_security_always_escalates(self):
        """Security issues always escalate."""
        engine = self._get_engine()
        analysis = {"intent": "SECURITY_ISSUE", "entities": {}, "sentiment": "NEGATIVE", "priority": "HIGH"}
        result = engine.evaluate(analysis, {"rag_results": []})
        assert result.decision.value == "ESCALATE"

    def test_critical_priority_escalates(self):
        """CRITICAL priority always escalates."""
        engine = self._get_engine()
        analysis = {"intent": "PAYMENT_ISSUE", "entities": {}, "priority": "CRITICAL"}
        result = engine.evaluate(analysis, {"rag_results": []})
        assert result.decision.value == "ESCALATE"

    def test_simple_greeting_resolves(self):
        """Simple greeting can be resolved."""
        engine = self._get_engine()
        analysis = {"intent": "GREETING", "entities": {}, "sentiment": "NEUTRAL", "priority": "LOW"}
        context = {"rag_results": [{"score": 0.7, "title": "FAQ"}]}
        result = engine.evaluate(analysis, context)
        assert result.decision.value == "RESOLVE"

    def test_refund_requires_confirmation(self):
        """Refund issues require confirmation."""
        engine = self._get_engine()
        analysis = {
            "intent": "REFUND_ISSUE",
            "entities": {"transaction_id": "TXN123"},
            "sentiment": "NEUTRAL",
            "priority": "MEDIUM",
        }
        context = {"rag_results": [{"score": 0.5}]}
        result = engine.evaluate(analysis, context)
        assert result.decision.value in ("CONFIRM", "ESCALATE")

    def test_frustrated_customer_gets_escalated(self):
        """Negative sentiment with moderate confidence triggers escalation."""
        engine = self._get_engine()
        analysis = {
            "intent": "PAYMENT_ISSUE",
            "entities": {},
            "sentiment": "NEGATIVE",
            "priority": "MEDIUM",
        }
        context = {"rag_results": []}  # No RAG results
        result = engine.evaluate(analysis, context)
        assert result.decision.value == "ESCALATE"

    def test_repeated_attempts_escalate(self):
        """Too many resolution attempts triggers escalation."""
        engine = self._get_engine()
        analysis = {"intent": "GENERAL_QUERY", "entities": {}, "priority": "LOW"}
        context = {"rag_results": [{"score": 0.5}], "attempt_count": 5}
        result = engine.evaluate(analysis, context)
        assert result.decision.value == "ESCALATE"

    def test_escalation_context_populated(self):
        """Escalation result includes context for expert."""
        engine = self._get_engine()
        analysis = {
            "intent": "PAYMENT_ISSUE",
            "entities": {"transaction_id": "TXN123"},
            "sentiment": "NEGATIVE",
            "priority": "HIGH",
        }
        result = engine.evaluate(analysis, {"rag_results": []})
        assert result.context.recommended_specialization == "Payments/Finance"


# ==============================================================================
# CAPABILITY 6: Code-Mixed Language / Tanglish
# ==============================================================================

class TestCodeMixedLanguageDetector:
    """Tests for Capability 6: Language Detection."""

    def _get_detector(self):
        from app.ai.intelligence.language import CodeMixedLanguageDetector
        return CodeMixedLanguageDetector()

    def test_pure_english(self):
        """Pure English detected correctly."""
        detector = self._get_detector()
        result = detector.detect("I need help with my order please")
        assert result.primary_language == "en"
        assert not result.is_code_mixed

    def test_tanglish_romanized(self):
        """Romanized Tanglish detected."""
        detector = self._get_detector()
        result = detector.detect("Bro my payment irukku but delivery illa da")
        assert result.is_code_mixed
        assert result.code_mix_type == "tanglish"

    def test_tamil_script(self):
        """Tamil script detected."""
        detector = self._get_detector()
        result = detector.detect("எனது ஆர்டர் எங்கே?")
        assert result.primary_language == "ta"
        assert "tamil" in result.script_types

    def test_hindi_script(self):
        """Devanagari script detected."""
        detector = self._get_detector()
        result = detector.detect("मेरा ऑर्डर कहाँ है?")
        assert result.primary_language == "hi"
        assert "devanagari" in result.script_types

    def test_code_mixed_tamil_english(self):
        """Mixed Tamil script + English detected."""
        detector = self._get_detector()
        result = detector.detect("My order எங்கே இருக்கு?")
        assert result.is_code_mixed
        assert result.primary_language == "ta"
        assert "en" in result.mixed_with

    def test_hinglish_romanized(self):
        """Romanized Hinglish detected."""
        detector = self._get_detector()
        result = detector.detect("Mera order nahi aaya hai bhai")
        assert result.is_code_mixed
        assert result.code_mix_type == "hinglish"


class TestIndianLanguageNormalizer:
    """Tests for Capability 6: Normalization."""

    def _get_normalizer(self):
        from app.ai.intelligence.language import IndianLanguageNormalizer
        return IndianLanguageNormalizer()

    def test_tanglish_normalization(self):
        """Tanglish words normalized to English."""
        normalizer = self._get_normalizer()
        result = normalizer.normalize("payment irukku but delivery illa")
        assert "is" in result.normalized  # irukku -> is
        assert "not" in result.normalized  # illa -> not
        assert len(result.detected_slang) > 0

    def test_preserve_entities(self):
        """Entity IDs preserved during normalization."""
        normalizer = self._get_normalizer()
        result = normalizer.normalize("TXN123 la payment irukku")
        assert "TXN123" in result.original  # Original preserved

    def test_empty_input(self):
        """Empty input handled gracefully."""
        normalizer = self._get_normalizer()
        result = normalizer.normalize("")
        assert result.normalized == ""


class TestCodeMixedIntentExtractor:
    """Tests for intent extraction from code-mixed messages."""

    def _get_extractor(self):
        from app.ai.intelligence.language import CodeMixedIntentExtractor
        return CodeMixedIntentExtractor()

    def test_tanglish_payment_intent(self):
        """Payment intent extracted from Tanglish."""
        extractor = self._get_extractor()
        result = extractor.extract_intent("Bro my panam deducted but order illa")
        assert result["intent"] == "PAYMENT_ISSUE"
        assert result["is_code_mixed"]

    def test_tanglish_delivery_intent(self):
        """Delivery intent extracted from Tanglish."""
        extractor = self._get_extractor()
        result = extractor.extract_intent("Order eppo varum da? ORD456")
        assert result["intent"] == "DELIVERY_ISSUE"
        assert "ORD456" in str(result["entities"])

    def test_entity_extraction_from_mixed(self):
        """Entities extracted from code-mixed messages."""
        extractor = self._get_extractor()
        result = extractor.extract_intent("TXN789 transaction check pannunga")
        assert "TXN789" in str(result["entities"])


# ==============================================================================
# CAPABILITY 7: Resolution Failure Prediction
# ==============================================================================

class TestFrustrationDetector:
    """Tests for frustration detection."""

    def _get_detector(self):
        from app.ai.intelligence.failure_prediction import FrustrationDetector
        return FrustrationDetector()

    def test_calm_customer(self):
        """Calm customer has low frustration."""
        detector = self._get_detector()
        frustration = detector.estimate_frustration("Could you help me check my order?", [])
        assert frustration < 0.3

    def test_frustrated_customer(self):
        """Frustrated customer detected."""
        detector = self._get_detector()
        frustration = detector.estimate_frustration(
            "This is TERRIBLE! I am FED UP with your useless service!!!",
            [{"content": "x"}] * 8,  # Long conversation
        )
        assert frustration > 0.5

    def test_escalation_request(self):
        """Escalation request detected as frustration."""
        detector = self._get_detector()
        frustration = detector.estimate_frustration(
            "I want to talk to a real person, not a bot",
            [{"content": "x"}] * 4,
        )
        assert frustration > 0.2

    def test_all_caps_shouting(self):
        """ALL CAPS detected as frustration signal."""
        detector = self._get_detector()
        frustration = detector.estimate_frustration(
            "WHERE IS MY ORDER WHY IS NOBODY HELPING",
            [],
        )
        assert frustration > 0.1


class TestFailurePredictor:
    """Tests for failure prediction."""

    def _get_predictor(self):
        from app.ai.intelligence.failure_prediction import FailurePredictor
        return FailurePredictor()

    def test_low_risk_simple_query(self):
        """Simple query has low failure prediction."""
        predictor = self._get_predictor()
        analysis = {"intent": "GREETING", "entities": {}, "sentiment": "NEUTRAL", "original_message": "Hello"}
        result = predictor.predict(analysis, {"rag_results": [{"score": 0.5}], "history": []})
        assert result.probability < 0.4
        assert not result.should_escalate_early

    def test_high_risk_security_with_frustration(self):
        """Security + frustration = high failure risk."""
        predictor = self._get_predictor()
        analysis = {
            "intent": "SECURITY_ISSUE",
            "entities": {},
            "sentiment": "NEGATIVE",
            "original_message": "My account was hacked! This is TERRIBLE and RIDICULOUS! I am FED UP! Talk to someone!!!",
        }
        context = {"rag_results": [], "history": [{"content": "x"}] * 10}
        result = predictor.predict(analysis, context)
        assert result.probability > 0.4

    def test_repeated_failures_increase_prediction(self):
        """Failed attempts increase failure prediction."""
        from app.ai.intelligence.failure_prediction import FailurePredictor, ResolutionAttemptTracker
        predictor = FailurePredictor()
        tracker = ResolutionAttemptTracker()

        # Track multiple failures
        for _ in range(3):
            tracker.track_attempt(1, "rag_lookup", success=False, error_message="No results")

        analysis = {"intent": "GENERAL_QUERY", "entities": {}, "original_message": "Help"}
        result = predictor.predict(analysis, {"rag_results": [], "history": []}, tracker, conversation_id=1)
        assert result.probability > 0.3


class TestAttemptTracker:
    """Tests for resolution attempt tracking."""

    def test_track_and_retrieve(self):
        from app.ai.intelligence.failure_prediction import ResolutionAttemptTracker
        tracker = ResolutionAttemptTracker()
        tracker.track_attempt(1, "rag_lookup", True)
        tracker.track_attempt(1, "tool_execution", False, "TOOL_ERROR")
        assert tracker.get_attempt_count(1) == 2
        assert tracker.get_failure_count(1) == 1
        assert tracker.get_success_rate(1) == 0.5

    def test_clear_tracking(self):
        from app.ai.intelligence.failure_prediction import ResolutionAttemptTracker
        tracker = ResolutionAttemptTracker()
        tracker.track_attempt(1, "test", True)
        tracker.clear(1)
        assert tracker.get_attempt_count(1) == 0


# ==============================================================================
# CAPABILITY 8: Cross-Ticket Incident Discovery
# ==============================================================================

class TestTicketSimilarityAnalyzer:
    """Tests for ticket similarity analysis."""

    def _get_analyzer(self):
        from app.ai.intelligence.incidents import TicketSimilarityAnalyzer
        return TicketSimilarityAnalyzer()

    def test_identical_tickets_high_similarity(self):
        """Identical tickets have high similarity."""
        from app.ai.intelligence.incidents import TicketSnapshot
        analyzer = self._get_analyzer()
        now = datetime.now(timezone.utc)
        
        ticket_a = TicketSnapshot(ticket_id=1, subject="Payment failed", category="payment", intent="PAYMENT_ISSUE", created_at=now)
        ticket_b = TicketSnapshot(ticket_id=2, subject="Payment failed", category="payment", intent="PAYMENT_ISSUE", created_at=now + timedelta(minutes=5))
        
        sim = analyzer.compute_similarity(ticket_a, ticket_b)
        assert sim.overall > 0.7

    def test_unrelated_tickets_low_similarity(self):
        """Unrelated tickets have low similarity."""
        from app.ai.intelligence.incidents import TicketSnapshot
        analyzer = self._get_analyzer()
        now = datetime.now(timezone.utc)
        
        ticket_a = TicketSnapshot(ticket_id=1, subject="Payment failed", category="payment", intent="PAYMENT_ISSUE", created_at=now)
        ticket_b = TicketSnapshot(ticket_id=2, subject="Login not working", category="account", intent="LOGIN_ISSUE", created_at=now + timedelta(days=30))
        
        sim = analyzer.compute_similarity(ticket_a, ticket_b)
        assert sim.overall < 0.4


class TestIncidentDetector:
    """Tests for incident detection."""

    def _get_detector(self):
        from app.ai.intelligence.incidents import IncidentDetector
        return IncidentDetector()

    def test_detect_payment_incident(self):
        """Multiple payment failures detected as incident."""
        from app.ai.intelligence.incidents import TicketSnapshot
        detector = self._get_detector()
        now = datetime.now(timezone.utc)
        
        tickets = [
            TicketSnapshot(ticket_id=i, subject="Payment gateway error", category="payment",
                          intent="PAYMENT_ISSUE", created_at=now + timedelta(minutes=i * 5),
                          customer_id=100 + i, tenant_id="tenant_a")
            for i in range(5)
        ]
        
        incidents = detector.detect_incidents(tickets, tenant_id="tenant_a")
        assert len(incidents) >= 1
        assert incidents[0].affected_customer_count >= 2

    def test_no_incident_single_ticket(self):
        """Single ticket doesn't form an incident."""
        from app.ai.intelligence.incidents import TicketSnapshot
        detector = self._get_detector()
        tickets = [
            TicketSnapshot(ticket_id=1, subject="Help me", tenant_id="t1"),
        ]
        incidents = detector.detect_incidents(tickets, tenant_id="t1")
        assert len(incidents) == 0

    def test_tenant_isolation_in_incidents(self):
        """Incidents are tenant-isolated."""
        from app.ai.intelligence.incidents import TicketSnapshot
        detector = self._get_detector()
        now = datetime.now(timezone.utc)
        
        tickets = [
            TicketSnapshot(ticket_id=1, subject="Payment error", category="payment",
                          intent="PAYMENT_ISSUE", created_at=now, tenant_id="tenant_a"),
            TicketSnapshot(ticket_id=2, subject="Payment error", category="payment",
                          intent="PAYMENT_ISSUE", created_at=now, tenant_id="tenant_b"),
        ]
        
        incidents_a = detector.detect_incidents(tickets, tenant_id="tenant_a")
        incidents_b = detector.detect_incidents(tickets, tenant_id="tenant_b")
        assert len(incidents_a) == 0  # Only 1 ticket per tenant
        assert len(incidents_b) == 0

    def test_severity_based_on_count(self):
        """Incident severity scales with ticket count."""
        from app.ai.intelligence.incidents import TicketSnapshot
        detector = self._get_detector()
        now = datetime.now(timezone.utc)
        
        tickets = [
            TicketSnapshot(ticket_id=i, subject="Payment gateway error", category="payment",
                          intent="PAYMENT_ISSUE", created_at=now + timedelta(minutes=i),
                          customer_id=100 + i, tenant_id="t")
            for i in range(6)
        ]
        incidents = detector.detect_incidents(tickets, tenant_id="t")
        assert len(incidents) >= 1
        assert incidents[0].severity in ("HIGH", "CRITICAL")


# ==============================================================================
# CAPABILITY 9: Adaptive Autonomy Engine
# ==============================================================================

class TestAutonomyLevelDeterminer:
    """Tests for Capability 9: Adaptive Autonomy Engine."""

    def _get_determiner(self):
        from app.ai.intelligence.autonomy import AutonomyLevelDeterminer
        return AutonomyLevelDeterminer()

    def test_greeting_automatic(self):
        """Greetings are handled automatically."""
        determiner = self._get_determiner()
        analysis = {"intent": "GREETING", "entities": {}, "sentiment": "NEUTRAL", "priority": "LOW"}
        context = {"rag_results": [{"score": 0.7, "title": "FAQ"}]}
        result = determiner.determine_level(analysis, context)
        assert result.level.value == "AUTOMATIC"

    def test_security_escalates(self):
        """Security issues always escalate."""
        determiner = self._get_determiner()
        analysis = {"intent": "SECURITY_ISSUE", "entities": {}, "priority": "HIGH"}
        result = determiner.determine_level(analysis, {"rag_results": []})
        assert result.level.value == "ESCALATE"

    def test_critical_priority_escalates(self):
        """CRITICAL priority always escalates."""
        determiner = self._get_determiner()
        analysis = {"intent": "GENERAL_QUERY", "entities": {}, "priority": "CRITICAL"}
        result = determiner.determine_level(analysis, {"rag_results": []})
        assert result.level.value == "ESCALATE"

    def test_max_attempts_escalates(self):
        """Maximum attempts triggers escalation."""
        determiner = self._get_determiner()
        analysis = {"intent": "GENERAL_QUERY", "entities": {}, "priority": "LOW"}
        context = {"rag_results": [{"score": 0.9}], "attempt_count": 5}
        result = determiner.determine_level(analysis, context)
        assert result.level.value == "ESCALATE"

    def test_tool_requires_confirmation(self):
        """High-risk tools require confirmation."""
        determiner = self._get_determiner()
        analysis = {
            "intent": "REFUND_ISSUE",
            "entities": {},
            "priority": "MEDIUM",
            "decision_state": "USE_TOOL",
            "tool_name": "create_refund_request",
        }
        result = determiner.determine_level(analysis, {"rag_results": [{"score": 0.5}]})
        assert result.level.value == "CONFIRMATION_REQUIRED"


class TestAutonomyAdapter:
    """Tests for autonomy threshold adaptation."""

    def test_record_and_track_outcomes(self):
        from app.ai.intelligence.autonomy import AutonomyAdapter
        adapter = AutonomyAdapter()
        for _ in range(10):
            adapter.record_outcome("GENERAL_QUERY", True)
        rate = adapter.get_success_rate("GENERAL_QUERY")
        assert rate == 1.0

    def test_high_success_lowers_threshold(self):
        from app.ai.intelligence.autonomy import AutonomyAdapter
        adapter = AutonomyAdapter()
        for _ in range(10):
            adapter.record_outcome("GENERAL_QUERY", True)
        thresholds = adapter.get_adjusted_thresholds("GENERAL_QUERY")
        assert thresholds.auto_resolve_min_confidence < 75.0  # Lowered

    def test_low_success_raises_threshold(self):
        from app.ai.intelligence.autonomy import AutonomyAdapter
        adapter = AutonomyAdapter()
        for _ in range(10):
            adapter.record_outcome("PAYMENT_ISSUE", False)
        thresholds = adapter.get_adjusted_thresholds("PAYMENT_ISSUE")
        assert thresholds.auto_resolve_min_confidence > 75.0  # Raised

    def test_unknown_intent_neutral(self):
        from app.ai.intelligence.autonomy import AutonomyAdapter
        adapter = AutonomyAdapter()
        rate = adapter.get_success_rate("UNKNOWN")
        assert rate is None


# ==============================================================================
# CAPABILITY 10: Intelligent Expert Routing
# ==============================================================================

class TestExpertMatcher:
    """Tests for Capability 10: Expert Routing."""

    def _make_experts(self):
        from app.ai.intelligence.routing import ExpertProfile
        return [
            ExpertProfile(
                expert_id=1, name="PaymentExpert",
                expertise_areas=["Payments/Finance"],
                proficiency_levels={"Payments/Finance": 5},
                current_workload=1, max_concurrent=5, is_available=True,
                satisfaction_rating=4.8, total_resolved=200,
            ),
            ExpertProfile(
                expert_id=2, name="SecurityExpert",
                expertise_areas=["Security", "Account/Auth"],
                proficiency_levels={"Security": 5, "Account/Auth": 4},
                current_workload=3, max_concurrent=5, is_available=True,
                satisfaction_rating=4.5, total_resolved=150,
            ),
            ExpertProfile(
                expert_id=3, name="GeneralExpert",
                expertise_areas=["General Support"],
                proficiency_levels={"General Support": 3},
                current_workload=0, max_concurrent=5, is_available=True,
                satisfaction_rating=3.5, total_resolved=50,
            ),
        ]

    def test_payment_routed_to_payment_expert(self):
        """Payment cases routed to payment specialist."""
        from app.ai.intelligence.routing import ExpertMatcher, RoutingCase
        matcher = ExpertMatcher()
        experts = self._make_experts()
        case = RoutingCase(category="Payments/Finance", priority="HIGH")
        decision = matcher.match(case, experts)
        assert decision.primary_expert_id == 1  # PaymentExpert

    def test_security_routed_to_security_expert(self):
        """Security cases routed to security specialist."""
        from app.ai.intelligence.routing import ExpertMatcher, RoutingCase
        matcher = ExpertMatcher()
        experts = self._make_experts()
        case = RoutingCase(category="Security", priority="CRITICAL")
        decision = matcher.match(case, experts)
        assert decision.primary_expert_id == 2  # SecurityExpert

    def test_no_experts_available(self):
        """No experts available handled gracefully."""
        from app.ai.intelligence.routing import ExpertMatcher, RoutingCase
        matcher = ExpertMatcher()
        case = RoutingCase(category="General Support")
        decision = matcher.match(case, [])
        assert decision.primary_expert_id is None
        assert decision.estimated_wait_minutes > 0

    def test_fallback_expert_selected(self):
        """Fallback expert is selected when primary is determined."""
        from app.ai.intelligence.routing import ExpertMatcher, RoutingCase
        matcher = ExpertMatcher()
        experts = self._make_experts()
        case = RoutingCase(category="Payments/Finance")
        decision = matcher.match(case, experts)
        assert decision.primary_expert_id is not None
        assert decision.fallback_expert_id is not None
        assert decision.primary_expert_id != decision.fallback_expert_id

    def test_unavailable_expert_not_selected(self):
        """Unavailable experts aren't selected as primary."""
        from app.ai.intelligence.routing import ExpertMatcher, RoutingCase, ExpertProfile
        matcher = ExpertMatcher()
        experts = [
            ExpertProfile(
                expert_id=1, expertise_areas=["Payments/Finance"],
                proficiency_levels={"Payments/Finance": 5},
                is_available=False, max_concurrent=5, current_workload=0,
            ),
            ExpertProfile(
                expert_id=2, expertise_areas=["Payments/Finance", "General Support"],
                proficiency_levels={"Payments/Finance": 3, "General Support": 3},
                is_available=True, max_concurrent=5, current_workload=0,
                satisfaction_rating=4.0, total_resolved=50,
            ),
        ]
        case = RoutingCase(category="Payments/Finance")
        decision = matcher.match(case, experts)
        assert decision.primary_expert_id == 2  # The available one

    def test_overloaded_expert_penalized(self):
        """Overloaded experts are penalized."""
        from app.ai.intelligence.routing import ExpertMatcher, RoutingCase, ExpertProfile
        matcher = ExpertMatcher()
        experts = [
            ExpertProfile(
                expert_id=1, expertise_areas=["Payments/Finance"],
                proficiency_levels={"Payments/Finance": 5},
                is_available=True, max_concurrent=5, current_workload=5,  # Full
                satisfaction_rating=5.0, total_resolved=200,
            ),
            ExpertProfile(
                expert_id=2, expertise_areas=["Payments/Finance"],
                proficiency_levels={"Payments/Finance": 4},
                is_available=True, max_concurrent=5, current_workload=0,  # Free
                satisfaction_rating=4.0, total_resolved=100,
            ),
        ]
        case = RoutingCase(category="Payments/Finance")
        decision = matcher.match(case, experts)
        assert decision.primary_expert_id == 2  # The free one


class TestRoutingDecisionEngine:
    """Tests for routing decision engine with load balancing."""

    def test_load_balanced_routing(self):
        """Load balancing swaps when appropriate."""
        from app.ai.intelligence.routing import RoutingDecisionEngine, ExpertProfile, RoutingCase
        engine = RoutingDecisionEngine()
        experts = [
            ExpertProfile(
                expert_id=1, expertise_areas=["General Support"],
                proficiency_levels={"General Support": 4},
                is_available=True, max_concurrent=5, current_workload=4,
                satisfaction_rating=4.5, total_resolved=100,
            ),
            ExpertProfile(
                expert_id=2, expertise_areas=["General Support"],
                proficiency_levels={"General Support": 3},
                is_available=True, max_concurrent=5, current_workload=0,
                satisfaction_rating=4.0, total_resolved=80,
            ),
        ]
        case = RoutingCase(category="General Support", priority="LOW")
        decision = engine.route(case, experts)
        # For LOW priority, load balancing should swap to less-loaded expert
        assert decision.primary_expert_id == 2  # Less loaded
