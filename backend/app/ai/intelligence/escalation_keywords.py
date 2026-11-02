"""
ResolveAIV2 — Milestone P1.7 Multilingual Escalation & Safety Keywords

Provides comprehensive keyword sets and validators for Tamil, Tanglish, Hindi, Hinglish,
and English to guarantee immediate mandatory human escalation on supervisor requests,
fraud, account compromise, and unauthorized transactions.
"""

import re
from typing import Any, List

# Supervisor / Human demand phrases across scripts and languages
MULTILINGUAL_SUPERVISOR_KEYWORDS: List[str] = [
    # English
    "speak to a human", "talk to a human", "i want to talk to a human", "talk to human",
    "connect me to an expert", "talk to an expert", "speak to an expert", "transfer to an expert",
    "connect to an expert", "connect me to expert", "speak with an expert", "human expert",
    "can i speak to a real person", "speak to a real person", "talk to a real person", "real person",
    "please transfer me to customer support", "transfer me to customer support", "transfer to customer support",
    "transfer to support", "customer support", "contact customer support", "connect to customer support",
    "human supervisor", "supervisor", "escalate this", "escalate to human", "escalate to supervisor",
    "human agent", "transfer to human", "connect me to a human", "talk to agent", "speak with agent",
    "call manager", "talk to manager", "customer care executive", "representative", "live agent",
    "human support", "human assistance", "human representative", "need a human", "want a human",

    # Tamil (native script)
    "மேற்பார்வையாளர்", "மேனேஜர்", "மனிதர்", "மனிதரிடம் பேசு", "மனிதரிடம் பேச", "மனிதரிடம்", "மனித ஏஜென்ட்",
    "மனித ஆதரவு வேண்டும்", "மனித ஏஜென்ட் வேண்டும்", "ஏஜென்ட்டுடன் இணைக்கவும்", "நிபுணரிடம் பேச வேண்டும்",
    "நேரடி அதிகாரி", "உயர் அதிகாரி", "மனிதரிடம் மாற்று", "அதிகாரியிடம் பேசு", "அதிகாரியிடம்",
    "வாடிக்கையாளர் சேவை", "உதவி மையம்",

    # Tanglish (Romanized Tamil)
    "agent kitta connect pannunga", "agent kitta connect pannu", "agent kitta pesanum",
    "enakku human support venum", "human support venum", "human agent venum", "manushan kitta pesanum",
    "human kitta connect pannunga", "human kitta connect pannu", "human kitta pesanum",
    "expert venum", "expert kitta connect pannunga", "expert kitta pesanum", "expert ta pesanum",
    "supervisor kitta", "manager kitta", "supervisor ta pesanum", "aalu kitta pesanum",
    "transfer to supervisor", "human venum", "supervisor kooda pesanum", "manager ta pesanum",
    "support kitta connect pannu", "support kitta connect pannunga",

    # Hindi (native script)
    "सुपरवाइजर", "मैनेजर", "इंसान से बात", "अधिकारी से बात", "मानव एजेंट",
    "सीनियर से बात", "प्रतिनिधि से बात", "कस्टमर केयर से बात", "इंसान से कनेक्ट करो",
    "मानव सहायता चाहिए", "इंसान से बात करनी है", "एजेंट से बात करनी है", "विशेषज्ञ से बात कराएं",
    "कस्टमर सपोर्ट से बात", "सपोर्ट टीम से बात",

    # Hinglish (Romanized Hindi)
    "mujhe human agent se baat karni hai", "agent se baat karni hai", "human agent chahiye",
    "expert se connect karo", "expert se baat karni hai", "expert chahiye", "kisi expert se baat",
    "human support chahiye", "kisi agent se baat karao", "kisi insaan se baat karao",
    "supervisor se baat", "manager se baat", "insan se baat", "kisi aadmi se baat",
    "senior se baat karao", "asli insaan", "transfer to supervisor", "human se baat karwao",
    "supervisor bulao", "manager bulao", "kisi insaan se connect karo", "customer care se baat",
    "support team se baat", "customer support se baat",
]

# Fraud / Security / Account Compromise phrases across scripts and languages
MULTILINGUAL_FRAUD_KEYWORDS: List[str] = [
    # English
    "fraud", "hacked", "unauthorized", "stolen", "stole", "compromised", "security breach", "scam",
    "money stolen", "account hacked", "identity theft", "phishing", "accessed my account",
    "someone accessed", "unauthorized access", "card compromised", "unauthorized transaction",
    "unauthorized txn", "money deducted without permission",

    # Tamil (native script)
    "மோசடி", "திருட்டு", "ஹேக்", "அங்கீகரிக்கப்படாத", "ஏமாற்று", "சைபர் கிரைம்",
    "பணம் திருடப்பட்டது", "கணக்கு ஹேக்", "கணக்கு திருடப்பட்டது",

    # Tanglish (Romanized Tamil)
    "mosadi", "hack pannitaanga", "thiruttu", "unauthorized txn", "panam pochu fraud",
    "scam pannitaanga", "account hack aayiduchu", "panatha thirudittaanga", "thirudittaanga",
    "panam pochu", "yemaathittaanga", "panam thiruditaanga",

    # Hindi (native script)
    "धोखाधड़ी", "चोरी", "हैक", "स्कैम", "अनधिकृत", "खाता हैक", "पैसे चोरी",
    "खाता चोरी", "पैसे कट गए फ्रॉड",

    # Hinglish (Romanized Hindi)
    "dhokhadhadi", "dhoka hua", "chori ho gaya", "paisa kat gaya scam", "account hack ho gaya",
    "unauthorized debit", "scam hua", "paise chori ho gaye", "koi fraud hua hai", "paisa chori",
]


# Compiled regex patterns for natural conversational supervisor demands
SUPERVISOR_PATTERNS = [
    re.compile(r"\b(?:connect|speak|talk|transfer|escalate|reach|chat)\s+(?:me\s+)?(?:with|to)\s+(?:an?\s+|the\s+)?(?:expert|human|agent|specialist|supervisor|person|representative|support|team|someone)\b", re.IGNORECASE),
    re.compile(r"\b(?:can|could|would|please|need|want)\s+(?:u|you|i|to)?\s*(?:connect|talk|speak|transfer|reach|chat)\s+(?:me\s+)?(?:with|to)\s+(?:an?\s+|the\s+)?(?:expert|human|agent|specialist|supervisor|person|representative|support|team|someone)\b", re.IGNORECASE),
    re.compile(r"\b(?:i\s+want|i\s+need|give\s+me|get\s+me)\s+(?:to\s+speak\s+to\s+|to\s+talk\s+to\s+|to\s+connect\s+with\s+)?(?:an?\s+|the\s+)?(?:human|expert|agent|supervisor|representative|live\s+agent|real\s+person)\b", re.IGNORECASE),
    re.compile(r"\b(?:real\s+person|human\s+being|live\s+agent|human\s+support|human\s+expert|human\s+agent|customer\s+care\s+executive)\b", re.IGNORECASE),
    re.compile(r"\b(?:speak|talk)\s+with\s+(?:an?\s+|the\s+)?(?:expert|agent|person|human|someone)\b", re.IGNORECASE),
    re.compile(r"\b(?:transfer\s+to\s+support|connect\s+with\s+support|connect\s+to\s+support|transfer\s+me\s+to\s+support)\b", re.IGNORECASE),
    re.compile(r"\b(?:agent|expert|human|supervisor|manager|manushan|aalu|support)\s*(?:kitta|ta|kooda|oda)?\s*(?:connect|pesa|pesanum|venum|panna|vai|kedaikuma)\b", re.IGNORECASE),
    re.compile(r"\b(?:expert|human|agent|supervisor)\s+(?:venum|thevai|support\s+venum)\b", re.IGNORECASE),
    re.compile(r"(?:மனித|நிபுணர்|அதிகாரி|மேற்பார்வையாளர்).*(?:பேச|இணைக்க|வேண்டும்|மாற்று)", re.IGNORECASE),
    re.compile(r"\b(?:expert|agent|human|insaan|aadmi|senior|supervisor|manager|adhikari)\s*(?:se|ko)?\s*(?:direct|seedha|turant|jaldi)?\s*(?:baat|connect|karwao|karao|chahiye|bulao|milwao|kijiye|karo)\b", re.IGNORECASE),
    re.compile(r"\b(?:kisi|koi)\s+(?:senior\s+)?(?:expert|agent|insaan|aadmi|person)\s*(?:se)?\s*(?:direct\s+)?(?:baat|connect)\b", re.IGNORECASE),
    re.compile(r"(?:इंसान|विशेषज्ञ|अधिकारी|सुपरवाइजर|एजेंट).*(?:बात|कनेक्ट|चाहिए|कराएं)", re.IGNORECASE),
]

FRAUD_PATTERNS = [
    re.compile(r"\b(?:hack(?:ed)?|unauthorized|stolen|stole|compromised|scam|phishing)\b", re.IGNORECASE),
    re.compile(r"\b(?:account|card|money|panam|paisa|funds)\s+(?:stolen|hacked|thirudittaanga|gayab|unauthorized|stole)\b", re.IGNORECASE),
    re.compile(r"\b(?:money|panam|paisa|amount)\s+(?:deducted|debited)\s+(?:without\s+permission|unauthorized|scam|fraud)\b", re.IGNORECASE),
    re.compile(r"\b(?:someone\s+(?:accessed|hacked|stole|compromised))\b", re.IGNORECASE),
    re.compile(r"(?:மோசடி|திருட்டு|ஹேக்|சைபர் கிரைம்)", re.IGNORECASE),
    re.compile(r"(?:धोखाधड़ी|चोरी|हैक|स्कैम)", re.IGNORECASE),
]


def _normalize_for_matching(text: Any) -> str:
    """Strip extraneous punctuation for robust substring matching."""
    if hasattr(text, "content"):
        text = text.content
    elif hasattr(text, "text"):
        text = text.text
    cleaned = str(text or "").lower()
    # Replace punctuation characters with space, keeping alphanumerics and Indic scripts
    cleaned = re.sub(r"[^\w\s\u0B80-\u0BFF\u0900-\u097F]", " ", cleaned)
    return " ".join(cleaned.split())


def is_supervisor_demand(message: Any) -> bool:
    """Returns True if message contains supervisor/human escalation intent in any supported language/script."""
    if hasattr(message, "content"):
        message = message.content
    elif hasattr(message, "text"):
        message = message.text
    msg_raw = str(message or "").lower()
    msg_norm = _normalize_for_matching(message)
    if any(p.search(msg_raw) or p.search(msg_norm) for p in SUPERVISOR_PATTERNS):
        return True
    return any(
        kw in msg_raw or _normalize_for_matching(kw) in msg_norm
        for kw in MULTILINGUAL_SUPERVISOR_KEYWORDS
    )


def is_fraud_or_security(message: Any) -> bool:
    """Returns True if message contains fraud/security compromise in any supported language/script."""
    if hasattr(message, "content"):
        message = message.content
    elif hasattr(message, "text"):
        message = message.text
    msg_raw = str(message or "").lower()
    msg_norm = _normalize_for_matching(message)
    if any(p.search(msg_raw) or p.search(msg_norm) for p in FRAUD_PATTERNS):
        return True
    return any(
        kw in msg_raw or _normalize_for_matching(kw) in msg_norm
        for kw in MULTILINGUAL_FRAUD_KEYWORDS
    )
