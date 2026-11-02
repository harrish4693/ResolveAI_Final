"""
ResolveAIV2 — Context-Aware Conversation State Manager
======================================================
Maintains structured, isolated, auditable state for each conversation turn:
- Active topic and domain intent.
- Conversational / Discourse function (Speech Act).
- Questions awaiting customer answers (pending_question / pending_entity).
- Unresolved customer requests.
- Accumulated verified entities (Order ID, Transaction ID, etc.).
- Active language preference and demonstrated communication style.
- Actions already performed and their results (preventing redundant tool runs).
- Resolution lifecycle (in_progress, resolved, waiting_for_customer, escalated).

All state is strictly scoped to the current conversation ID and customer ID,
guaranteeing strict customer/tenant isolation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ConversationState:
    conversation_id: int
    customer_id: int
    tenant_id: str = "default"
    active_topic: str = "general"                 # order_status, return_policy, delivery, cancellation, account, technical, general
    active_intent: str = "GENERAL_QUERY"
    conversational_function: str = "NEW_REQUEST"  # GREETING, ACKNOWLEDGMENT, FOLLOW_UP, ANSWER_TO_PENDING, CLARIFICATION_OR_CORRECTION, CONTINUATION, NEW_REQUEST, LANGUAGE_SWITCH, ESCALATION_REQUEST, CRITICAL_SAFETY, EMOTIONAL_REACTION
    latest_customer_message: str = ""
    latest_understood_meaning: str = ""
    last_assistant_response: str = ""
    last_decision: str = ""
    pending_question: Optional[str] = None        # ask_order_id, ask_transaction_id, ask_clarification, confirm_action
    pending_entity: Optional[str] = None          # order_id, transaction_id
    unresolved_request: Optional[str] = None      # The ongoing goal of the customer
    entities: Dict[str, Any] = field(default_factory=dict)
    actions_performed: List[Dict[str, Any]] = field(default_factory=list)
    resolution_status: str = "in_progress"        # in_progress, resolved, waiting_for_customer, escalated
    language_preference: str = "english"
    communication_style: Dict[str, Any] = field(default_factory=lambda: {
        "formality": "informal",
        "brevity": "concise",
        "urgency": "normal",
        "sentiment": "neutral"
    })
    turn_count: int = 0
    pending_handoff_confirmation: bool = False
    pending_handoff_reason: Optional[str] = None
    pending_handoff_analysis: Optional[Dict[str, Any]] = None
    handoff_confirmed: bool = False
    handoff_rejected: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationState":
        valid_keys = {
            "conversation_id", "customer_id", "tenant_id", "active_topic",
            "active_intent", "conversational_function", "latest_customer_message",
            "latest_understood_meaning", "last_assistant_response", "last_decision",
            "pending_question", "pending_entity", "unresolved_request", "entities",
            "actions_performed", "resolution_status", "language_preference",
            "communication_style", "turn_count",
            "pending_handoff_confirmation", "pending_handoff_reason",
            "pending_handoff_analysis", "handoff_confirmed", "handoff_rejected"
        }
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


class ConversationStateManager:
    """Manages the lifecycle and transitions of ConversationState."""

    @staticmethod
    def load_state(
        conversation: Optional[Any] = None,
        all_messages: Optional[List[Any]] = None,
        tenant_id: str = "default"
    ) -> ConversationState:
        """
        Reconstructs or rehydrates ConversationState for the given conversation.
        Strictly isolated to conversation.id and conversation.customer_id.
        """
        # 0. Handle None conversation safely
        if conversation is None:
            return ConversationState(
                conversation_id=0,
                customer_id=0,
                tenant_id=tenant_id,
                language_preference="english",
            )
        all_messages = all_messages or []

        # 1. Search for persisted state in recent AI message metadata
        last_ai_msg = None
        for msg in reversed(all_messages):
            sender = getattr(msg, "sender_type", None)
            sender_str = sender.value if hasattr(sender, "value") else str(sender or "")
            if sender_str.upper() in ("AI", "AGENT", "ASSISTANT"):
                last_ai_msg = msg
                break

        if last_ai_msg and getattr(last_ai_msg, "metadata_", None):
            persisted = last_ai_msg.metadata_.get("conversation_state")
            if isinstance(persisted, dict):
                try:
                    state = ConversationState.from_dict(persisted)
                    # Enforce strict ID matching to prevent any accidental leakage
                    state.conversation_id = conversation.id
                    state.customer_id = conversation.customer_id
                    state.tenant_id = tenant_id
                    if conversation.preferred_language:
                        state.language_preference = conversation.preferred_language.lower()
                    return state
                except Exception as e:
                    logger.warning(f"Could not deserialize persisted conversation_state: {e}")

        # 2. Fallback: Initialize fresh state from historical context
        initial_lang = (getattr(conversation, "preferred_language", None) or "english").lower()
        state = ConversationState(
            conversation_id=conversation.id,
            customer_id=conversation.customer_id,
            tenant_id=tenant_id,
            language_preference=initial_lang,
        )

        # Reconstruct entities and pending state from message history
        for msg in all_messages:
            sender = getattr(msg, "sender_type", None)
            sender_str = sender.value if hasattr(sender, "value") else str(sender or "")
            content = str(getattr(msg, "content", "") or "")

            if sender_str.upper() in ("AI", "AGENT", "ASSISTANT"):
                c_lower = content.lower()
                state.last_assistant_response = content
                if "order id" in c_lower and ("provide" in c_lower or "need" in c_lower or "sollunga" in c_lower or "batayein" in c_lower):
                    state.pending_question = "ask_order_id"
                    state.pending_entity = "order_id"
                elif "transaction id" in c_lower or "txn" in c_lower:
                    state.pending_question = "ask_transaction_id"
                    state.pending_entity = "transaction_id"
                elif "connect pannattuma" in c_lower or "connect you" in c_lower or "connect karun" in c_lower or "இணைக்கட்டுமா" in c_lower or "जोड़ूँ" in c_lower:
                    state.pending_handoff_confirmation = True
                    state.pending_question = "confirm_handoff"

                meta = getattr(msg, "metadata_", {}) or {}
                if isinstance(meta, dict):
                    if meta.get("entities"):
                        state.entities.update(meta["entities"])
                    if meta.get("intent"):
                        state.active_intent = meta["intent"]

        state.turn_count = len(all_messages) // 2
        return state

    @staticmethod
    def update_before_turn(
        state: ConversationState,
        customer_message: str,
        understanding: Any,
    ) -> ConversationState:
        """
        Transitions conversation state before AI provider planning.
        Evaluates the speech act (conversational function) and pending requests.
        """
        state.turn_count += 1
        state.latest_customer_message = customer_message
        state.latest_understood_meaning = getattr(understanding, "understood_meaning", "")
        conv_fn = getattr(understanding, "conversational_function", "NEW_REQUEST")
        state.conversational_function = conv_fn

        # Merge newly extracted entities into accumulated entities
        new_entities = getattr(understanding, "entities", {}) or {}
        if isinstance(new_entities, dict) and new_entities:
            state.entities.update(new_entities)

        # Update communication style
        style = getattr(understanding, "communication_style", None)
        if isinstance(style, dict):
            state.communication_style.update(style)

        # Behavioral state transitions based on Conversational Function:
        if state.pending_handoff_confirmation:
            from app.ai.intelligence.language import UniversalMeaningEngine
            if UniversalMeaningEngine.is_affirmative_confirmation(customer_message):
                state.pending_handoff_confirmation = False
                state.handoff_confirmed = True
                state.handoff_rejected = False
                state.resolution_status = "escalating"
                state.pending_question = None
                return state
            elif UniversalMeaningEngine.is_negative_confirmation(customer_message):
                state.pending_handoff_confirmation = False
                state.handoff_rejected = True
                state.handoff_confirmed = False
                state.pending_handoff_reason = None
                state.pending_handoff_analysis = None
                state.resolution_status = "in_progress"
                state.pending_question = None
                return state
            else:
                # Ambiguous response to confirmation: keep awaiting confirmation
                state.resolution_status = "waiting_for_customer"
                state.pending_question = "confirm_handoff"
                return state

        if conv_fn == "ACKNOWLEDGMENT":
            # RC-2 Fix: Only wipe entities when no active unresolved request remains.
            # "Seri" / "ok" is conversational glue — the customer's task may still be in flight.
            # Entities are cleared only when the conversation goal has been explicitly met
            # (resolution_status == "resolved" and no pending question outstanding).
            state.active_intent = "ACKNOWLEDGMENT"
            has_active_task = bool(state.unresolved_request) or bool(state.pending_question)
            if not has_active_task:
                state.entities = {}
                state.resolution_status = "resolved"
                state.unresolved_request = None
            # If there IS an active task, keep entities intact — the acknowledgment
            # is just conversational, not a signal that the issue is resolved.

        elif conv_fn == "ANSWER_TO_PENDING":
            # The customer answered ResolveAI's pending question
            state.pending_question = None
            state.pending_entity = None
            state.resolution_status = "in_progress"

        elif conv_fn == "CLARIFICATION_OR_CORRECTION":
            # Correction to previously supplied information
            state.resolution_status = "in_progress"

        elif conv_fn in ("NEW_REQUEST", "TOPIC_CHANGE"):
            # Customer introduced a new topic / domain inquiry
            cat = getattr(understanding, "category", "general")
            state.active_topic = cat
            state.active_intent = getattr(understanding, "intent", "GENERAL_QUERY")
            state.pending_question = None
            state.pending_entity = None
            state.resolution_status = "in_progress"
            state.unresolved_request = customer_message

        elif conv_fn == "FOLLOW_UP":
            state.resolution_status = "in_progress"

        elif conv_fn == "LANGUAGE_SWITCH":
            # Preferred language changed, preserve active unresolved request
            pass

        elif conv_fn in ("ESCALATION_REQUEST", "CRITICAL_SAFETY"):
            state.resolution_status = "escalated"

        return state

    @staticmethod
    def update_after_turn(
        state: ConversationState,
        decision: str,
        response_text: str,
        tool_name: Optional[str] = None,
        tool_result: Optional[Any] = None,
        analysis: Optional[Dict[str, Any]] = None,
    ) -> ConversationState:
        """
        Updates state after response generation and validation pass.
        """
        state.last_decision = decision
        state.last_assistant_response = response_text

        # Record action if a tool was executed
        if tool_name:
            state.actions_performed.append({
                "tool": tool_name,
                "status": "success" if tool_result else "executed",
                "result_preview": str(tool_result)[:100] if tool_result else None
            })

        # Track pending expectations from the customer
        resp_lower = (response_text or "").lower()
        if state.pending_handoff_confirmation:
            state.resolution_status = "waiting_for_customer"
            state.pending_question = "confirm_handoff"
        elif decision == "ASK_USER":
            state.resolution_status = "waiting_for_customer"
            if "order id" in resp_lower:
                state.pending_question = "ask_order_id"
                state.pending_entity = "order_id"
            elif "transaction id" in resp_lower:
                state.pending_question = "ask_transaction_id"
                state.pending_entity = "transaction_id"
            else:
                state.pending_question = "ask_clarification"
        elif decision == "RESOLVE":
            if state.conversational_function == "ACKNOWLEDGMENT":
                state.resolution_status = "resolved"
                state.pending_question = None
                state.unresolved_request = None
            else:
                state.resolution_status = "in_progress"
                state.unresolved_request = None
        elif decision == "ESCALATE":
            state.resolution_status = "escalated"

        return state
