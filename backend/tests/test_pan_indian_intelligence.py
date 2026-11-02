"""
ResolveAI V2 — Pan-Indian Multilingual Intelligence Engine Test Suite

Validates:
1. Complete 9-language core rollout coverage in both native script and Romanized code-mixing:
   - Tamil (ta, Tanglish)
   - Telugu (te, Telugu-English)
   - Kannada (kn, Kannada-English)
   - Malayalam (ml, Malayalam-English)
   - Hindi (hi, Hinglish)
   - Bengali (bn, Bengali-English)
   - Marathi (mr, Marathi-English)
   - Gujarati (gu, Gujarati-English)
   - Punjabi (pa, Punjabi-English)
2. Semantic Equivalence for Delivery Delays across all 9 languages.
3. Negation Inversion across all 9 languages (Payment completed vs failed, Refund received vs missing).
4. Cross-language Incident Clustering linking disparate Indian languages into unified incidents.
5. Multilingual RAG Retrieval retrieving English knowledge articles for non-English queries.
6. Decision Engine Autonomy preventing false escalations for routine multilingual queries.
7. Extensible Language Registry supporting Core (9) and Expanded (13) rollout tiers.
"""

import pytest
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.ai.intelligence.language import (
    LanguageRegistry,
    LanguageInfo,
    UniversalMeaningEngine,
    CodeMixedLanguageDetector,
    IndianLanguageNormalizer,
)
from app.ai.intelligence.multilingual_engine import (
    MultilingualEngineService,
    multilingual_service,
)
from app.ai.m4.decision import DecisionEngine, ResponseGenerator
from app.rag.models import KnowledgeArticle
from app.rag.retriever import TFIDFRetriever
from app.ai.intelligence.incidents import (
    TicketSnapshot,
    TicketSimilarityAnalyzer,
    IncidentDetector,
)


class TestLanguageRegistryAndExtensibility:
    """Verifies that the language registry supports all Core & Expanded tiers and dynamic additions."""

    def test_core_languages_coverage(self):
        core_languages = LanguageRegistry.list_core()
        core_codes = {lang.code for lang in core_languages}
        expected_core = {"ta", "te", "kn", "ml", "hi", "bn", "mr", "gu", "pa", "en"}
        assert expected_core.issubset(core_codes), (
            f"Missing core rollout languages: {expected_core - core_codes}"
        )

    def test_expanded_languages_coverage(self):
        expanded_languages = LanguageRegistry.list_expanded()
        expanded_codes = {lang.code for lang in expanded_languages}
        expected_expanded = {
            "or", "as", "ur", "ks", "kok", "mni", "ne",
            "brx", "doi", "sa", "sat", "mai", "sd"
        }
        assert expected_expanded.issubset(expanded_codes), (
            f"Missing expanded rollout languages: {expected_expanded - expanded_codes}"
        )

    def test_dynamic_language_registration(self):
        """Validates that a new regional variety can be registered dynamically at runtime."""
        bhojpuri_info = LanguageInfo(
            code="bho",
            name="Bhojpuri",
            native_name="भोजपुरी",
            script="devanagari",
            code_mixed_name="bhojpuri_english",
            bcp47="bho-IN",
            family="Indo-Aryan",
            tier="expanded",
            supported_code_mixing=True,
        )
        LanguageRegistry.register(bhojpuri_info)
        fetched = LanguageRegistry.get("bho")
        assert fetched is not None
        assert fetched.name == "Bhojpuri"
        assert fetched.bcp47 == "bho-IN"


class TestPanIndianDeliveryEquivalence:
    """
    Evaluates delivery delay equivalence across ALL 9 core rollout languages
    in BOTH native script and Romanized code-mixed forms.
    All 18 variants must accurately map to DELIVERY_ISSUE, category 'delivery',
    and negation_detected=True.
    """

    @pytest.fixture(autouse=True)
    def setup_engine(self):
        self.service = MultilingualEngineService()

    @pytest.mark.parametrize(
        "language_name,phrase,expected_lang,is_code_mixed",
        [
            # 1. Tamil
            ("Tamil Script", "என் ஆர்டர் இன்னும் வரவில்லை", "ta", False),
            ("Tanglish", "En order innum varala bro", "ta", True),

            # 2. Telugu
            ("Telugu Script", "నా ఆర్డర్ ఇంకా రాలేదు", "te", False),
            ("Telugu-English", "Naa order inka raledu andi", "te", True),

            # 3. Kannada
            ("Kannada Script", "ನನ್ನ ಆರ್ಡರ್ ಇನ್ನೂ ಬಂದಿಲ್ಲ", "kn", False),
            ("Kannada-English", "Nanna order innu bandilla", "kn", True),

            # 4. Malayalam
            ("Malayalam Script", "എന്റെ ഓർഡർ ഇതുവരെ വന്നില്ല", "ml", False),
            ("Malayalam-English", "Ente order ithuvare vannilla", "ml", True),

            # 5. Hindi
            ("Hindi Script", "मेरा ऑर्डर अभी तक नहीं आया", "hi", False),
            ("Hinglish", "Mera order abhi tak nahi aaya bhai", "hi", True),

            # 6. Bengali
            ("Bengali Script", "আমার অর্ডার এখনো আসেনি", "bn", False),
            ("Bengali-English", "Amar order ekhono asheni", "bn", True),

            # 7. Marathi
            ("Marathi Script", "माझा ऑर्डर अजून आला नाही", "mr", False),
            ("Marathi-English", "Maza order ajun aala nahi", "mr", True),

            # 8. Gujarati
            ("Gujarati Script", "મારો ઓર્ડર હજી સુધી નથી આવ્યો", "gu", False),
            ("Gujarati-English", "Maro order haji sudhi nathi aavyo", "gu", True),

            # 9. Punjabi
            ("Punjabi Script", "ਮੇਰਾ ਆਰਡਰ ਅਜੇ ਤੱਕ ਨਹੀਂ ਆਇਆ", "pa", False),
            ("Punjabi-English", "Mera order aje tak nahi aaya", "pa", True),
        ],
    )
    def test_delivery_delay_equivalence_across_9_languages(
        self, language_name, phrase, expected_lang, is_code_mixed
    ):
        understanding = self.service.understand(phrase)
        assert understanding.intent == "DELIVERY_ISSUE", (
            f"Failed intent for {language_name} ('{phrase}'): got {understanding.intent}"
        )
        assert understanding.category == "delivery", (
            f"Failed category for {language_name} ('{phrase}'): got {understanding.category}"
        )
        assert understanding.negation_detected is True, (
            f"Failed negation_detected for {language_name} ('{phrase}'): expected True"
        )
        assert understanding.primary_language == expected_lang, (
            f"Failed primary_language for {language_name} ('{phrase}'): expected {expected_lang}, got {understanding.primary_language}"
        )
        search_query = understanding.normalized_search_query.lower()
        assert "delivery" in search_query or "order" in search_query, (
            f"Normalized search query does not contain delivery/order for '{phrase}': '{search_query}'"
        )


class TestPanIndianNegationInversion:
    """
    Evaluates negation inversion across all 9 core rollout languages:
    1. Payment completed (positive confirmation: negation=False, intent=PAYMENT_CONFIRMATION)
    2. Payment failed / not done (issue: negation=True, intent=PAYMENT_ISSUE)
    3. Refund received (positive confirmation: negation=False, intent=REFUND_RECEIVED)
    4. Refund missing (issue: negation=True, intent=REFUND_ISSUE)
    """

    @pytest.fixture(autouse=True)
    def setup_engine(self):
        self.service = MultilingualEngineService()

    @pytest.mark.parametrize(
        "lang_code,positive_phrase,negative_phrase",
        [
            ("ta", "Payment panniten", "Payment pannala"),
            ("te", "Payment chesanu", "Payment cheyaledu"),
            ("kn", "Payment maadiddini", "Payment madilla"),
            ("ml", "Payment cheythu", "Payment cheythilla"),
            ("hi", "Payment kar diya", "Payment nahi kiya"),
            ("bn", "Payment korechi", "Payment korini"),
            ("mr", "Payment kela", "Payment kela nahi"),
            ("gu", "Payment kari didhu", "Payment nathi karyu"),
            ("pa", "Payment kar ditta", "Payment nahi kita"),
        ],
    )
    def test_payment_negation_inversion_all_languages(
        self, lang_code, positive_phrase, negative_phrase
    ):
        # 1. Positive payment confirmation
        u_pos = self.service.understand(positive_phrase)
        assert u_pos.negation_detected is False, (
            f"Expected negation=False for '{positive_phrase}', got {u_pos.negation_detected}"
        )
        assert u_pos.intent == "PAYMENT_CONFIRMATION", (
            f"Expected PAYMENT_CONFIRMATION for '{positive_phrase}', got {u_pos.intent}"
        )
        assert u_pos.category == "payment"

        # 2. Negative payment issue
        u_neg = self.service.understand(negative_phrase)
        assert u_neg.negation_detected is True, (
            f"Expected negation=True for '{negative_phrase}', got {u_neg.negation_detected}"
        )
        assert u_neg.intent == "PAYMENT_ISSUE", (
            f"Expected PAYMENT_ISSUE for '{negative_phrase}', got {u_neg.intent}"
        )
        assert u_neg.category == "payment"

    @pytest.mark.parametrize(
        "lang_code,received_phrase,missing_phrase",
        [
            ("ta", "Refund vandhuduchu", "Refund varala"),
            ("te", "Refund vachindi", "Refund raledu"),
            ("kn", "Refund banthu", "Refund bandilla"),
            ("ml", "Refund vannu", "Refund vannilla"),
            ("hi", "Refund mil gaya", "Refund nahi mila"),
            ("bn", "Refund peyechi", "Refund asheni"),
            ("mr", "Refund milaala", "Refund aala nahi"),
            ("gu", "Refund mali gayo", "Refund nathi malyo"),
            ("pa", "Refund mil gaya", "Refund nahi milya"),
        ],
    )
    def test_refund_negation_inversion_all_languages(
        self, lang_code, received_phrase, missing_phrase
    ):
        # 1. Positive refund received
        u_rec = self.service.understand(received_phrase)
        assert u_rec.negation_detected is False, (
            f"Expected negation=False for '{received_phrase}', got {u_rec.negation_detected}"
        )
        assert u_rec.intent == "REFUND_RECEIVED", (
            f"Expected REFUND_RECEIVED for '{received_phrase}', got {u_rec.intent}"
        )
        assert u_rec.category == "refund"

        # 2. Missing refund issue
        u_mis = self.service.understand(missing_phrase)
        assert u_mis.negation_detected is True, (
            f"Expected negation=True for '{missing_phrase}', got {u_mis.negation_detected}"
        )
        assert u_mis.intent == "REFUND_ISSUE", (
            f"Expected REFUND_ISSUE for '{missing_phrase}', got {u_mis.intent}"
        )
        assert u_mis.category == "refund"


class TestPanIndianCrossLanguageIncidentClustering:
    """
    Validates cross-ticket incident discovery clustering tickets submitted in
    different Indian languages (e.g. Telugu, Bengali, Tamil, Marathi, Hindi).
    """

    def test_cluster_five_different_languages_into_same_incident(self):
        now = datetime.now(timezone.utc)
        analyzer = TicketSimilarityAnalyzer()

        t_telugu = TicketSnapshot(
            ticket_id=101,
            subject="Naa order inka raledu",
            category="delivery",
            intent="DELIVERY_ISSUE",
            created_at=now,
            customer_id=1001,
            tenant_id="tenant_india",
        )
        t_bengali = TicketSnapshot(
            ticket_id=102,
            subject="আমার অর্ডার এখনো আসেনি",
            category="delivery",
            intent="DELIVERY_ISSUE",
            created_at=now,
            customer_id=1002,
            tenant_id="tenant_india",
        )
        t_marathi = TicketSnapshot(
            ticket_id=103,
            subject="माझा ऑर्डर अजून आला नाही",
            category="delivery",
            intent="DELIVERY_ISSUE",
            created_at=now,
            customer_id=1003,
            tenant_id="tenant_india",
        )
        t_tamil = TicketSnapshot(
            ticket_id=104,
            subject="En order innum varala bro",
            category="delivery",
            intent="DELIVERY_ISSUE",
            created_at=now,
            customer_id=1004,
            tenant_id="tenant_india",
        )
        t_hindi = TicketSnapshot(
            ticket_id=105,
            subject="Mera order abhi tak nahi aaya",
            category="delivery",
            intent="DELIVERY_ISSUE",
            created_at=now,
            customer_id=1005,
            tenant_id="tenant_india",
        )

        tickets = [t_telugu, t_bengali, t_marathi, t_tamil, t_hindi]

        # Pairwise similarity check
        score_te_bn = analyzer.compute_similarity(t_telugu, t_bengali)
        assert score_te_bn.overall >= IncidentDetector.SIMILARITY_THRESHOLD, (
            f"Expected Telugu & Bengali tickets to exceed threshold {IncidentDetector.SIMILARITY_THRESHOLD}, got {score_te_bn.overall}"
        )

        score_ta_mr = analyzer.compute_similarity(t_tamil, t_marathi)
        assert score_ta_mr.overall >= IncidentDetector.SIMILARITY_THRESHOLD, (
            f"Expected Tamil & Marathi tickets to exceed threshold {IncidentDetector.SIMILARITY_THRESHOLD}, got {score_ta_mr.overall}"
        )

        detector = IncidentDetector()
        hypotheses = detector.detect_incidents(tickets, tenant_id="tenant_india")
        assert len(hypotheses) >= 1, "Expected at least 1 clustered incident hypothesis across languages"
        
        all_affected = set()
        for h in hypotheses:
            all_affected.update(h.affected_tickets)

        assert {101, 102, 103, 104, 105}.issubset(all_affected), (
            f"Expected all 5 language tickets to be clustered into incident, got affected tickets: {all_affected}"
        )


class TestPanIndianMultilingualRAGRetrieval:
    """
    Validates that queries in any of the 9 core rollout languages successfully
    retrieve English knowledge articles through canonical search expansion.
    """

    @pytest.mark.asyncio
    async def test_indic_queries_retrieve_english_delivery_policy(self, db_session: AsyncSession):
        tenant = "rag_multilingual_tenant"

        # Clean prior test tenant data
        await db_session.execute(
            delete(KnowledgeArticle).where(KnowledgeArticle.tenant_id == tenant)
        )
        await db_session.commit()

        # Seed English Knowledge Base Articles
        art_delivery = KnowledgeArticle(
            title="Standard Delivery & Shipping Timeline Policy",
            content="Orders are shipped within 2-4 business days. Track shipment status using order ID. Delayed deliveries are escalated to logistics.",
            category="delivery",
            tenant_id=tenant,
            is_active=True,
        )
        art_refund = KnowledgeArticle(
            title="Refund Processing & Bank Reversal Policy",
            content="Refunds are processed within 5-7 business days. If payment was deducted, check your bank statement or transaction reference.",
            category="refund",
            tenant_id=tenant,
            is_active=True,
        )
        db_session.add_all([art_delivery, art_refund])
        await db_session.commit()

        retriever = TFIDFRetriever()
        TFIDFRetriever.invalidate(tenant)
        await retriever.refresh(db_session, tenant_id=tenant)

        indic_delivery_queries = [
            "Naa order inka raledu tracking details kavali",      # Telugu
            "আমার অর্ডার এখনো আসেনি ডেলিভারি কবে হবে?",          # Bengali
            "Nanna order innu bandilla delivery yaavaga barutte", # Kannada
            "Ente order ithuvare vannilla delivery late aayi",    # Malayalam
            "माझा ऑर्डर अजून आला नाही डिलिव्हरी कधी होणार?",     # Marathi
            "Maro order haji sudhi nathi aavyo delivery kyare",   # Gujarati
            "Mera order aje tak nahi aaya delivery status",       # Punjabi
            "என் ஆர்டர் இன்னும் வரவில்லை டெலிவரி எப்போது?",      # Tamil
        ]

        for query in indic_delivery_queries:
            res = await retriever.search(query, db=db_session, top_k=2, tenant_id=tenant)
            assert res["status"] == "RAG_SUCCESS", f"RAG failed for query: '{query}'"
            assert len(res["results"]) > 0
            top_title = res["results"][0]["title"]
            assert "Delivery" in top_title or "Shipping" in top_title, (
                f"Expected delivery policy article for query '{query}', but got '{top_title}'"
            )


class TestPanIndianDecisionEngineAutonomy:
    """
    Validates autonomous handling across languages:
    - Routine delivery delay asks for Order ID via ASK_USER without false escalation.
    - Providing Order ID routes to tool execution or resolution.
    - Payment confirmation resolves via RESOLVE.
    - Supervisor demand escalates via ESCALATE.
    """

    @pytest.fixture(autouse=True)
    def setup_engines(self):
        self.decision_engine = DecisionEngine()
        self.response_generator = ResponseGenerator()
        self.service = MultilingualEngineService()

    def test_routine_delay_telugu_asks_user(self):
        u = self.service.understand("Naa order inka raledu")
        analysis = {
            "intent": u.intent,
            "category": u.category,
            "priority": "LOW",
            "entities": u.entities,
            "original_message": u.original_text,
            "diagnostic_details": u.diagnostic_details,
            "negation_detected": u.negation_detected,
        }
        decision = self.decision_engine.decide(analysis, [])
        assert decision["decision"] == "ASK_USER"
        assert decision["decision"] != "ESCALATE"

    def test_routine_delay_with_order_id_kannada_uses_tool(self):
        u = self.service.understand("Nanna order ORD-88123 innu bandilla")
        analysis = {
            "intent": u.intent,
            "category": u.category,
            "priority": "LOW",
            "entities": u.entities,
            "original_message": u.original_text,
            "diagnostic_details": u.diagnostic_details,
            "negation_detected": u.negation_detected,
        }
        decision = self.decision_engine.decide(analysis, [])
        assert decision["decision"] == "USE_TOOL"
        assert decision["tool_name"] == "get_order_status"
        assert decision["tool_args"]["order_id"] == "ORD-88123"

    def test_payment_confirmation_marathi_resolves(self):
        u = self.service.understand("Payment kela")
        analysis = {
            "intent": u.intent,
            "category": u.category,
            "priority": "LOW",
            "entities": u.entities,
            "original_message": u.original_text,
            "diagnostic_details": u.diagnostic_details,
            "negation_detected": u.negation_detected,
        }
        decision = self.decision_engine.decide(analysis, [])
        assert decision["decision"] == "RESOLVE"
        assert decision["decision"] != "ESCALATE"

    def test_supervisor_escalation_punjabi_escalates(self):
        u = self.service.understand("Mainu supervisor se baat karni hai")
        analysis = {
            "intent": u.intent,
            "category": u.category,
            "priority": "HIGH",
            "entities": u.entities,
            "original_message": u.original_text,
            "diagnostic_details": u.diagnostic_details,
            "negation_detected": u.negation_detected,
        }
        decision = self.decision_engine.decide(analysis, [])
        assert decision["decision"] == "ESCALATE"
