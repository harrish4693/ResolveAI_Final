"""
ResolveAIV2 — Multilingual Conversational Emotion & Tone Analyzer

Estimates customer conversational states:
- Frustrated: Acknowledge problem empathetically, remain calm, focus on next action.
- Confused: Simplify explanation, ask one clear question at a time.
- Urgent: Prioritize immediate next step with crisp, swift assistance.
- Calm: Friendly, natural, efficient conversational flow.
- Satisfied: Warm closing / next-step confirmation.
- Uncertain: Explain what is known clearly and what must be verified.

Supports English, Tanglish (Tamil-English), and Hinglish (Hindi-English).
"""

from __future__ import annotations

import re
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class EmotionState(str, Enum):
    FRUSTRATED = "frustrated"
    CONFUSED = "confused"
    URGENT = "urgent"
    CALM = "calm"
    SATISFIED = "satisfied"
    UNCERTAIN = "uncertain"

# Convenient alias
CustomerEmotion = EmotionState


@dataclass
class EmotionAnalysisResult:
    primary_emotion: str = EmotionState.CALM.value
    confidence: float = 0.85
    signals: List[str] = field(default_factory=list)
    conversational_guidance: str = ""
    prosody_rate: float = 1.0
    prosody_pitch: float = 1.0


class ConversationalEmotionAnalyzer:
    """
    Fast multilingual emotion and conversational state detector.
    Analyzes lexical patterns, punctuation intensity, repetition markers,
    and history context to provide grounded emotion estimates.
    """

    FRUSTRATION_KEYWORDS = {
        "frustrated", "frustrating", "frustration", "irritated", "angry", "annoyed",
        "worst", "waste", "horrible", "terrible", "useless", "pathetic", "ridiculous",
        "scam", "cheat", "cheating", "bad experience", "money gone", "deducted but",
        # Tanglish / Tamil markers
        "kaduppu", "romba frustrating", "tholla", "kashtam", "waste ah irukku",
        "aagalaya", "panam pochu", "aiyo", "mudiyala", "enna bro idhu",
        "thirumba thirumba", "already tried", "solli solli", "yen ipdi",
        # Hinglish / Hindi markers
        "bakwas", "kharab", "pareshan", "pareshani", "gussa", "kitni baar",
        "lut gaye", "bekaar", "dhoka", "pehle bhi bola tha", "thak gaya",
    }

    CONFUSION_KEYWORDS = {
        "confused", "confusing", "confusion", "don't understand", "not understanding",
        "what do you mean", "unclear", "lost", "how does this work",
        # Tanglish
        "puriyala", "enna solreenga", "therila", "eppadi pannrathu", "doubt ah irukku",
        "konjam explain pannunga", "clarity illa",
        # Hinglish
        "samajh nahi aaya", "kaise kare", "samajh nahi aa raha", "kya matlab",
        "pata nahi chal raha",
    }

    URGENCY_KEYWORDS = {
        "urgent", "urgently", "emergency", "immediately", "right now", "asap",
        "travel tomorrow", "flight tomorrow", "deadline", "today itself", "hurry",
        # Tanglish
        "seekiram", "udane", "urgent ah venum", "ippove", "naalaikku flight",
        "avasiyam", "konjam speed ah",
        # Hinglish
        "jaldi", "turant", "abhi ke abhi", "aaj hi", "emergency hai", "kal travel hai",
    }

    SATISFACTION_KEYWORDS = {
        "thank you", "thanks", "great", "awesome", "perfect", "resolved",
        "working now", "helped a lot", "appreciate it", "good job",
        # Tanglish
        "nandri", "super bro", "romba nandri", "correct ah aayiduchu", "working bro",
        # Hinglish
        "shukriya", "dhanyawad", "theek ho gaya", "badhiya", "bahut accha",
    }

    UNCERTAINTY_KEYWORDS = {
        "maybe", "not sure", "might be", "perhaps", "i guess", "probably",
        # Tanglish
        "sandhegam", "therilaye", "irukkalam", "apdi nu nenaikren",
        # Hinglish
        "shayad", "pakka nahi", "lagta hai", "ho sakta hai",
    }

    @classmethod
    def analyze(
        cls,
        text: str,
        history: Optional[List[Dict[str, Any]]] = None,
        attempt_count: int = 0,
        repeated_failure: bool = False,
    ) -> EmotionAnalysisResult:
        """
        Estimates conversational state from current turn and context.
        """
        clean = text.lower().strip()
        signals = []

        # 1. Punctuation intensity
        exclamation_count = clean.count("!")
        question_count = clean.count("?")
        if exclamation_count >= 2:
            signals.append("high_exclamation_intensity")
        if question_count >= 2:
            signals.append("multiple_question_marks")

        # 2. Check for repeated solution / attempt signals
        has_repeated_effort = (
            attempt_count >= 2
            or repeated_failure
            or "already tried" in clean
            or "thirumba" in clean
            or "pehle bhi" in clean
            or "again and again" in clean
        )
        if has_repeated_effort:
            signals.append("repeated_failed_attempt")

        # 3. Match keyword sets
        frustration_hits = [k for k in cls.FRUSTRATION_KEYWORDS if k in clean]
        confusion_hits = [k for k in cls.CONFUSION_KEYWORDS if k in clean]
        urgency_hits = [k for k in cls.URGENCY_KEYWORDS if k in clean]
        satisfaction_hits = [k for k in cls.SATISFACTION_KEYWORDS if k in clean]
        uncertainty_hits = [k for k in cls.UNCERTAINTY_KEYWORDS if k in clean]

        if frustration_hits:
            signals.extend(f"frustration:{h}" for h in frustration_hits[:3])
        if confusion_hits:
            signals.extend(f"confusion:{h}" for h in confusion_hits[:3])
        if urgency_hits:
            signals.extend(f"urgency:{h}" for h in urgency_hits[:3])
        if satisfaction_hits:
            signals.extend(f"satisfaction:{h}" for h in satisfaction_hits[:3])
        if uncertainty_hits:
            signals.extend(f"uncertainty:{h}" for h in uncertainty_hits[:3])

        # 4. Determine primary emotion with prioritization
        # Frustration with repeated effort is highest priority
        if frustration_hits or has_repeated_effort:
            emotion = EmotionState.FRUSTRATED.value
            confidence = min(0.70 + (len(frustration_hits) * 0.1) + (0.15 if has_repeated_effort else 0), 0.96)
            guidance = (
                "Customer is frustrated. Acknowledge their issue warmly before proposing actions. "
                "Remain calm, empathetic, and patient. Never argue, blame, or dismiss. Focus on next step."
            )
            prosody_rate = 0.98
            prosody_pitch = 1.0

        elif urgency_hits:
            emotion = EmotionState.URGENT.value
            confidence = min(0.75 + (len(urgency_hits) * 0.1), 0.95)
            guidance = (
                "Customer has an urgent concern. Prioritize the immediate next step. "
                "Keep response crisp, clear, and reassuring."
            )
            prosody_rate = 1.05
            prosody_pitch = 1.02

        elif confusion_hits or (question_count >= 2 and len(clean.split()) < 8):
            emotion = EmotionState.CONFUSED.value
            confidence = min(0.70 + (len(confusion_hits) * 0.1), 0.92)
            guidance = (
                "Customer is confused. Simplify explanation, avoid jargon, and ask only ONE clear question at a time."
            )
            prosody_rate = 0.95
            prosody_pitch = 1.0

        elif uncertainty_hits:
            emotion = EmotionState.UNCERTAIN.value
            confidence = min(0.65 + (len(uncertainty_hits) * 0.1), 0.88)
            guidance = (
                "Customer is uncertain. Clarify what is known and specify what needs checking."
            )
            prosody_rate = 0.98
            prosody_pitch = 1.0

        elif satisfaction_hits:
            emotion = EmotionState.SATISFIED.value
            confidence = min(0.75 + (len(satisfaction_hits) * 0.1), 0.95)
            guidance = (
                "Customer is satisfied. Provide a warm, polite confirmation or check if they need anything else."
            )
            prosody_rate = 1.02
            prosody_pitch = 1.0

        else:
            emotion = EmotionState.CALM.value
            confidence = 0.85
            guidance = (
                "Customer is calm. Maintain a helpful, friendly, natural conversational tone."
            )
            prosody_rate = 1.02
            prosody_pitch = 1.0

        return EmotionAnalysisResult(
            primary_emotion=emotion,
            confidence=round(confidence, 2),
            signals=signals,
            conversational_guidance=guidance,
            prosody_rate=prosody_rate,
            prosody_pitch=prosody_pitch,
        )
