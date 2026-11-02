import re
from typing import Dict, Any, Tuple

class LanguageDetector:
    def __init__(self):
        from app.ai.intelligence.language import CodeMixedLanguageDetector
        self._detector = CodeMixedLanguageDetector()

    def detect(self, text: str) -> str:
        """
        Detects English, Tamil, Tanglish, Hindi, Hinglish, and Indic languages.
        Returns the detected language code or code-mix type.
        """
        if not text:
            return "en"
        res = self._detector.detect(text)
        if res.is_code_mixed and res.code_mix_type in ("tanglish", "hinglish"):
            return res.code_mix_type
        if res.primary_language in ("ta", "hi", "kn", "te", "bn", "ml"):
            return res.primary_language
        return "en"

class IntentClassifier:
    def __init__(self):
        from app.ai.intelligence.language import UniversalMeaningEngine
        self._engine = UniversalMeaningEngine()

    def classify(self, text: str) -> str:
        """
        Classifies intent into DELIVERY_ISSUE, PAYMENT_ISSUE, PAYMENT_CONFIRMATION,
        REFUND_ISSUE, REFUND_RECEIVED, LOGIN_ISSUE, SECURITY_ISSUE, ESCALATION_REQUEST, etc.
        """
        from app.ai.intelligence.escalation_keywords import is_supervisor_demand, is_fraud_or_security

        if is_supervisor_demand(text):
            return "ESCALATION_REQUEST"
        if is_fraud_or_security(text):
            return "SECURITY_ISSUE"

        u = self._engine.understand_utterance(text)
        if u.intent and u.intent not in ("UNKNOWN", ""):
            return u.intent

        return "GENERAL_QUERY"

class SentimentAnalyzer:
    def __init__(self):
        from app.ai.intelligence.language import UniversalMeaningEngine
        self._engine = UniversalMeaningEngine()

    def analyze(self, text: str) -> str:
        """
        Classifies sentiment as POSITIVE, NEUTRAL, NEGATIVE across English,
        Tamil, Tanglish, Hindi, and Hinglish with negation awareness.
        """
        text_lower = text.lower()
        
        # Check communication style from UniversalMeaningEngine
        style = self._engine.detect_communication_style(text)
        style_sent = style.get("sentiment", "neutral").upper()
        if style_sent in ("POSITIVE", "NEGATIVE", "FRUSTRATED"):
            return "NEGATIVE" if style_sent == "FRUSTRATED" else style_sent

        # Multilingual positive and negative tokens
        negative_words = [
            'fail', 'failed', 'error', 'wrong', 'bad', 'terrible', 'stolen', 'hack', 'angry',
            'upset', 'late', 'deducted', 'kashtam', 'erichal', 'kovam', 'thala vali', 'waste',
            'bakwas', 'dikkat', 'kharab', 'mosam', 'மோசம்', 'பிரச்சனை', 'தவறு'
        ]
        positive_words = [
            'good', 'great', 'thanks', 'thank you', 'awesome', 'resolved', 'nandri', 'magizhchi',
            'shukriya', 'dhanyawad', 'badhiya', 'super', 'நன்றி', 'மகிழ்ச்சி'
        ]
        
        neg_count = sum(1 for word in negative_words if word in text_lower)
        pos_count = sum(1 for word in positive_words if word in text_lower)
        
        # Negation check: e.g. "not working" -> negative, "not bad" -> positive/neutral
        is_neg = self._engine.detect_negation(text)
        if is_neg and pos_count > 0 and neg_count == 0:
            return "NEGATIVE"
        if is_neg and "not bad" in text_lower:
            return "POSITIVE"

        if neg_count > pos_count:
            return "NEGATIVE"
        if pos_count > neg_count:
            return "POSITIVE"
        return "NEUTRAL"

class EntityExtractor:
    def __init__(self):
        from app.ai.intelligence.language import UniversalMeaningEngine
        self._engine = UniversalMeaningEngine()

    def extract(self, text: str) -> Dict[str, Any]:
        """
        Extracts entities like order IDs, transaction IDs, amounts, and ticket IDs.
        """
        return self._engine.extract_entities(text)
