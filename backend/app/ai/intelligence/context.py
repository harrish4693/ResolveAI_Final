"""
Capability 3: Conversation Context Management

Manages conversation context including message retrieval, token counting,
context enrichment with customer history, and context summarization.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ContextWindow:
    """Represents the current context window state."""
    messages: List[Dict[str, Any]] = field(default_factory=list)
    total_tokens: int = 0
    max_tokens: int = 4000
    is_truncated: bool = False
    summary: str = ""
    key_points: List[str] = field(default_factory=list)


@dataclass
class EnrichedContext:
    """Context enriched with customer history, tickets, and KB results."""
    conversation_history: List[Dict[str, Any]] = field(default_factory=list)
    customer_memories: List[str] = field(default_factory=list)
    related_tickets: List[Dict[str, Any]] = field(default_factory=list)
    rag_results: List[Dict[str, Any]] = field(default_factory=list)
    intent_history: List[str] = field(default_factory=list)
    enrichment_score: float = 0.0  # 0-1 how much useful context we have


class ConversationContextManager:
    """
    Manages conversation context window including token counting,
    message prioritization, and context window optimization.
    """

    # Average tokens per character (rough estimate)
    CHARS_PER_TOKEN = 4
    DEFAULT_MAX_TOKENS = 4000

    def __init__(self, max_tokens: int = DEFAULT_MAX_TOKENS):
        self.max_tokens = max_tokens

    def build_context_window(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: Optional[int] = None,
    ) -> ContextWindow:
        """
        Build an optimized context window from conversation messages.
        
        Keeps the most recent messages within the token limit,
        and summarizes older messages if needed.
        """
        limit = max_tokens or self.max_tokens
        window = ContextWindow(max_tokens=limit)

        if not messages:
            return window

        # Calculate tokens for each message
        message_tokens = []
        for msg in messages:
            content = msg.get("content", "")
            tokens = self._estimate_tokens(content)
            message_tokens.append((msg, tokens))

        # Build window from most recent, working backwards
        selected = []
        total = 0
        for msg, tokens in reversed(message_tokens):
            if total + tokens <= limit:
                selected.insert(0, msg)
                total += tokens
            else:
                window.is_truncated = True
                break

        window.messages = selected
        window.total_tokens = total

        # If truncated, generate summary of older messages
        if window.is_truncated:
            older = [msg for msg, _ in message_tokens if msg not in selected]
            window.summary = self._summarize_messages(older)
            window.key_points = self._extract_key_points(older)

        return window

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count from text length."""
        return max(1, len(text) // self.CHARS_PER_TOKEN)

    def _summarize_messages(self, messages: List[Dict[str, Any]]) -> str:
        """Create a brief summary of older messages."""
        if not messages:
            return ""

        parts = []
        for msg in messages[-5:]:  # Last 5 of the older messages
            sender = msg.get("sender_type", "unknown")
            content = msg.get("content", "")[:100]
            parts.append(f"{sender}: {content}")

        return "Previous context: " + " | ".join(parts)

    def _extract_key_points(self, messages: List[Dict[str, Any]]) -> List[str]:
        """Extract key points from older messages."""
        key_points = []
        for msg in messages:
            content = msg.get("content", "").lower()
            # Extract entity mentions
            if "txn" in content or "ord" in content:
                key_points.append(f"Referenced: {msg.get('content', '')[:80]}")
            if any(kw in content for kw in ["problem", "issue", "error", "fail"]):
                key_points.append(f"Issue reported: {msg.get('content', '')[:80]}")
        return key_points[:5]  # Limit to 5 key points


class ContextEnricher:
    """
    Enriches conversation context with additional information sources:
    customer history, related tickets, and knowledge base results.
    """

    def enrich(
        self,
        conversation_history: List[Dict[str, Any]],
        customer_memories: List[str] = None,
        related_tickets: List[Dict[str, Any]] = None,
        rag_results: List[Dict[str, Any]] = None,
    ) -> EnrichedContext:
        """
        Enrich the conversation context with all available information.
        
        Returns:
            EnrichedContext with combined information and enrichment score.
        """
        enriched = EnrichedContext(
            conversation_history=conversation_history or [],
            customer_memories=customer_memories or [],
            related_tickets=related_tickets or [],
            rag_results=rag_results or [],
        )

        # Extract intent history
        enriched.intent_history = self._extract_intent_history(conversation_history)

        # Calculate enrichment score
        enriched.enrichment_score = self._calculate_enrichment_score(enriched)

        return enriched

    def _extract_intent_history(self, history: List[Dict[str, Any]]) -> List[str]:
        """Extract sequence of intents from conversation history."""
        intents = []
        for msg in history:
            metadata = msg.get("metadata", {})
            if isinstance(metadata, dict):
                intent = metadata.get("intent")
                if intent and (not intents or intents[-1] != intent):
                    intents.append(intent)
        return intents

    def _calculate_enrichment_score(self, ctx: EnrichedContext) -> float:
        """Calculate how well-enriched the context is (0-1)."""
        score = 0.0

        # Conversation history
        msg_count = len(ctx.conversation_history)
        if msg_count > 0:
            score += 0.25
        if msg_count >= 3:
            score += 0.1

        # Customer memories
        if ctx.customer_memories:
            score += 0.2

        # Related tickets
        if ctx.related_tickets:
            score += 0.15

        # RAG results
        if ctx.rag_results:
            score += 0.2

        # Intent history
        if ctx.intent_history:
            score += 0.1

        return min(1.0, score)


class ContextSummarizer:
    """
    Summarizes conversation context for handoff to human experts
    or for context window optimization.
    """

    def summarize_for_handoff(
        self,
        history: List[Dict[str, Any]],
        analysis: Dict[str, Any] = None,
        memories: List[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a comprehensive summary for expert handoff.
        
        Returns a structured summary including:
        - Issue description
        - Key entities
        - Customer sentiment
        - Actions attempted
        - Relevant memories
        """
        summary: Dict[str, Any] = {
            "issue_description": "",
            "customer_messages": [],
            "ai_responses": [],
            "entities_collected": {},
            "sentiment": "NEUTRAL",
            "actions_attempted": [],
            "memories": memories or [],
        }

        if not history:
            return summary

        # Separate customer and AI messages
        for msg in history:
            sender = msg.get("sender_type", "")
            content = msg.get("content", "")
            
            if sender in ("customer", "CUSTOMER"):
                summary["customer_messages"].append(content[:200])
            elif sender in ("ai", "AI"):
                summary["ai_responses"].append(content[:200])

        # First customer message is usually the issue description
        if summary["customer_messages"]:
            summary["issue_description"] = summary["customer_messages"][0]

        # Extract from analysis
        if analysis:
            summary["entities_collected"] = analysis.get("entities", {})
            summary["sentiment"] = analysis.get("sentiment", "NEUTRAL")

            # Track attempted actions
            decision = analysis.get("decision_state", "")
            tool = analysis.get("tool_name", "")
            if decision:
                summary["actions_attempted"].append(f"Decision: {decision}")
            if tool:
                summary["actions_attempted"].append(f"Tool: {tool}")

        return summary

    def get_context_stats(self, history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get statistics about the conversation context."""
        customer_msgs = sum(1 for m in history if m.get("sender_type") in ("customer", "CUSTOMER"))
        ai_msgs = sum(1 for m in history if m.get("sender_type") in ("ai", "AI"))
        total_chars = sum(len(m.get("content", "")) for m in history)

        return {
            "total_messages": len(history),
            "customer_messages": customer_msgs,
            "ai_messages": ai_msgs,
            "total_characters": total_chars,
            "estimated_tokens": total_chars // 4,
        }
