import asyncio
from typing import Any, Dict, List
from sqlalchemy.ext.asyncio import AsyncSession
from app.ai.base import AIProvider

class StubAIProvider(AIProvider):
    """
    Deterministic AI provider used for M3 (before real AI is integrated).
    Uses simple keyword matching.
    """

    async def analyze(self, message: str, context: Dict[str, Any], db: AsyncSession = None) -> Dict[str, Any]:
        text = message.lower()
        intent = "GENERAL"
        
        if any(kw in text for kw in ["payment", "refund", "charge", "billing", "money"]):
            intent = "PAYMENT_ISSUE"
        elif any(kw in text for kw in ["password", "login", "account", "security"]):
            intent = "SECURITY"
        elif any(kw in text for kw in ["human", "escalate", "agent", "person"]):
            intent = "ESCALATE_REQUEST"
            
        # Simulate slight processing delay for realism in UI
        await asyncio.sleep(0.5)

        return {
            "intent": intent,
            "sentiment": "NEUTRAL",
            "entities": [],
            "priority": "HIGH" if intent == "SECURITY" else "MEDIUM"
        }

    async def generate_response(
        self, analysis: Dict[str, Any], knowledge: List[Any], context: Dict[str, Any], db: AsyncSession = None
    ) -> str:
        intent = analysis.get("intent", "GENERAL")
        
        await asyncio.sleep(0.5) # Simulate typing delay

        if intent == "PAYMENT_ISSUE":
            return "I understand you have a question about payments or billing. This is a Stub AI response, but in the future, I'd look up your invoice and help you process a refund."
        elif intent == "SECURITY":
            return "It looks like you're having trouble with your account security or login. (Stub AI: Please ensure you don't share your password.)"
        elif intent == "ESCALATE_REQUEST":
            return "I see you'd like to speak with a human. (Stub AI: I would normally escalate this ticket to our expert queue now.)"
        else:
            return "I am the ResolveAIV2 Stub AI. I received your message and I'm ready to assist you!"
