from abc import ABC, abstractmethod
from typing import Any, Dict, List, Type
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

class AIProvider(ABC):
    """
    Abstract AI Provider interface.
    Ensures that the conversation engine is completely decoupled from the AI implementation.
    """

    @abstractmethod
    async def analyze(self, message: str, context: Dict[str, Any], db: AsyncSession = None) -> Dict[str, Any]:
        """
        Analyzes the incoming message and extracts intent, sentiment, and entities.
        Returns a dictionary representing the AnalysisResult.
        """
        pass

    @abstractmethod
    async def generate_response(
        self, analysis: Dict[str, Any], knowledge: List[Any], context: Dict[str, Any], db: AsyncSession = None
    ) -> str:
        """
        Generates a text response based on the analysis, provided knowledge articles,
        and conversation context.
        """
        pass

    @abstractmethod
    async def generate_structured(
        self, messages: List[Dict[str, str]], response_format: Type[BaseModel]
    ) -> BaseModel:
        """
        Generates a structured Pydantic response based on the provided messages.
        This provides a unified method for generic extractions like Memory and Semantic Validation.
        """
        pass

    async def process_voice_turn(
        self, message: str, context: Dict[str, Any], db: AsyncSession = None
    ) -> Dict[str, Any]:
        """
        Processes a real-time voice turn with unified emotion awareness, language detection,
        and conversational response generation.
        """
        analysis = await self.analyze(message, context, db)
        response_text = await self.generate_response(analysis, [], context, db)
        return {
            "intent": analysis.get("intent", "GENERAL_QUERY"),
            "sentiment": analysis.get("sentiment", "neutral"),
            "priority": analysis.get("priority", "LOW"),
            "language": analysis.get("language", "English"),
            "emotion": analysis.get("emotion", "calm"),
            "emotion_confidence": analysis.get("emotion_confidence", 0.85),
            "entities": analysis.get("entities", {}),
            "decision": analysis.get("decision_state", "RESOLVE"),
            "spoken_response": response_text,
            "tool_name": analysis.get("tool_name"),
            "tool_args": analysis.get("tool_args", {}),
            "reason": analysis.get("decision_reason", ""),
        }

