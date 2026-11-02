import pytest
from app.ai.intelligence.language import (
    UniversalMeaningEngine,
    UniversalMeaningUnderstanding,
    CodeMixedLanguageDetector,
    IndianLanguageNormalizer,
    CodeMixedIntentExtractor,
)
from app.ai.m4.provider import M4AIProvider


@pytest.fixture(autouse=True)
def setup_db():
    yield


@pytest.fixture
def engine():
    return UniversalMeaningEngine()


# ── 1. Morphological Negation Detection Tests ──

def test_negation_tanglish(engine):
    assert engine.detect_negation("app open aagala") is True
    assert engine.detect_negation("innum varala") is True
    assert engine.detect_negation("enala login panna mudiyala") is True
    assert engine.detect_negation("kaasu varave illa") is True
    assert engine.detect_negation("refund kedakkala") is True

    # Positive counterparts must NOT trigger negation
    assert engine.detect_negation("app open aayiduchu") is False
    assert engine.detect_negation("order vandhuruchu") is False
    assert engine.detect_negation("payment aagiduchu") is False


def test_negation_hinglish(engine):
    assert engine.detect_negation("app nahi khul raha") is True
    assert engine.detect_negation("paise wapas nahi mile") is True
    assert engine.detect_negation("order deliver nahi hua") is True

    # Positive counterparts
    assert engine.detect_negation("paise mil gaye") is False
    assert engine.detect_negation("app chal raha hai") is False


def test_negation_english(engine):
    assert engine.detect_negation("the app is not opening") is True
    assert engine.detect_negation("payment failed to process") is True
    assert engine.detect_negation("unable to reset password") is True

    # Positive counterparts
    assert engine.detect_negation("payment was successful") is False
    assert engine.detect_negation("app is working fine") is False


# ── 2. Generalization Across Support Categories & Code-Mixed Languages ──

def test_technical_issue_tanglish(engine):
    u = engine.understand_utterance("App open aagala bro")
    assert u.category == "technical"
    assert u.intent == "TECHNICAL_ISSUE"
    assert u.negation_detected is True
    assert u.diagnostic_details.get("symptom") == "launch_failure"


def test_technical_issue_frozen_screen(engine):
    u = engine.understand_utterance("screen mothama loading-laye nikkudhu")
    assert u.category == "technical"
    assert u.intent == "TECHNICAL_ISSUE"
    assert u.diagnostic_details.get("symptom") == "loading_freeze"


def test_technical_issue_tamil_script(engine):
    u = engine.understand_utterance("ஆப் கிராஷ் ஆகிறது")
    assert u.category == "technical"
    assert u.intent == "TECHNICAL_ISSUE"
    assert u.primary_language == "ta"
    assert u.detected_script == "tamil"


def test_payment_deduction_hinglish(engine):
    u = engine.understand_utterance("account se paise kat gaye par order nahi hua TXN-998811")
    assert u.category == "payment"
    assert u.intent == "PAYMENT_ISSUE"
    assert u.negation_detected is True
    assert "TXN-998811" in u.entities.get("transaction_id", "")


def test_delivery_late_tanglish(engine):
    u = engine.understand_utterance("order ORD-54321 innum varala eppo deliver aagum?")
    assert u.category == "delivery"
    assert u.intent == "DELIVERY_ISSUE"
    assert u.negation_detected is True
    assert "ORD-54321" in u.entities.get("order_id", "")


def test_refund_query_tanglish(engine):
    u = engine.understand_utterance("enakku refund panam thirumba varala bro")
    assert u.category == "refund"
    assert u.intent == "REFUND_ISSUE"
    assert u.negation_detected is True


def test_order_modification_tanglish(engine):
    u = engine.understand_utterance("delivery address change panna mudiyuma?")
    assert u.category == "order"
    assert u.intent == "ORDER_MANAGEMENT"


def test_login_issue_tanglish(engine):
    u = engine.understand_utterance("password maranthuten OTP innum varala")
    assert u.category == "account"
    assert u.intent == "LOGIN_ISSUE"
    assert u.negation_detected is True


def test_subscription_upgrade(engine):
    u = engine.understand_utterance("premium plan upgrade panna venum")
    assert u.category == "subscription"
    assert u.intent == "SUBSCRIPTION_ISSUE"


def test_warranty_replacement_claim(engine):
    u = engine.understand_utterance("product damage aagi vandhuruchu warranty replacement claim pannanum")
    assert u.category == "warranty"
    assert u.intent == "WARRANTY_SERVICE"


def test_supervisor_escalation(engine):
    u = engine.understand_utterance("manager kitta pesanum connect pannunga")
    assert u.category == "escalation"
    assert u.intent == "ESCALATION_REQUEST"


# ── 3. Opening Problem Statement vs Multi-Turn Context ──

def test_opening_problem_statement(engine):
    u = engine.understand_utterance("Enakku oru problem irukku")
    assert u.intent == "OPENING_PROBLEM_STATEMENT"
    assert u.clarification_needed is True
    assert u.is_ambiguous is True


def test_multi_turn_diagnostic_flow(engine):
    # Turn 1: Caller states vague problem
    u1 = engine.understand_utterance("Enakku oru problem irukku")
    assert u1.intent == "OPENING_PROBLEM_STATEMENT"

    # Agent responds with inquiry
    history = [
        {"sender_type": "customer", "content": "Enakku oru problem irukku"},
        {"sender_type": "ai", "content": "Seri, enna problem? Sollunga."},
    ]

    # Turn 2: Caller says "App open aagala"
    u2 = engine.understand_utterance("App open aagala", history=history)
    assert u2.intent == "TECHNICAL_ISSUE"
    assert u2.diagnostic_details.get("symptom") == "launch_failure"

    # Agent asks diagnostic follow-up
    history.extend([
        {"sender_type": "customer", "content": "App open aagala"},
        {"sender_type": "ai", "content": "Error message edhavadhu kaatutha, illa loading-laye nikkudha?"},
    ])

    # Turn 3: Caller gives short diagnostic answer "Loading-laye nikkudhu."
    u3 = engine.understand_utterance("Loading-laye nikkudhu.", history=history)
    assert u3.intent == "TECHNICAL_ISSUE"
    assert u3.diagnostic_details.get("symptom") == "loading_freeze"
    assert u3.diagnostic_details.get("is_follow_up") is True


# ── 4. Entity Extraction Accuracy ──

def test_entity_extraction(engine):
    text = "order ORD-99214 refund panam Rs. 750 innum varala transaction TXN-102938"
    entities = engine.extract_entities(text)
    assert entities.get("order_id") == "ORD-99214"
    assert entities.get("transaction_id") == "TXN-102938"
    assert entities.get("amount") == 750.0


# ── 5. M4 Voice Turn Provider Integration ──

@pytest.mark.asyncio
async def test_m4_voice_turn_opening_problem():
    m4 = M4AIProvider()
    res = await m4.process_voice_turn("Enakku oru problem irukku", {"history": []})
    assert res["intent"] == "OPENING_PROBLEM_STATEMENT"
    assert res["decision"] == "ASK_USER"
    assert "sollunga" in res["spoken_response"].lower() or "problem" in res["spoken_response"].lower()


@pytest.mark.asyncio
async def test_m4_voice_turn_app_launch_diagnostic():
    m4 = M4AIProvider()
    res = await m4.process_voice_turn("App open aagala", {"history": []})
    assert res["intent"] == "TECHNICAL_ISSUE"
    assert res["decision"] == "ASK_USER"
    assert res["negation_detected"] is True
    # Voice naturalness: no markdown, under 30 words
    assert "*" not in res["spoken_response"]
    assert len(res["spoken_response"].split()) <= 30


@pytest.mark.asyncio
async def test_m4_voice_turn_loading_freeze():
    m4 = M4AIProvider()
    history = [
        {"sender_type": "customer", "content": "App open aagala"},
        {"sender_type": "ai", "content": "Error message edhavadhu kaatutha, illa loading-laye nikkudha?"},
    ]
    res = await m4.process_voice_turn("Loading-laye nikkudhu.", {"history": history})
    assert res["intent"] == "TECHNICAL_ISSUE"
    assert res["decision"] == "ASK_USER"
    assert "cache" in res["spoken_response"].lower() or "restart" in res["spoken_response"].lower()
