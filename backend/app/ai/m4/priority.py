from typing import Dict, Any
from app.ai.intelligence.escalation_keywords import is_fraud_or_security

class PriorityEngine:
    def determine_priority(self, intent: str, sentiment: str, message: str) -> str:
        """
        Determines priority based on intent, sentiment, and context.
        Levels: LOW, MEDIUM, HIGH, CRITICAL
        """
        text_lower = message.lower()
        
        if intent == "SECURITY_ISSUE":
            # Determine severity
            if is_fraud_or_security(message) or any(kw in text_lower for kw in ['accessed', 'hack', 'stolen', 'stole', 'unauthorized', 'fraud', 'accessing', 'ஹேக்']):
                return "CRITICAL"
            elif 'suspicious' in text_lower:
                return "HIGH"
            else:
                return "MEDIUM" # e.g. "change my security settings"

        if intent == "ESCALATION_REQUEST":
            return "HIGH"
                
        if sentiment == "NEGATIVE":
            if intent in ["PAYMENT_ISSUE", "LOGIN_ISSUE"]:
                return "HIGH"
            return "MEDIUM"
            
        return "LOW"
