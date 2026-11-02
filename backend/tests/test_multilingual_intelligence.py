"""
ResolveAI V2 — Global Tamil & Tanglish Intelligence Engine Test Suite
Validates:
1. Meaning equivalence across Tamil script, Tanglish, and English
2. Accurate negation preservation (payment made vs not made, refund received vs not received)
3. Multilingual RAG retrieval (Tamil script and Tanglish queries retrieve English articles)
4. Cross-ticket incident clustering across languages
5. Autonomy & safe resolution of routine queries without false escalation
"""

import pytest
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.ai.intelligence.language import UniversalMeaningEngine, CodeMixedLanguageDetector
from app.ai.intelligence.multilingual_engine import MultilingualEngineService, multilingual_service
from app.ai.m4.analysis import LanguageDetector, IntentClassifier, SentimentAnalyzer, EntityExtractor
from app.ai.m4.decision import DecisionEngine, ResponseGenerator
from app.rag.models import KnowledgeArticle
from app.rag.retriever import TFIDFRetriever
from app.ai.intelligence.incidents import TicketSnapshot, TicketSimilarityAnalyzer, IncidentDetector


class TestLanguageUnderstandingAndEquivalence:
    """Requirement B & C: Universal semantic understanding across linguistic representations."""

    @pytest.fixture(autouse=True)
    def setup_engine(self):
        self.engine = UniversalMeaningEngine()
        self.service = MultilingualEngineService()

    def test_five_equivalent_delivery_phrases(self):
        """
        Equivalent delivery issues across Tamil script, Tanglish, informal slang,
        and English must all resolve to DELIVERY_ISSUE, category 'delivery',
        negation_detected=True, and generate an appropriate search query.
        """
        phrases = [
            "En order innum varala",
            "Order varave illa",
            "என் ஆர்டர் இன்னும் வரவில்லை",
            "My order has not arrived",
            "Parcel innum reach aagala",
        ]

        for phrase in phrases:
            understanding = self.service.understand(phrase)
            assert understanding.intent == "DELIVERY_ISSUE", (
                f"Failed intent equivalence for '{phrase}': got {understanding.intent}"
            )
            assert understanding.category == "delivery", (
                f"Failed category equivalence for '{phrase}': got {understanding.category}"
            )
            assert understanding.negation_detected is True, (
                f"Expected negation_detected=True for '{phrase}', got False"
            )
            assert "delivery" in understanding.normalized_search_query.lower() or "order" in understanding.normalized_search_query.lower(), (
                f"Expected delivery search query for '{phrase}', got '{understanding.normalized_search_query}'"
            )

    def test_payment_negation_inversion(self):
        """
        'Payment panniten' (payment completed; negation=False) vs
        'Payment pannala' (payment not made; negation=True).
        Must never mistake a completed payment for an issue/dispute.
        """
        # 1. Payment completed (positive confirmation)
        u_positive = self.service.understand("Payment panniten")
        assert u_positive.negation_detected is False
        assert u_positive.intent == "PAYMENT_CONFIRMATION"
        assert u_positive.category == "payment"

        # 2. Payment not done (negative issue)
        u_negative = self.service.understand("Payment pannala")
        assert u_negative.negation_detected is True
        assert u_negative.intent == "PAYMENT_ISSUE"
        assert u_negative.category == "payment"

    def test_refund_negation_inversion(self):
        """
        'Refund varala' (refund missing; negation=True) vs
        'Refund vandhuduchu' (refund arrived; negation=False).
        Must never escalate an already received refund to an expert.
        """
        # 1. Refund not arrived (dispute / inquiry)
        u_missing = self.service.understand("Refund varala")
        assert u_missing.negation_detected is True
        assert u_missing.intent == "REFUND_ISSUE"
        assert u_missing.category == "refund"

        # 2. Refund arrived (positive confirmation)
        u_received = self.service.understand("Refund vandhuduchu")
        assert u_received.negation_detected is False
        assert u_received.intent == "REFUND_RECEIVED"
        assert u_received.category == "refund"

    def test_tamil_script_and_tanglish_language_detection(self):
        """Validates primary_language and code_mix_type accuracy."""
        # Native Tamil script
        u_tamil = self.service.understand("என் ஆர்டர் எங்கே?")
        assert u_tamil.primary_language == "ta"
        assert u_tamil.detected_script == "tamil"

        # Tanglish (Latin characters)
        u_tanglish = self.service.understand("En order innum varala bro")
        assert u_tanglish.primary_language == "ta"
        assert u_tanglish.code_mix_type == "tanglish"
        assert u_tanglish.is_code_mixed is True

        # English
        u_en = self.service.understand("My package has not been delivered yet")
        assert u_en.primary_language == "en"
        assert u_en.detected_script == "latin"

    def test_informal_slang_and_urgency_detection(self):
        """Detects informal colloquial markers, urgency, and sentiment."""
        u_urgent = self.service.understand("Romba late aagudhu bro, seekiram delivery pannunga")
        assert u_urgent.intent == "DELIVERY_ISSUE"
        assert u_urgent.urgency == "urgent"
        assert u_urgent.communication_style.get("formality") == "informal"

        u_frustrated = self.service.understand("Suthama work aagala, waste of service")
        assert u_frustrated.sentiment == "NEGATIVE"

        u_positive = self.service.understand("Nandri bro, problem solve aayiduchu")
        assert u_positive.intent == "ACKNOWLEDGMENT"
        assert u_positive.sentiment == "POSITIVE"


class TestDecisionEngineAndAutonomy:
    """Requirement D & H: Decision engine handles Tamil/Tanglish queries without false escalations."""

    @pytest.fixture(autouse=True)
    def setup_engines(self):
        self.decision_engine = DecisionEngine()
        self.response_generator = ResponseGenerator()
        self.service = MultilingualEngineService()

    def test_routine_delivery_delay_asks_user_no_false_escalation(self):
        """
        'En order innum varala' with no Order ID must yield ASK_USER (asking for Order ID),
        NOT ESCALATE.
        """
        u = self.service.understand("En order innum varala")
        analysis = {
            "intent": u.intent,
            "category": u.category,
            "negation_detected": u.negation_detected,
            "entities": u.entities,
            "original_message": u.original_text,
            "priority": "MEDIUM",
        }
        decision = self.decision_engine.decide(analysis, retrieved_articles=[])
        assert decision["decision"] == "ASK_USER"
        assert decision.get("missing_entity") == "order_id"

        # Response generation in Tanglish
        response = self.response_generator.generate(decision, language="tanglish")
        assert "Order ID" in response or "order" in response.lower()

    def test_refund_received_resolves_without_escalation(self):
        """
        'Refund vandhuduchu, thanks bro' must RESOLVE with acknowledgment and NOT escalate.
        """
        u = self.service.understand("Refund vandhuduchu, thanks bro")
        analysis = {
            "intent": u.intent,
            "category": u.category,
            "negation_detected": u.negation_detected,
            "entities": u.entities,
            "original_message": u.original_text,
            "priority": "LOW",
        }
        decision = self.decision_engine.decide(analysis, retrieved_articles=[])
        assert decision["decision"] == "RESOLVE"
        assert decision.get("action_type") == "refund_received_acknowledgment"

        # Response generation in Tanglish
        response = self.response_generator.generate(decision, language="tanglish")
        assert "refund" in response.lower() or "magizhchi" in response.lower()

    def test_payment_confirmation_resolves_without_escalation(self):
        """
        'Payment panniten' must RESOLVE with payment confirmation and NOT ask for transaction ID as an error.
        """
        u = self.service.understand("Payment panniten")
        analysis = {
            "intent": u.intent,
            "category": u.category,
            "negation_detected": u.negation_detected,
            "entities": u.entities,
            "original_message": u.original_text,
            "priority": "LOW",
        }
        decision = self.decision_engine.decide(analysis, retrieved_articles=[])
        assert decision["decision"] == "RESOLVE"
        assert decision.get("action_type") == "payment_confirmation"

        response = self.response_generator.generate(decision, language="tanglish")
        assert "payment" in response.lower()


class TestMultilingualRAGRetrieval:
    """Requirement E: Multilingual RAG queries in Tamil script and Tanglish retrieving English articles."""

    @pytest.mark.asyncio
    async def test_tamil_and_tanglish_retrieve_english_knowledge_articles(self, db_session: AsyncSession):
        tenant_id = "test_multilingual_rag"
        retriever = TFIDFRetriever()
        retriever.invalidate(tenant_id)

        # Seed English knowledge base articles
        articles = [
            KnowledgeArticle(
                title="Delivery & Shipping Policy",
                content="Standard delivery takes 3 to 5 business days. Customers can track delayed orders using their Order ID.",
                category="delivery",
                tenant_id=tenant_id,
                is_active=True,
            ),
            KnowledgeArticle(
                title="Return and Refund Guidelines",
                content="Returns are accepted within 30 days of delivery. Refunds are credited back to original payment method in 5-7 business days.",
                category="refund",
                tenant_id=tenant_id,
                is_active=True,
            ),
        ]
        for a in articles:
            db_session.add(a)
        await db_session.flush()

        # Query 1: Pure Tamil script for delivery
        res_ta = await retriever.search("என் ஆர்டர் இன்னும் வரவில்லை", db_session, tenant_id=tenant_id)
        assert res_ta["status"] == "RAG_SUCCESS", f"Failed for Tamil script delivery: {res_ta}"
        assert len(res_ta["results"]) > 0
        assert res_ta["results"][0]["category"] == "delivery"

        # Query 2: Tanglish for delivery
        res_tanglish = await retriever.search("Order varave illa bro", db_session, tenant_id=tenant_id)
        assert res_tanglish["status"] == "RAG_SUCCESS", f"Failed for Tanglish delivery: {res_tanglish}"
        assert len(res_tanglish["results"]) > 0
        assert res_tanglish["results"][0]["category"] == "delivery"

        # Query 3: English for delivery
        res_en = await retriever.search("My order has not arrived", db_session, tenant_id=tenant_id)
        assert res_en["status"] == "RAG_SUCCESS", f"Failed for English delivery: {res_en}"
        assert len(res_en["results"]) > 0
        assert res_en["results"][0]["category"] == "delivery"

        # Clean up
        await db_session.execute(delete(KnowledgeArticle).where(KnowledgeArticle.tenant_id == tenant_id))
        await db_session.flush()
        retriever.invalidate(tenant_id)


class TestCrossTicketIncidentClustering:
    """Requirement D & H: Cross-ticket incident clustering across Tamil script, Tanglish, and English."""

    def test_cluster_tamil_tanglish_english_tickets(self):
        now = datetime.now(timezone.utc)
        analyzer = TicketSimilarityAnalyzer()

        t1 = TicketSnapshot(
            ticket_id=101,
            subject="Delivery delay: package not arrived",
            category="delivery",
            intent="DELIVERY_ISSUE",
            created_at=now,
            tenant_id="default",
            normalized_text="order delivery delay",
        )

        t2 = TicketSnapshot(
            ticket_id=102,
            subject="Order varave illa romba late aagudhu",
            category="delivery",
            intent="DELIVERY_ISSUE",
            created_at=now,
            tenant_id="default",
            normalized_text="order delivery delay innum varala",
        )

        t3 = TicketSnapshot(
            ticket_id=103,
            subject="என் ஆர்டர் இன்னும் வரவில்லை",
            category="delivery",
            intent="DELIVERY_ISSUE",
            created_at=now,
            tenant_id="default",
            normalized_text="டெலிவரி தாமதம்",
        )

        score_1_2 = analyzer.compute_similarity(t1, t2)
        score_1_3 = analyzer.compute_similarity(t1, t3)
        score_2_3 = analyzer.compute_similarity(t2, t3)

        # All pairwise similarities must exceed threshold
        threshold = IncidentDetector.SIMILARITY_THRESHOLD
        assert score_1_2.overall >= threshold, f"Score 1-2 was {score_1_2.overall}"
        assert score_1_3.overall >= threshold, f"Score 1-3 was {score_1_3.overall}"
        assert score_2_3.overall >= threshold, f"Score 2-3 was {score_2_3.overall}"


class TestExpandedMultilingualScenarios:
    """Requirement G: Versioned evaluation dataset covering login, ambiguity, STT variations, and provider flow."""

    @pytest.fixture(autouse=True)
    def setup_services(self):
        self.service = MultilingualEngineService()
        from app.ai.m4.provider import M4AIProvider
        self.provider = M4AIProvider()

    def test_login_and_auth_scenarios(self):
        """Validates account/login intent detection across languages."""
        # 1. Tanglish
        u_tanglish = self.service.understand("Password maranthuten pa, login aagala")
        assert u_tanglish.intent == "LOGIN_ISSUE"
        assert u_tanglish.category == "account"

        # 2. Tamil script
        u_tamil = self.service.understand("கடவுச்சொல் மறந்துவிட்டது, உள்நுழைய முடியவில்லை")
        assert u_tamil.intent == "LOGIN_ISSUE"
        assert u_tamil.category == "account"

    def test_ambiguous_opening_queries(self):
        """Vague problem statements must be flagged for clarification."""
        u_vague = self.service.understand("Enakku oru problem irukku")
        assert u_vague.intent == "OPENING_PROBLEM_STATEMENT"
        assert u_vague.is_ambiguous is True
        assert u_vague.clarification_needed is True

    def test_stt_transcription_informal_spellings(self):
        """Handles phonetic STT spelling variations cleanly."""
        # 'parsal' instead of 'parcel', 'inum' instead of 'innum'
        u_stt = self.service.understand("Parsal inum varala")
        assert u_stt.intent == "DELIVERY_ISSUE"
        assert u_stt.category == "delivery"
        assert u_stt.negation_detected is True

    def test_order_id_purpose_clarification(self):
        """When user asks why Order ID is needed, detects purpose clarification."""
        u_why = self.service.understand("Edhukku order id kekuringa?")
        assert u_why.intent == "CLARIFICATION_ORDER_ID_PURPOSE"
        assert u_why.category == "clarification"

    @pytest.mark.asyncio
    async def test_m4_provider_end_to_end_analyze_and_response(self, db_session: AsyncSession):
        """Ensures M4AIProvider preserves negation and normalized search query in analysis."""
        msg = "Order varave illa, parcel innum reach aagala"
        context = {
            "conversation_id": 999,
            "tenant_id": "test_m4_provider",
            "history": [],
        }
        analysis = await self.provider.analyze(msg, context, db=db_session)
        assert analysis["intent"] == "DELIVERY_ISSUE"
        assert analysis["category"] == "delivery"
        assert analysis["negation_detected"] is True
        assert "normalized_search_query" in analysis
        assert "delivery" in analysis["normalized_search_query"].lower()

