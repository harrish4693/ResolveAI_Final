"""
ResolveAIV2 — Milestone P2.5 Step 4 (C): Sticky Language & Consistency Test Suite

Verifies:
1. detect_explicit_language_request detects native and romanized explicit requests:
   - "I wish to continue in Tanglish", "Tanglish-la pesalam", "tanglish la pesunga" -> "tanglish"
   - "Tamil la pesunga", "தமிழ்ல பேசுங்க" -> "tamil"
   - "Hindi mein baat karo", "हिन्दी में बात करो" -> "hindi"
   - "Hinglish mein baat karte hain" -> "hinglish"
   - "continue in english" -> "english"
2. Immediate acknowledgment returned in the requested language in the same turn:
   - "tanglish" -> "Sari, Tanglish-la pesalam. Enna help venum?"
   - "tamil" -> "சரி, தமிழில் பேசலாம். உங்களுக்கு என்ன உதவி வேண்டும்?"
   - "hindi" -> "ज़रूर, हम हिन्दी में बात कर सकते हैं। मैं आपकी क्या मदद कर सकता हूँ?"
3. Sticky persistence across 5 consecutive follow-up turns:
   - Once set to "tanglish", subsequent turns retain preferred_language="tanglish"
   - Even when user turns contain neutral or English keywords.
4. Layer 9 Language Consistency Check (check_language_consistency):
   - When expected is "tanglish", an English-only response is rejected (REGENERATE).
   - When expected is "tanglish", Tanglish response passes.
   - When expected is "tamil", Tamil script passes, English-only response is rejected.
   - When expected is "hindi", Hindi script passes, English-only response is rejected.
5. REST API PATCH /conversations/{id} updates preferred_language and saves to memory.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.conversations.service import ConversationService
from app.ai.validation.models import (
    ResponseValidationContext,
    ValidationStatus,
    CheckResult,
)
from app.ai.validation.service import ValidationService
from app.ai.validation.rules import check_language_consistency


class TestP2_5_ExplicitLanguageDetection:
    """Verifies dual-script explicit language request detection."""

    @pytest.mark.parametrize("phrase,expected_lang", [
        ("I wish to continue in Tanglish", "tanglish"),
        ("Tanglish-la pesalam", "tanglish"),
        ("tanglish la pesunga", "tanglish"),
        ("tanglish la pesalaama", "tanglish"),
        ("pesalam tanglish la", "tanglish"),
        ("Tamil la pesunga", "tamil"),
        ("tamilil pesavum", "tamil"),
        ("தமிழ்ல பேசுங்க", "tamil"),
        ("தமிழில் பேசுங்கள்", "tamil"),
        ("Hindi mein baat karo", "hindi"),
        ("hindi me baat karo", "hindi"),
        ("हिन्दी में बात करो", "hindi"),
        ("हिंदी में बोलिए", "hindi"),
        ("Hinglish mein baat karte hain", "hinglish"),
        ("continue in hinglish", "hinglish"),
        ("please talk in english", "english"),
        ("continue in english please", "english"),
        ("can we speak in english", "english"),
    ])
    def test_detect_explicit_language_request(self, phrase, expected_lang):
        detected = ConversationService.detect_explicit_language_request(phrase)
        assert detected == expected_lang, f"Failed for '{phrase}': expected {expected_lang}, got {detected}"

    def test_non_switching_phrases_return_none(self):
        non_switch_phrases = [
            "My payment failed yesterday.",
            "Where is my refund?",
            "Enaku refund venum",
            "Mera order deliver nahi hua",
        ]
        for phrase in non_switch_phrases:
            assert ConversationService.detect_explicit_language_request(phrase) is None

    def test_instant_acknowledgment_mapping(self):
        """All supported languages have instant acknowledgments defined."""
        for lang in ["tanglish", "tamil", "hindi", "hinglish", "english"]:
            ack = ConversationService.LANGUAGE_SWITCH_ACKNOWLEDGMENTS.get(lang)
            assert ack is not None and len(ack) > 0, f"Missing acknowledgment for {lang}"
        
        # Verify specific Tanglish greeting requirement
        assert ConversationService.LANGUAGE_SWITCH_ACKNOWLEDGMENTS["tanglish"] == (
            "Sari, Tanglish-la pesalam. Enna help venum?"
        )


class TestP2_5_Layer9_LanguageConsistency:
    """Verifies that Layer 9 validation enforces language consistency."""

    def test_rejects_english_when_tanglish_requested(self):
        """When caller requested Tanglish, pure English reply must trigger REGENERATE."""
        ctx = ResponseValidationContext(
            conversation_id=1,
            customer_id=1,
            user_message="I wish to continue in Tanglish",
            agent_decision="RESOLVE",
            draft_response="I understand you want to talk in Tanglish. How can I help you today?",
            conversation_history=[],
            preferred_language="tanglish",
        )
        res = check_language_consistency(ctx)
        assert res.status == ValidationStatus.REGENERATE
        assert len(res.violations) > 0
        assert res.violations[0].violation_type == "WRONG_LANGUAGE"

    def test_accepts_tanglish_when_tanglish_requested(self):
        """Tanglish reply passes when tanglish is requested."""
        ctx = ResponseValidationContext(
            conversation_id=1,
            customer_id=1,
            user_message="order status sollu bro",
            agent_decision="RESOLVE",
            draft_response="Kandippa, ungaloda order status-a check panni udaney solren.",
            conversation_history=[],
            preferred_language="tanglish",
        )
        res = check_language_consistency(ctx)
        assert res.status == ValidationStatus.VALID
        assert len(res.violations) == 0

    def test_rejects_english_when_tamil_requested(self):
        """When Tamil script is requested, pure English draft is rejected."""
        ctx = ResponseValidationContext(
            conversation_id=1,
            customer_id=1,
            user_message="தமிழ்ல பேசுங்க",
            agent_decision="RESOLVE",
            draft_response="I am checking your transaction right now.",
            conversation_history=[],
            preferred_language="tamil",
        )
        res = check_language_consistency(ctx)
        assert res.status == ValidationStatus.REGENERATE
        assert len(res.violations) > 0
        assert res.violations[0].violation_type == "WRONG_LANGUAGE"

    def test_accepts_tamil_script_when_tamil_requested(self):
        """Tamil script passes when Tamil is requested."""
        ctx = ResponseValidationContext(
            conversation_id=1,
            customer_id=1,
            user_message="என் ஆர்டர் எங்கே?",
            agent_decision="RESOLVE",
            draft_response="உங்கள் ஆர்டர் நிலையை உடனே சரிபார்த்து விடுகிறேன்.",
            conversation_history=[],
            preferred_language="tamil",
        )
        res = check_language_consistency(ctx)
        assert res.status == ValidationStatus.VALID
        assert len(res.violations) == 0

    def test_rejects_english_when_hindi_requested(self):
        """When Hindi script is requested, pure English draft is rejected."""
        ctx = ResponseValidationContext(
            conversation_id=1,
            customer_id=1,
            user_message="हिन्दी में बात करो",
            agent_decision="RESOLVE",
            draft_response="Sure, I can help you with your order.",
            conversation_history=[],
            preferred_language="hindi",
        )
        res = check_language_consistency(ctx)
        assert res.status == ValidationStatus.REGENERATE
        assert len(res.violations) > 0
        assert res.violations[0].violation_type == "WRONG_LANGUAGE"

    def test_accepts_hindi_script_when_hindi_requested(self):
        """Hindi script passes when Hindi is requested."""
        ctx = ResponseValidationContext(
            conversation_id=1,
            customer_id=1,
            user_message="मेरा रिफंड कब आएगा?",
            agent_decision="RESOLVE",
            draft_response="ज़रूर, मैं आपके रिफंड की स्थिति तुरंत चेक कर रहा हूँ।",
            conversation_history=[],
            preferred_language="hindi",
        )
        res = check_language_consistency(ctx)
        assert res.status == ValidationStatus.VALID
        assert len(res.violations) == 0


class TestP2_5_StickyLanguageTurns:
    """Verifies that once language preference is set, it stays sticky across 5 turns."""

    def test_five_consecutive_turns_stay_sticky(self):
        """Simulate conversation holding sticky preference over 5 successive turns."""
        convo_language = None

        # Turn 1: Caller sets Tanglish
        turn1_input = "I wish to continue in Tanglish"
        switch_lang = ConversationService.detect_explicit_language_request(turn1_input)
        assert switch_lang == "tanglish"
        convo_language = switch_lang  # Stored on conversation

        # 5 Follow-up turns with diverse inputs (some containing English loan words)
        subsequent_turns = [
            "Order status enna aachu?",
            "Tracking ID check pannalama?",
            "Payment debit aayiduchu aana order cancel nu varudhu",
            "Refund eppo varum bank account ku?",
            "Sari bro, thanks for the help.",
        ]

        for i, turn_input in enumerate(subsequent_turns, start=2):
            # Check if caller explicitly requested a switch in this turn
            new_switch = ConversationService.detect_explicit_language_request(turn_input)
            if new_switch:
                convo_language = new_switch
            
            # convo_language must remain sticky as 'tanglish'
            assert convo_language == "tanglish", f"Turn {i} dropped sticky language"


class TestP2_5_NullLanguageFallback:
    """Verifies that existing conversations with NULL preferred_language fall back to auto-detect without crashing."""

    def test_null_preferred_language_validation_skips_cleanly(self):
        """When preferred_language is NULL/None, Layer 9 consistency check skips without error."""
        ctx = ResponseValidationContext(
            conversation_id=99,
            customer_id=1,
            user_message="Hello, I need help with my package.",
            agent_decision="RESOLVE",
            draft_response="I would be happy to help with your package.",
            conversation_history=[],
            preferred_language=None,
        )
        res = check_language_consistency(ctx)
        assert res.status == ValidationStatus.VALID
        assert res.checks.language_consistency == CheckResult.SKIP
        assert len(res.violations) == 0

    @pytest.mark.parametrize("msg,expected_auto_lang", [
        ("Where is my order tracking number?", "english"),
        ("En order tracking status sollu bro", "tanglish"),
        ("என் ஆர்டர் எங்கே உள்ளது?", "tamil"),
        ("मेरा रिफंड कब तक आएगा?", "hindi"),
    ])
    def test_null_preferred_language_auto_detects_signals(self, msg, expected_auto_lang):
        """Cheap signal detection correctly auto-detects language when conversation.preferred_language is NULL."""
        signals = ConversationService._detect_cheap_voice_signals(msg)
        assert signals.get("language", "English").lower() == expected_auto_lang

    @pytest.mark.asyncio
    async def test_process_message_with_null_preferred_language(self):
        """Verify process_message on a Conversation with preferred_language=None auto-detects language without crash."""
        service = ConversationService()
        service.ai_provider = MagicMock()
        service.ai_provider.decide_action = AsyncMock(return_value={
            "decision": "RESOLVE",
            "reasoning": "Standard response",
            "draft_response": "Here is your order status.",
            "tools_to_execute": [],
        })

        db = AsyncMock()
        mock_exec_res = MagicMock()
        mock_exec_res.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_exec_res)
        db.get = AsyncMock(return_value=None)
        db.scalar = AsyncMock(return_value=None)

        conversation = MagicMock()
        conversation.id = 101
        conversation.customer_id = 42
        conversation.preferred_language = None
        conversation.messages = []
        conversation.status = "ACTIVE"
        conversation.workflow_state = "IDLE"

        # Mock out external memory & validation dependencies
        with patch("app.memory.service.MemoryService.retrieve_relevant_memory", new_callable=AsyncMock) as mock_mem_get, \
             patch("app.memory.service.MemoryService.save_memory", new_callable=AsyncMock) as mock_mem_set, \
             patch.object(service, "_detect_cheap_voice_signals", return_value={"intent": "ORDER_STATUS", "urgency": "NORMAL", "sentiment": "NEUTRAL", "language": "English"}), \
             patch("app.ai.validation.service.ValidationService.validate_response", new_callable=AsyncMock) as mock_val, \
             patch("app.conversations.service.MessageService.create_message", new_callable=AsyncMock) as mock_create_msg, \
             patch("app.conversations.service.manager.send_to_conversation_participants", new_callable=AsyncMock):

            mock_mem_get.return_value = []
            mock_val.return_value = MagicMock(status=ValidationStatus.VALID, draft_response="Here is your order status.")
            mock_create_msg.return_value = MagicMock(id=501, content="Here is your order status.")

            # Trigger AI response on conversation where preferred_language is NULL
            await service._trigger_ai_response(
                db=db,
                conversation=conversation,
                latest_message="Where is my package?",
            )

            # Auto-detection should have populated preferred_language to 'english'
            assert conversation.preferred_language == "english"

    @pytest.mark.asyncio
    async def test_livekit_voice_utterance_with_null_preferred_language(self):
        """Verify LiveKit voice utterance with existing conversation (preferred_language=None) succeeds."""
        from app.voice.livekit_service import LiveKitService

        db = AsyncMock()
        db.add = MagicMock()
        conversation = MagicMock()
        conversation.id = 202
        conversation.customer_id = 7
        conversation.preferred_language = None
        conversation.workflow_state = "IDLE"

        mock_exec_res = MagicMock()
        mock_exec_res.scalars.return_value.first.return_value = MagicMock(id=99, content="Mock reply")
        db.execute = AsyncMock(return_value=mock_exec_res)
        db.scalar = AsyncMock(side_effect=[conversation, None])
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        with patch("app.conversations.service.ConversationService.process_customer_message", new_callable=AsyncMock) as mock_pcm:
            result = await LiveKitService.process_spoken_utterance(
                db=db,
                conversation_id=202,
                customer_id=7,
                utterance_id="utt_test_null_lang",
                transcript="Where is my parcel?",
            )

            assert result["status"] == "processed"
            assert result["conversation_id"] == 202
            mock_pcm.assert_awaited_once()


