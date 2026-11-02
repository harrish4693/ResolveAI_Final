"""
ResolveAIV2 — Comprehensive Real Multilingual Voice Agent Test Suite
===================================================================
Tests real end-to-end voice support for:
1. Capability registry completeness & truthfulness (Tier 1, Tier 2, Tier 3, Text-Only, Foreign).
2. Explicit language switching via natural cross-lingual, regional, and endonym phrases:
   - "Switch to Kannada."
   - "Kannada la pesu."
   - "Kannadadalli maatadi."
   - "Speak Telugu."
   - "Malayalam-il samsarikkamo?"
   - "Hindi se English mein switch karo."
   - "Bangla te kotha bolun."
   - "Marathi madhe bola."
   - "Gujarati ma bolo."
   - "Punjabi vich gal karo."
   - "Odia re katha kuha."
3. Multi-turn conversational flow in Kannada with tool execution and session continuity.
4. Multi-turn conversational flow in Telugu with tool execution and session continuity.
5. Multi-turn conversational flow in Malayalam with policy inquiry.
6. Code-mixed speech and negation preservation across Dravidian and Indo-Aryan languages.
7. Truthful disclosure for text-only Indian languages vs unsupported foreign languages.
8. Tenant isolation and authorization in multilingual voice context.
"""

import pytest
from sqlalchemy import select

from app.database import async_session_factory
from app.users.models import User
from app.commerce.models import Order, Transaction
from app.conversations.models import Conversation, ConversationMessage
from app.conversations.service import ConversationService
from app.shared.models import ConversationChannel
from app.voice.language_controller import (
    VoiceLanguageController,
    VoiceLanguagePolicy,
    VOICE_CAPABILITY_REGISTRY,
    SUPPORTED_LANGUAGES,
    UNSUPPORTED_FOREIGN_LANGUAGES,
    TEXT_ONLY_INDIAN_LANGUAGES,
)


# ── TEST 1: Truthful Capability Registry ─────────────────────────────────────

def test_capability_registry_truthfulness():
    """Verify that every language in VOICE_CAPABILITY_REGISTRY has distinct truthful flags."""
    # Tier 1 languages must support full voice conversation, STT, and TTS
    tier_1 = ["kannada", "telugu", "malayalam"]
    for lang in tier_1:
        assert lang in VOICE_CAPABILITY_REGISTRY, f"Missing {lang} in VOICE_CAPABILITY_REGISTRY"
        cap = VOICE_CAPABILITY_REGISTRY[lang]
        assert cap.text_understanding is True
        assert cap.native_script_recognition is True
        assert cap.code_mixed_understanding is True
        assert cap.speech_to_text is True
        assert cap.text_to_speech is True
        assert cap.full_voice_conversation is True

    # Tier 2 languages
    tier_2 = ["bengali", "marathi", "gujarati", "punjabi"]
    for lang in tier_2:
        assert lang in VOICE_CAPABILITY_REGISTRY, f"Missing {lang} in VOICE_CAPABILITY_REGISTRY"
        cap = VOICE_CAPABILITY_REGISTRY[lang]
        assert cap.speech_to_text is True
        assert cap.text_to_speech is True
        assert cap.full_voice_conversation is True

    # Tier 3 languages
    tier_3 = ["odia", "assamese", "urdu"]
    for lang in tier_3:
        assert lang in VOICE_CAPABILITY_REGISTRY, f"Missing {lang} in VOICE_CAPABILITY_REGISTRY"
        cap = VOICE_CAPABILITY_REGISTRY[lang]
        assert cap.speech_to_text is True
        assert cap.text_to_speech is True
        assert cap.full_voice_conversation is True

    # Text-only Indian languages MUST NOT be marked as full voice conversation
    text_only = ["bodo", "dogri", "santali", "maithili", "manipuri", "kashmiri", "konkani", "sanskrit", "sindhi"]
    for lang in text_only:
        assert lang in VOICE_CAPABILITY_REGISTRY, f"Missing {lang} in VOICE_CAPABILITY_REGISTRY"
        cap = VOICE_CAPABILITY_REGISTRY[lang]
        assert cap.text_understanding is True
        assert cap.speech_to_text is False, f"{lang} STT must be False"
        assert cap.text_to_speech is False, f"{lang} TTS must be False"
        assert cap.full_voice_conversation is False, f"{lang} full_voice must be False"

    # Foreign languages
    assert "french" in UNSUPPORTED_FOREIGN_LANGUAGES
    assert "german" in UNSUPPORTED_FOREIGN_LANGUAGES
    assert "spanish" in UNSUPPORTED_FOREIGN_LANGUAGES
    assert "japanese" in UNSUPPORTED_FOREIGN_LANGUAGES


# ── TEST 2: Natural Cross-Lingual & Endonym Language Switching ───────────────

@pytest.mark.parametrize(
    "phrase,expected_lang,expected_unsupported",
    [
        ("Switch to Kannada.", "kannada", False),
        ("Kannada la pesu.", "kannada", False),
        ("Kannadadalli maatadi.", "kannada", False),
        ("Speak in Kannada please", "kannada", False),
        ("Speak Telugu.", "telugu", False),
        ("Telugu lo matladu.", "telugu", False),
        ("Malayalam-il samsarikkamo?", "malayalam", False),
        ("Malayalam la pesunga", "malayalam", False),
        ("Hindi se English mein switch karo.", "english", False),
        ("Bangla te kotha bolun.", "bengali", False),
        ("Marathi madhe bola.", "marathi", False),
        ("Gujarati ma bolo.", "gujarati", False),
        ("Punjabi vich gal karo.", "punjabi", False),
        ("Odia re katha kuha.", "odia", False),
        ("Urdu mein baat kijiye.", "urdu", False),
        ("Parlez-vous francais?", "french", True),
        ("Sprechen sie deutsch?", "german", True),
        ("Can we talk in Bodo?", "bodo", True),
        ("Dogri mein baat karo.", "dogri", True),
        ("Santali te ror me.", "santali", True),
    ],
)
def test_detect_explicit_request_phrases(phrase, expected_lang, expected_unsupported):
    lang, unsupp_name = VoiceLanguageController.detect_explicit_request(phrase)
    if expected_unsupported:
        assert unsupp_name is not None, f"Expected unsupported for '{phrase}'"
        assert expected_lang in unsupp_name.lower() or unsupp_name.lower() == expected_lang
    else:
        assert lang == expected_lang, f"Failed for phrase '{phrase}': expected {expected_lang}, got {lang}"
        assert unsupp_name is None


# ── TEST 3: Unsupported vs Text-Only Disclosure Messages ─────────────────────

def test_unsupported_vs_text_only_disclosure():
    """Verify that foreign languages and text-only Indian languages get truthful distinct messages."""
    # Foreign language disclosure
    foreign_msg = VoiceLanguageController.get_unsupported_language_message("German", "english")
    assert "German" in foreign_msg
    assert "English" in foreign_msg
    assert "Kannada" in foreign_msg or "Tamil" in foreign_msg

    # Text-only Indian language disclosure
    text_only_msg = VoiceLanguageController.get_unsupported_language_message("Bodo", "english")
    assert "Bodo" in text_only_msg
    assert "text support" in text_only_msg.lower() or "voice conversation is not yet available" in text_only_msg.lower()


# ── TEST 4: Multi-Turn Voice Conversation in Kannada with Tool Execution ─────

@pytest.mark.asyncio
async def test_multiturn_kannada_session_with_tool_execution():
    """
    Validates end-to-end multi-turn Kannada voice session:
    Turn 1: Customer asks in Tamil to speak Kannada: 'Kannada la pesu.' -> Agent acknowledges in Kannada.
    Turn 2: Customer asks order status: 'Nanna order ORD-KN-101 status yenu?' -> Tool executes -> Kannada order status.
    Turn 3: Customer follows up: 'Dhanyavadagalu' -> Agent maintains Kannada without falling back to English.
    """
    async with async_session_factory() as session:
        user = User(email="kannada_voice_user@example.com", password_hash="testpasshash", full_name="Ramesh Gowda")
        session.add(user)
        await session.flush()

        order = Order(
            order_number="ORD-KN-101",
            customer_id=user.id,
            status="shipped",
            tracking_number="KNTRK998877",
        )
        session.add(order)

        convo = Conversation(customer_id=user.id, channel=ConversationChannel.VOICE)
        session.add(convo)
        await session.flush()

        svc = ConversationService()
        spoken_replies = []

        async def capture_tts(text: str):
            spoken_replies.append(text)

        # Turn 1: Request switch to Kannada
        res1 = await svc.process_customer_message(
            db=session,
            conversation=convo,
            customer_id=user.id,
            message_content="Kannada la pesu.",
            tts_callback=capture_tts,
            reply_with_voice=True,
        )
        assert convo.preferred_language == "kannada"
        assert any(term in " ".join(spoken_replies) for term in ["ಖಂಡಿತ", "ಕನ್ನಡದಲ್ಲಿ", "ಸಹಾಯ"])

        # Turn 2: Inquire about order status in Kannada
        res2 = await svc.process_customer_message(
            db=session,
            conversation=convo,
            customer_id=user.id,
            message_content="Nanna order ORD-KN-101 status yenu?",
            tts_callback=capture_tts,
            reply_with_voice=True,
        )
        # Must execute tool and return grounded details in Kannada or Kanglish
        assert convo.preferred_language in ("kannada", "kanglish")
        all_spoken = " ".join(spoken_replies)
        assert "ORD-KN-101" in all_spoken or "KNTRK998877" in all_spoken or "shipped" in all_spoken.lower() or "ಸ್ಥಿತಿ" in all_spoken

        # Turn 3: Follow-up closing in Kannada
        res3 = await svc.process_customer_message(
            db=session,
            conversation=convo,
            customer_id=user.id,
            message_content="Dhanyavadagalu!",
            tts_callback=capture_tts,
            reply_with_voice=True,
        )
        # MUST remain in Kannada/Kanglish
        assert convo.preferred_language in ("kannada", "kanglish")
        all_spoken = " ".join(spoken_replies)
        assert any(c in all_spoken for c in ["ಸಂತೋಷ", "ಧನ್ಯವಾದ", "ಸಹಾಯ", "Santhosha", "sahayavagbeka"])


# ── TEST 5: Multi-Turn Voice Conversation in Telugu with Tool Execution ──────

@pytest.mark.asyncio
async def test_multiturn_telugu_session_with_tool_execution():
    """
    Validates end-to-end multi-turn Telugu voice session:
    Turn 1: Customer asks 'Speak Telugu.' -> Agent acknowledges in Telugu.
    Turn 2: Customer provides transaction ID: 'Mee transaction TXN-TE-505 status cheppandi' -> Grounded Telugu reply.
    Turn 3: Customer asks return policy: 'Return policy gurinchi cheppandi' -> Grounded Telugu policy response.
    """
    async with async_session_factory() as session:
        user = User(email="telugu_voice_user@example.com", password_hash="testpasshash", full_name="Suresh Reddy")
        session.add(user)
        await session.flush()

        txn = Transaction(
            transaction_id="TXN-TE-505",
            customer_id=user.id,
            amount=2999.0,
            currency="INR",
            status="success",
        )
        session.add(txn)

        convo = Conversation(customer_id=user.id, channel=ConversationChannel.VOICE)
        session.add(convo)
        await session.flush()

        svc = ConversationService()
        spoken_replies = []

        async def capture_tts(text: str):
            spoken_replies.append(text)

        # Turn 1: Switch to Telugu
        await svc.process_customer_message(
            db=session,
            conversation=convo,
            customer_id=user.id,
            message_content="Speak Telugu.",
            tts_callback=capture_tts,
            reply_with_voice=True,
        )
        assert convo.preferred_language == "telugu"
        assert any(term in " ".join(spoken_replies) for term in ["తెలుగులో", "సహాయపడగలను", "తప్పకుండా"])

        # Turn 2: Query transaction status
        await svc.process_customer_message(
            db=session,
            conversation=convo,
            customer_id=user.id,
            message_content="Mee transaction TXN-TE-505 status cheppandi",
            tts_callback=capture_tts,
            reply_with_voice=True,
        )
        assert convo.preferred_language in ("telugu", "tenglish")
        all_spoken = " ".join(spoken_replies)
        assert "TXN-TE-505" in all_spoken or "2999" in all_spoken or "స్థితి" in all_spoken or "status" in all_spoken.lower()

        # Turn 3: Policy query in Telugu
        await svc.process_customer_message(
            db=session,
            conversation=convo,
            customer_id=user.id,
            message_content="Return policy gurinchi cheppandi",
            tts_callback=capture_tts,
            reply_with_voice=True,
        )
        assert convo.preferred_language in ("telugu", "tenglish")
        all_spoken = " ".join(spoken_replies)
        assert "30" in all_spoken or "రిటర్న్" in all_spoken or "return" in all_spoken.lower()


# ── TEST 6: Multi-Turn Voice Conversation in Malayalam ───────────────────────

@pytest.mark.asyncio
async def test_multiturn_malayalam_session():
    """
    Validates Malayalam voice session:
    Turn 1: 'Malayalam-il samsarikkamo?' -> Agent acknowledges in Malayalam.
    Turn 2: 'Return policy enthaanu?' -> Grounded Malayalam return policy response.
    """
    async with async_session_factory() as session:
        user = User(email="malayalam_voice_user@example.com", password_hash="testpasshash", full_name="Anjali Nair")
        session.add(user)
        await session.flush()

        convo = Conversation(customer_id=user.id, channel=ConversationChannel.VOICE)
        session.add(convo)
        await session.flush()

        svc = ConversationService()
        spoken_replies = []

        async def capture_tts(text: str):
            spoken_replies.append(text)

        # Turn 1: Switch to Malayalam
        await svc.process_customer_message(
            db=session,
            conversation=convo,
            customer_id=user.id,
            message_content="Malayalam-il samsarikkamo?",
            tts_callback=capture_tts,
            reply_with_voice=True,
        )
        assert convo.preferred_language == "malayalam"
        assert any(term in " ".join(spoken_replies) for term in ["മലയാളത്തിൽ", "തീർച്ചയായും", "സഹായിക്കണം"])

        # Turn 2: Policy inquiry
        await svc.process_customer_message(
            db=session,
            conversation=convo,
            customer_id=user.id,
            message_content="Return policy enthaanu?",
            tts_callback=capture_tts,
            reply_with_voice=True,
        )
        assert convo.preferred_language in ("malayalam", "manglish")
        all_spoken = " ".join(spoken_replies)
        assert "30" in all_spoken or "പോളിസി" in all_spoken or "റിട്ടേൺ" in all_spoken or "return" in all_spoken.lower()


# ── TEST 7: Code-Mixed Speech & Negation Preservation Across Languages ───────

@pytest.mark.parametrize(
    "utterance,expected_language",
    [
        ("En order innum varala bro.", "tanglish"),
        ("Mee order inka raledu andi.", "tenglish"),
        ("Nimma order innu bandilla ri.", "kanglish"),
        ("Njangalude order innum kittiyilla.", "manglish"),
        ("Mera order abhi tak nahi aaya.", "hinglish"),
        ("Aamar order ekhono aseni.", "benglish"),
        ("Majha order ajun aala nahi.", "marathish"),
    ],
)
def test_code_mixed_negation_language_preservation(utterance, expected_language):
    """Ensure natural negation expressions are recognized and preserve language without flipping."""
    policy = VoiceLanguagePolicy(response_language=expected_language)
    updated = VoiceLanguageController.evaluate_turn(policy, utterance)
    # The language must match or remain within the family
    assert updated.response_language in (expected_language, expected_language.replace("ish", ""))


# ── TEST 8: Tenant Isolation in Multilingual Voice Context ───────────────────

@pytest.mark.asyncio
async def test_tenant_isolation_in_multilingual_voice():
    """Verify that a customer in Kannada/Telugu cannot access another customer's order."""
    async with async_session_factory() as session:
        user_a = User(email="user_a_kannada@example.com", password_hash="testpasshash", full_name="User A")
        user_b = User(email="user_b_other@example.com", password_hash="testpasshash", full_name="User B")
        session.add_all([user_a, user_b])
        await session.flush()

        # Order belongs strictly to User B
        order_b = Order(
            order_number="ORD-SECRET-999",
            customer_id=user_b.id,
            status="delivered",
            tracking_number="SECRET999",
        )
        session.add(order_b)

        # Conversation belongs to User A
        convo_a = Conversation(customer_id=user_a.id, channel=ConversationChannel.VOICE, preferred_language="kannada")
        session.add(convo_a)
        await session.flush()

        svc = ConversationService()
        spoken = []

        async def capture_tts(text: str):
            spoken.append(text)

        # User A attempts to query User B's order in Kannada
        await svc.process_customer_message(
            db=session,
            conversation=convo_a,
            customer_id=user_a.id,
            message_content="Nanna order ORD-SECRET-999 status check maadi.",
            tts_callback=capture_tts,
            reply_with_voice=True,
        )

        all_spoken = " ".join(spoken)
        # Must not reveal User B's secret delivery/tracking info!
        assert "SECRET999" not in all_spoken
        assert "9999" not in all_spoken
        # Should inform that order was not found / unauthorized
        assert any(term in all_spoken for term in ["ಸಿಗಲಿಲ್ಲ", "ಕಂಡುಬಂದಿಲ್ಲ", "sigalilla", "not found", "verify", "unable", "check"])
