"""
M12.5 — Deterministic Validation Rules

Each rule receives a ResponseValidationContext and returns a ValidationResult.
Rules are ordered by priority: structural → security → tool → action → contradiction
→ memory → intent → grounding → quality.

Security and tool truthfulness are primarily deterministic.
They do NOT depend on an LLM — they use server-derived structured data.
"""

import re
import logging
from typing import List, Optional

from app.ai.validation.models import (
    ResponseValidationContext,
    ValidationResult,
    ValidationStatus,
    ValidationViolation,
    ValidationChecks,
    CheckResult,
    ToolResultContext,
)

logger = logging.getLogger(__name__)

# Patterns that should never appear in customer-facing responses
_INTERNAL_LEAK_PATTERNS = [
    re.compile(r"system\s*prompt", re.IGNORECASE),
    re.compile(r"internal\s*note", re.IGNORECASE),
    re.compile(r"api[_\s]?key", re.IGNORECASE),
    re.compile(r"bearer\s+[a-zA-Z0-9\-_.]+", re.IGNORECASE),
    re.compile(r"sk[-_][a-zA-Z0-9_-]{15,}", re.IGNORECASE),  # API keys
    re.compile(r"password\s*(?:is|[:=])\s*\S+", re.IGNORECASE),
    re.compile(r"secret(?:\s*key)?\s*(?:is|[:=])\s*\S+", re.IGNORECASE),
    re.compile(r"traceback\s*\(most recent", re.IGNORECASE),
    re.compile(r"Traceback:", re.IGNORECASE),
    re.compile(r"File \".*\", line \d+", re.IGNORECASE),
    re.compile(r"sqlalchemy\.", re.IGNORECASE),
    re.compile(r"database_url", re.IGNORECASE),
]

# Action claim patterns — the AI must not claim these unless the corresponding tool succeeded
_ACTION_CLAIM_PATTERNS = {
    "refund": re.compile(
        r"\b(?:i(?:'ve| have)?|we(?:'ve| have)?)\s+(?:just\s+)?(?:issued|processed|approved)\b.*\brefund\b|"
        r"\b(?:your\s+refund\s+(?:has\s+been|was)\s+(?:issued|processed|approved))\b|"
        r"\brefund\s+(?:has\s+been|was)\s+(?:issued|processed|approved)\s+to\s+your\b",
        re.IGNORECASE
    ),
    "cancel": re.compile(
        r"\b(?:i(?:'ve| have)?|we(?:'ve| have)?)\s+(?:just\s+)?(?:cancelled|canceled)\b.*\border\b|"
        r"\b(?:your\s+order\s+(?:has\s+been|was)\s+(?:cancelled|canceled))\b|"
        r"\border\s+[A-Za-z0-9_-]+\s+(?:has\s+been|was)\s+(?:cancelled|canceled)\b",
        re.IGNORECASE
    ),
    "update": re.compile(
        r"\b(?:i(?:'ve| have)?|we(?:'ve| have)?)\s+(?:just\s+)?(?:updated|changed|modified)\b.*\b(?:account|address|profile)\b|"
        r"\b(?:your\s+(?:account|address|profile)\s+(?:has\s+been|was)\s+(?:updated|changed|modified))\b",
        re.IGNORECASE
    ),
    "ticket_create": re.compile(
        r"\b(?:i(?:'ve| have)?|we(?:'ve| have)?)\s+(?:just\s+)?(?:created|opened|submitted)\b.*\bticket\b|"
        r"\b(?:a\s+ticket\s+(?:has\s+been|was)\s+(?:created|opened|submitted))\b",
        re.IGNORECASE
    ),
    "transfer": re.compile(
        r"\b(?:i(?:'ve| have)?|we(?:'ve| have)?)\s+(?:just\s+)?(?:transferred|connected)\s+you\b.*\b(?:expert|agent|specialist)\b|"
        r"\b(?:you\s+have\s+been\s+(?:transferred|connected))\b.*\b(?:expert|agent|specialist)\b",
        re.IGNORECASE
    ),
}

# Tool action mapping — which tool names correspond to which action claims
_TOOL_ACTION_MAP = {
    "create_refund_request": "refund",
    "cancel_order": "cancel",
    "update_account": "update",
    "create_support_ticket": "ticket_create",
    "request_human_support": "transfer",
}


def check_structural(ctx: ResponseValidationContext) -> ValidationResult:
    """Reject empty, whitespace-only, malformed, or obviously broken responses."""
    draft = ctx.draft_response
    violations = []

    if not draft or not draft.strip():
        violations.append(ValidationViolation(
            check_name="STRUCTURAL",
            violation_type="EMPTY_RESPONSE",
            reason="Draft response is empty or whitespace-only.",
            severity="HIGH",
        ))

    # Raw JSON that shouldn't be customer-facing
    stripped = draft.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            import json
            parsed = json.loads(stripped)
            # If it parsed as JSON with typical internal keys, it's likely debug output
            if any(k in parsed for k in ("decision", "tool_name", "status", "error_code", "stack_trace")):
                violations.append(ValidationViolation(
                    check_name="STRUCTURAL",
                    violation_type="RAW_JSON_OUTPUT",
                    reason="Draft response appears to be raw JSON debug output, not customer-facing prose.",
                    severity="HIGH",
                ))
        except (json.JSONDecodeError, ValueError):
            pass

    # Stack traces / exception messages
    if re.search(r"(Exception|Error|Traceback):", draft) and re.search(r"File \"", draft):
        violations.append(ValidationViolation(
            check_name="STRUCTURAL",
            violation_type="EXCEPTION_LEAK",
            reason="Draft response contains a stack trace or exception message.",
            severity="HIGH",
        ))

    # Excessive repetition (garbage text)
    words = draft.split()
    if len(words) > 10:
        unique_ratio = len(set(words)) / len(words)
        if unique_ratio < 0.15:
            violations.append(ValidationViolation(
                check_name="STRUCTURAL",
                violation_type="GARBAGE_REPETITION",
                reason="Draft response contains excessive repetition.",
                severity="MEDIUM",
            ))

    if violations:
        return ValidationResult(
            status=ValidationStatus.REGENERATE,
            violations=violations,
            checks=ValidationChecks(structural=CheckResult.FAIL),
        )
    return ValidationResult(status=ValidationStatus.VALID, checks=ValidationChecks(structural=CheckResult.PASS_))


def _normalize_id(val: str) -> str:
    """Normalize identifiers by removing hyphens, underscores, whitespace and lowercasing."""
    return re.sub(r"[-_\s]", "", val).lower()


def check_security(ctx: ResponseValidationContext) -> ValidationResult:
    """
    Security validation using server-derived structured authorization data.
    This is deterministic and does NOT rely solely on regex.
    """
    draft = ctx.draft_response.lower()
    violations = []

    # 1. Cross-customer data leak detection using structured authorization data
    #    Extract any order/ticket IDs mentioned in the draft (require digits to avoid matching "order")
    mentioned_order_ids = set(re.findall(r"\b(ORD[-_]?[a-zA-Z]*\d+\w*)\b", ctx.draft_response, re.IGNORECASE))
    mentioned_ticket_ids = set(re.findall(r"\b((?:TICKET|TKT)[-_]?[a-zA-Z]*\d+\w*)\b", ctx.draft_response, re.IGNORECASE))

    authorized_orders_norm = {_normalize_id(oid) for oid in ctx.authorized_order_ids}
    authorized_tickets_norm = {_normalize_id(tid) for tid in ctx.authorized_ticket_ids}

    # Extract user input references so echoing user's query in holding / clarification is not treated as a leak
    user_orders_norm = {_normalize_id(oid) for oid in re.findall(r"\b(ORD[-_]?[a-zA-Z]*\d+\w*)\b", ctx.user_message or "", re.IGNORECASE)}
    user_tickets_norm = {_normalize_id(tid) for tid in re.findall(r"\b((?:TICKET|TKT)[-_]?[a-zA-Z]*\d+\w*)\b", ctx.user_message or "", re.IGNORECASE)}

    EXAMPLE_PLACEHOLDER_IDS = {
        "ord123", "ord1234", "ord12345", "ord000", "ord999", "ordxxxx", "ordxxxxx",
        "ticket123", "ticket1234", "ticket12345", "ticket000", "tkt123", "tkt1234"
    }

    for oid in mentioned_order_ids:
        norm_oid = _normalize_id(oid)
        if norm_oid not in authorized_orders_norm:
            # If the agent is about to execute a tool (holding message), do not abort the tool call
            if ctx.agent_decision == "USE_TOOL" and norm_oid in user_orders_norm:
                continue

            # If the response is informing the user the order was not found / asking for verification
            is_clarification_or_not_found = any(phrase in draft for phrase in [
                "not found", "could not find", "couldn't find", "unable to find",
                "verify", "check your order", "double-check", "provide your order",
                "no order found", "invalid order"
            ])
            if is_clarification_or_not_found and norm_oid in user_orders_norm:
                continue

            # Allow illustrative format examples in clarifying questions (e.g. "for example: ORD-123" or "looks like ORD-12345")
            is_format_example = (
                norm_oid in EXAMPLE_PLACEHOLDER_IDS
                or any(hint in draft for hint in [
                    "example", "e.g.", "looks like", "such as", "format", "sample",
                    "like ord", "e.g.,", "for instance", "provide your order id"
                ])
            )
            if is_format_example and ctx.agent_decision == "ASK_USER":
                continue

            if authorized_orders_norm:
                violations.append(ValidationViolation(
                    check_name="SECURITY",
                    violation_type="CROSS_CUSTOMER_ORDER_LEAK",
                    reason=f"Draft mentions order '{oid}' which is not authorized for this customer.",
                    severity="HIGH",
                ))

    for tid in mentioned_ticket_ids:
        norm_tid = _normalize_id(tid)
        if norm_tid not in authorized_tickets_norm:
            if ctx.agent_decision == "USE_TOOL" and norm_tid in user_tickets_norm:
                continue

            is_clarification_or_not_found = any(phrase in draft for phrase in [
                "not found", "could not find", "couldn't find", "verify", "check your ticket", "provide"
            ])
            if is_clarification_or_not_found and norm_tid in user_tickets_norm:
                continue

            is_format_example = (
                norm_tid in EXAMPLE_PLACEHOLDER_IDS
                or any(hint in draft for hint in [
                    "example", "e.g.", "looks like", "such as", "format", "sample",
                    "like tkt", "like ticket", "e.g.,", "for instance", "provide your ticket"
                ])
            )
            if is_format_example and ctx.agent_decision == "ASK_USER":
                continue

            if authorized_tickets_norm:
                violations.append(ValidationViolation(
                    check_name="SECURITY",
                    violation_type="CROSS_CUSTOMER_TICKET_LEAK",
                    reason=f"Draft mentions ticket '{tid}' which is not authorized for this customer.",
                    severity="HIGH",
                ))

    # 2. Internal notes leak detection
    for note in ctx.internal_notes:
        # Check if the draft contains substantial content from internal notes
        note_words = [w.lower() for w in note.split() if len(w) > 4]
        if note_words:
            matching = sum(1 for w in note_words if w in draft)
            match_ratio = matching / len(note_words) if note_words else 0
            if match_ratio > 0.5 and len(note_words) >= 3:
                violations.append(ValidationViolation(
                    check_name="SECURITY",
                    violation_type="INTERNAL_NOTE_LEAK",
                    reason="Draft response appears to expose content from internal expert notes.",
                    severity="HIGH",
                ))
                break

    # 3. Regex-based defense-in-depth for secrets/credentials/system internals
    for pattern in _INTERNAL_LEAK_PATTERNS:
        if pattern.search(ctx.draft_response):
            violations.append(ValidationViolation(
                check_name="SECURITY",
                violation_type="INTERNAL_INFO_LEAK",
                reason=f"Draft response may contain internal/system information (pattern: {pattern.pattern[:40]}).",
                severity="HIGH",
            ))
            break  # One is enough to flag

    if violations:
        return ValidationResult(
            status=ValidationStatus.ESCALATE,
            violations=violations,
            checks=ValidationChecks(security=CheckResult.FAIL),
        )
    return ValidationResult(status=ValidationStatus.VALID, checks=ValidationChecks(security=CheckResult.PASS_))


def check_tool_truthfulness(ctx: ResponseValidationContext) -> ValidationResult:
    """
    Ensure the draft response accurately reflects actual tool execution results.
    Deterministic comparison against structured tool results.
    """
    if not ctx.tool_results:
        return ValidationResult(status=ValidationStatus.VALID, checks=ValidationChecks(tool_truthfulness=CheckResult.SKIP))

    draft_lower = ctx.draft_response.lower()
    violations = []

    for tool_result in ctx.tool_results:
        if not tool_result.success:
            # Tool FAILED — draft must not claim success
            success_phrases = [
                "has been shipped", "has shipped", "was shipped",
                "has been delivered", "was delivered",
                "has been processed", "was processed",
                "is currently shipped", "is currently delivered",
                "successfully", "completed successfully",
                "your order is on its way",
            ]
            for phrase in success_phrases:
                if phrase in draft_lower:
                    violations.append(ValidationViolation(
                        check_name="TOOL_TRUTHFULNESS",
                        violation_type="FABRICATED_SUCCESS_ON_FAILURE",
                        reason=f"Tool '{tool_result.tool_name}' failed but draft claims success ('{phrase}').",
                        severity="HIGH",
                    ))
                    break

        else:
            # Tool SUCCEEDED — check that claims match actual data
            data = tool_result.data
            if "status" in data:
                actual_status = str(data["status"]).lower()
                # Map known statuses to what the AI might say
                status_contradictions = {
                    "processing": ["shipped", "delivered", "completed", "in transit", "out for delivery"],
                    "shipped": ["delivered", "completed", "processing"],
                    "pending": ["shipped", "delivered", "completed", "processed", "in transit"],
                    "failed": ["success", "shipped", "delivered", "completed", "processed"],
                    "cancelled": ["shipped", "delivered", "active", "in transit"],
                    "open": ["closed", "resolved", "completed"],
                    "closed": ["open", "pending", "in progress"],
                }
                contradicting_claims = status_contradictions.get(actual_status, [])
                for claim in contradicting_claims:
                    if claim in draft_lower:
                        violations.append(ValidationViolation(
                            check_name="TOOL_TRUTHFULNESS",
                            violation_type="STATUS_MISMATCH",
                            reason=f"Tool returned status='{data['status']}' but draft claims '{claim}'.",
                            severity="HIGH",
                        ))
                        break

    if violations:
        return ValidationResult(
            status=ValidationStatus.REGENERATE,
            violations=violations,
            checks=ValidationChecks(tool_truthfulness=CheckResult.FAIL),
        )
    return ValidationResult(status=ValidationStatus.VALID, checks=ValidationChecks(tool_truthfulness=CheckResult.PASS_))


def check_action_truthfulness(ctx: ResponseValidationContext) -> ValidationResult:
    """
    Prevent the AI from claiming an action was completed when no tool
    successfully performed that action.
    """
    draft = ctx.draft_response
    violations = []

    # Build set of successfully completed action types
    completed_actions = set()
    for tr in ctx.tool_results:
        if tr.success:
            action_type = _TOOL_ACTION_MAP.get(tr.tool_name)
            if action_type:
                completed_actions.add(action_type)

    # Check each action claim pattern
    for action_type, pattern in _ACTION_CLAIM_PATTERNS.items():
        if action_type == "transfer" and ctx.agent_decision == "ESCALATE":
            continue # Escalation is a valid transfer claim natively

        if pattern.search(draft):
            if action_type not in completed_actions:
                violations.append(ValidationViolation(
                    check_name="ACTION_TRUTHFULNESS",
                    violation_type="FABRICATED_ACTION",
                    reason=f"Draft claims '{action_type}' action was completed, but no tool successfully performed it.",
                    severity="HIGH",
                ))

    # Special check: pending/confirmation states must not be described as completed
    for tr in ctx.tool_results:
        if not tr.success and tr.error_code in ("AWAITING_CONFIRMATION", "CONFIRMATION_REQUIRED", "PENDING"):
            if any(word in draft.lower() for word in ["completed", "done", "processed", "finished", "succeeded"]):
                violations.append(ValidationViolation(
                    check_name="ACTION_TRUTHFULNESS",
                    violation_type="PENDING_CLAIMED_AS_COMPLETE",
                    reason=f"Tool '{tr.tool_name}' is still pending/awaiting confirmation but draft claims completion.",
                    severity="HIGH",
                ))

    if violations:
        return ValidationResult(
            status=ValidationStatus.REGENERATE,
            violations=violations,
            checks=ValidationChecks(action_truthfulness=CheckResult.FAIL),
        )
    return ValidationResult(status=ValidationStatus.VALID, checks=ValidationChecks(action_truthfulness=CheckResult.PASS_))


def check_contradiction(ctx: ResponseValidationContext) -> ValidationResult:
    """
    Detect contradictions between the draft and authoritative tool data.
    Authoritative tool/database data always wins.
    """
    if not ctx.tool_results:
        return ValidationResult(status=ValidationStatus.VALID, checks=ValidationChecks(contradiction=CheckResult.SKIP))

    draft_lower = ctx.draft_response.lower()
    violations = []

    for tr in ctx.tool_results:
        if not tr.success:
            continue
        data = tr.data

        # Check order_id contradiction
        if "order_id" in data:
            actual_oid = str(data["order_id"])
            # If the draft mentions a DIFFERENT order ID, flag it
            mentioned = re.findall(r"\b(ORD[-_]?[a-zA-Z]*\d+\w*)\b", ctx.draft_response, re.IGNORECASE)
            for m_oid in mentioned:
                if _normalize_id(m_oid) != _normalize_id(actual_oid):
                    violations.append(ValidationViolation(
                        check_name="CONTRADICTION",
                        violation_type="WRONG_ORDER_ID",
                        reason=f"Tool returned order_id='{actual_oid}' but draft mentions '{m_oid}'.",
                        severity="HIGH",
                    ))

        # Check status contradiction (already partially handled in tool_truthfulness,
        # but this catches broader mismatches)
        if "status" in data:
            actual = str(data["status"]).lower()
            # payment-specific contradiction
            if actual == "failed" and any(w in draft_lower for w in ["successful", "succeeded", "went through", "was accepted"]):
                violations.append(ValidationViolation(
                    check_name="CONTRADICTION",
                    violation_type="STATUS_CONTRADICTION",
                    reason=f"Tool reports status='FAILED' but draft claims success.",
                    severity="HIGH",
                ))

    if violations:
        return ValidationResult(
            status=ValidationStatus.REGENERATE,
            violations=violations,
            checks=ValidationChecks(contradiction=CheckResult.FAIL),
        )
    return ValidationResult(status=ValidationStatus.VALID, checks=ValidationChecks(contradiction=CheckResult.PASS_))


def check_memory_consistency(ctx: ResponseValidationContext) -> ValidationResult:
    """
    Ensure the AI does not present stale historical memory as current authoritative truth
    when contradicted by current tool results.
    """
    if not ctx.memory_context or not ctx.tool_results:
        return ValidationResult(status=ValidationStatus.VALID, checks=ValidationChecks(memory_consistency=CheckResult.SKIP))

    violations = []
    draft_lower = ctx.draft_response.lower()

    # Extract order IDs from memory
    memory_order_ids = set()
    for mem in ctx.memory_context:
        memory_order_ids.update(re.findall(r"\b(ORD[-_]?[a-zA-Z]*\d+\w*)\b", mem, re.IGNORECASE))

    # Extract current authoritative order IDs from tool results
    current_order_ids = set()
    for tr in ctx.tool_results:
        if tr.success and "order_id" in tr.data:
            current_order_ids.add(_normalize_id(str(tr.data["order_id"])))

    # If the draft mentions a memory order ID that is NOT the current tool order ID
    if current_order_ids:
        for mem_oid in memory_order_ids:
            if _normalize_id(mem_oid) not in current_order_ids:
                # Check if the draft actually uses this stale memory ID as if it's current
                if mem_oid.lower() in draft_lower:
                    # Is it being presented as current truth?
                    stale_phrases = ["your order " + mem_oid.lower(), mem_oid.lower() + " is", mem_oid.lower() + " has"]
                    if any(phrase in draft_lower for phrase in stale_phrases):
                        violations.append(ValidationViolation(
                            check_name="MEMORY_CONSISTENCY",
                            violation_type="STALE_MEMORY_AS_CURRENT",
                            reason=f"Draft presents memory order '{mem_oid}' as current, but current tool data shows {current_order_ids}.",
                            severity="HIGH",
                        ))

    if violations:
        return ValidationResult(
            status=ValidationStatus.REGENERATE,
            violations=violations,
            checks=ValidationChecks(memory_consistency=CheckResult.FAIL),
        )
    return ValidationResult(status=ValidationStatus.VALID, checks=ValidationChecks(memory_consistency=CheckResult.PASS_))


def check_intent_alignment(ctx: ResponseValidationContext) -> ValidationResult:
    """
    Verify the draft response addresses the customer's actual intent.
    Uses structured intent classification, not keyword matching.
    """
    if not ctx.detected_intent:
        return ValidationResult(status=ValidationStatus.VALID, checks=ValidationChecks(intent_alignment=CheckResult.SKIP))

    if ctx.tool_results:
        return ValidationResult(status=ValidationStatus.VALID, checks=ValidationChecks(intent_alignment=CheckResult.SKIP))

    draft_lower = ctx.draft_response.lower()
    intent = ctx.detected_intent.upper()
    violations = []

    if ctx.detected_language != "en":
        return ValidationResult(status=ValidationStatus.VALID, checks=ValidationChecks(intent_alignment=CheckResult.SKIP))

    # Map intents to response-relevance indicators
    intent_relevance = {
        "PAYMENT_ISSUE": ["payment", "charge", "refund", "transaction", "billing", "invoice", "card", "money"],
        "DELIVERY_ISSUE": ["delivery", "order", "shipping", "shipped", "tracking", "arrived", "package", "transit"],
        "LOGIN_ISSUE": ["login", "password", "account", "sign in", "access", "locked", "reset", "credentials"],
        "SECURITY_ISSUE": ["security", "breach", "unauthorized", "suspicious", "compromised", "fraud"],
        "REFUND_ISSUE": ["refund", "return", "money back", "reimburse", "credit"],
    }

    # Skip for conversational intents
    if intent in ("GREETING", "GENERAL_QUERY"):
        return ValidationResult(status=ValidationStatus.VALID, checks=ValidationChecks(intent_alignment=CheckResult.PASS_))

    # Skip for escalation or clarification responses
    escalation_indicators = ["expert", "human", "escalat", "connect you", "support team", "specialist"]
    clarification_indicators = ["could you", "please provide", "can you tell", "what is your", "which", "let me check", "checking", "one moment"]
    if any(ind in draft_lower for ind in escalation_indicators + clarification_indicators):
        return ValidationResult(status=ValidationStatus.VALID, checks=ValidationChecks(intent_alignment=CheckResult.PASS_))

    # For specific intents, check if response is even remotely relevant
    relevant_keywords = intent_relevance.get(intent, [])
    if relevant_keywords:
        if not any(kw in draft_lower for kw in relevant_keywords):
            # Check if the response is at least addressing the user's message topic
            user_words = set(ctx.user_message.lower().split())
            draft_words = set(draft_lower.split())
            overlap = user_words & draft_words
            content_words = {w for w in overlap if len(w) > 3}

            if len(content_words) < 2:
                violations.append(ValidationViolation(
                    check_name="INTENT_ALIGNMENT",
                    violation_type="IRRELEVANT_RESPONSE",
                    reason=f"Customer intent is '{intent}' but draft does not address this topic.",
                    severity="MEDIUM",
                ))

    if violations:
        return ValidationResult(
            status=ValidationStatus.REGENERATE,
            violations=violations,
            checks=ValidationChecks(intent_alignment=CheckResult.FAIL),
        )
    return ValidationResult(status=ValidationStatus.VALID, checks=ValidationChecks(intent_alignment=CheckResult.PASS_))


def check_response_quality(ctx: ResponseValidationContext) -> ValidationResult:
    """Basic quality checks on the draft response."""
    draft = ctx.draft_response
    violations = []

    prompt_fragments = [
        "you are a helpful", "as an ai", "i am an ai language model",
        "as a language model", "as an ai i cannot", "i cannot assist as an ai", "i'm just an ai",
        "### system", "### instruction", "[INST]", "<<SYS>>",
    ]
    for frag in prompt_fragments:
        if frag in draft.lower():
            violations.append(ValidationViolation(
                check_name="RESPONSE_QUALITY",
                violation_type="PROMPT_FRAGMENT",
                reason=f"Draft contains prompt fragment: '{frag}'.",
                severity="MEDIUM",
            ))
            break

    if violations:
        return ValidationResult(
            status=ValidationStatus.REGENERATE,
            violations=violations,
            checks=ValidationChecks(response_quality=CheckResult.FAIL),
        )
    return ValidationResult(status=ValidationStatus.VALID, checks=ValidationChecks(response_quality=CheckResult.PASS_))


def check_language_consistency(ctx: ResponseValidationContext) -> ValidationResult:
    """
    Validation Rule Layer 9 (Milestone P2.5):
    Rejects draft response if it does not adhere to the conversation's active preferred language.
    If preferred_language is set (english | tamil | tanglish | hindi | hinglish),
    validates response matches that language. Returns REGENERATE on violation.
    """
    pref = (ctx.preferred_language or "").lower().strip()
    if not pref:
        return ValidationResult(status=ValidationStatus.VALID, checks=ValidationChecks(language_consistency=CheckResult.SKIP))

    draft = ctx.draft_response or ""
    words = set(re.findall(r"\b[a-zA-Z]+\b", draft.lower()))
    is_tamil_unicode = any("\u0b80" <= c <= "\u0bff" for c in draft)
    is_devanagari_unicode = any("\u0900" <= c <= "\u097f" for c in draft)
    is_hindi_unicode = is_devanagari_unicode
    is_kannada_unicode = any("\u0c80" <= c <= "\u0cff" for c in draft)
    is_telugu_unicode = any("\u0c00" <= c <= "\u0c7f" for c in draft)
    is_malayalam_unicode = any("\u0d00" <= c <= "\u0d7f" for c in draft)
    is_bengali_unicode = any("\u0980" <= c <= "\u09ff" for c in draft)
    is_gujarati_unicode = any("\u0a80" <= c <= "\u0aff" for c in draft)
    is_gurmukhi_unicode = any("\u0a00" <= c <= "\u0a7f" for c in draft)
    is_odia_unicode = any("\u0b00" <= c <= "\u0b7f" for c in draft)
    is_urdu_unicode = any("\u0600" <= c <= "\u06ff" for c in draft)
    is_any_indic_unicode = (
        is_tamil_unicode or is_devanagari_unicode or is_kannada_unicode or
        is_telugu_unicode or is_malayalam_unicode or is_bengali_unicode or
        is_gujarati_unicode or is_gurmukhi_unicode or is_odia_unicode or is_urdu_unicode
    )

    if pref in ("tanglish",):
        tanglish_markers = {
            "seri", "bro", "unga", "ungala", "ungallukku", "ungalukku", "enna", "venum",
            "panren", "pannunga", "pannanum", "pesalam", "pesunga", "irukku", "illai", "illa",
            "kavalapadatheenga", "kandippa", "aiyo", "romba", "mudiyum", "mudiyala", "kettukren",
            "oru", "nimisham", "enaku", "unakku", "paakren", "sollunga", "puriyudhu", "tharen",
            "kudunga", "vaanga", "ponga", "aachu", "aayiduchu", "namma", "padi", "kulla", "aana",
            "apram", "solren", "therinjikonga", "mudiyadhu", "vandhudum", "irukanum", "aagum",
            "pathi", "pathie", "pannalam", "anupuvom", "kedaikkum", "kedaikum", "idhu", "adha", "edhavadhu",
            "saaman", "porul", "reach", "parsal", "panam", "kaasu", "thirupi", "thiruppi", "innum", "varala"
        }
        from app.ai.intelligence.language import CodeMixedLanguageDetector
        cm_res = CodeMixedLanguageDetector().detect(draft)
        has_tanglish_marker = any(w in words for w in tanglish_markers)
        if not has_tanglish_marker and cm_res.is_code_mixed and cm_res.code_mix_type == "tanglish":
            has_tanglish_marker = True

        # Check morphological patterns for naturally generated Tanglish with unseen vocabulary
        is_tanglish_candidate = (
            has_tanglish_marker
            or is_tamil_unicode
            or any(re.search(pat, draft.lower()) for pat in [
                r"\b\w+(?:unga|aachu|aayiduchu|aagala|iduchu|aam|aadh|adha|ren|rom|num|ley|leye|oda|kku|ukku|la|pa|da)\b",
                r"\b(?:naan|neenga|adh|idhu|edhu|yaar|enna|enga|eppo|eppadi|epdi|apdi|ipdi|oru|sila|nalla|romba|konjam|seri|sari|mudiy|theriy|puriy|saaman|porul|kaasu|panam|vandi|kadai|veedu|varal|vandh|anup|solren|solla|sollu)\w*\b"
            ])
        )

        if not is_tanglish_candidate:
            # If detector cannot confidently determine language and this is attempt 2+, avoid an unjustified loop
            if cm_res.confidence < 0.70 and getattr(ctx, "attempt_number", 1) >= 2:
                return ValidationResult(status=ValidationStatus.VALID, checks=ValidationChecks(language_consistency=CheckResult.PASS_))
            return ValidationResult(
                status=ValidationStatus.REGENERATE,
                violations=[
                    ValidationViolation(
                        check_name="LANGUAGE_CONSISTENCY",
                        violation_type="WRONG_LANGUAGE",
                        reason="Caller preferred language is Tanglish, but draft response contains no Tanglish words (appears to be plain English).",
                        severity="HIGH"
                    )
                ],
                checks=ValidationChecks(language_consistency=CheckResult.FAIL),
                reasons=["Respond in conversational Tanglish in English letters (e.g. 'Sari, Tanglish-la pesalam. Enna help venum?')."]
            )

    elif pref in ("tamil", "ta", "ta-in"):
        if not is_tamil_unicode:
            return ValidationResult(
                status=ValidationStatus.REGENERATE,
                violations=[
                    ValidationViolation(
                        check_name="LANGUAGE_CONSISTENCY",
                        violation_type="WRONG_LANGUAGE",
                        reason="Caller preferred language is Tamil, but draft response lacks Tamil script (தமிழ்).",
                        severity="HIGH"
                    )
                ],
                checks=ValidationChecks(language_consistency=CheckResult.FAIL),
                reasons=["Respond in Tamil script (தமிழ்)."]
            )

    elif pref in ("hindi", "hi", "hi-in"):
        if not is_hindi_unicode:
            return ValidationResult(
                status=ValidationStatus.REGENERATE,
                violations=[
                    ValidationViolation(
                        check_name="LANGUAGE_CONSISTENCY",
                        violation_type="WRONG_LANGUAGE",
                        reason="Caller preferred language is Hindi, but draft response lacks Devanagari script (हिन्दी).",
                        severity="HIGH"
                    )
                ],
                checks=ValidationChecks(language_consistency=CheckResult.FAIL),
                reasons=["Respond in Hindi script (हिन्दी)."]
            )

    elif pref in ("hinglish",):
        hinglish_markers = {
            "haan", "ji", "theek", "hai", "bilkul", "aap", "aapka", "kya", "kaise",
            "kar", "karo", "karta", "karenge", "mera", "meri", "hum", "sunte", "hain",
            "pareshan", "mat", "hoiye", "ek", "second", "bhai", "bataiye", "raha", "rahi",
            "saman", "cheez", "paisa", "paise", "wapas", "milega", "kab", "kahan"
        }
        from app.ai.intelligence.language import CodeMixedLanguageDetector
        cm_res = CodeMixedLanguageDetector().detect(draft)
        has_hinglish_marker = any(w in words for w in hinglish_markers)
        if not has_hinglish_marker and cm_res.is_code_mixed and cm_res.code_mix_type == "hinglish":
            has_hinglish_marker = True

        # Check morphological patterns for naturally generated Hinglish with unseen vocabulary
        is_hinglish_candidate = (
            has_hinglish_marker
            or is_hindi_unicode
            or any(re.search(pat, draft.lower()) for pat in [
                r"\b\w+(?:ega|egi|enge|iye|iyega|gaya|gayi|gaye|raha|rahi|rahe|wala|wali|kar|karta|karte|karti|hota|hote|hoti)\b",
                r"\b(?:main|hum|aap|tum|mera|meri|mere|tera|uska|iski|kya|kyun|kaise|kab|kahan|nahi|mat|haan|theek|accha|bahut|thoda|paisa|saman|cheez|bhejne|dena|lena|chahiye)\b"
            ])
        )

        if not is_hinglish_candidate:
            if cm_res.confidence < 0.70 and getattr(ctx, "attempt_number", 1) >= 2:
                return ValidationResult(status=ValidationStatus.VALID, checks=ValidationChecks(language_consistency=CheckResult.PASS_))
            return ValidationResult(
                status=ValidationStatus.REGENERATE,
                violations=[
                    ValidationViolation(
                        check_name="LANGUAGE_CONSISTENCY",
                        violation_type="WRONG_LANGUAGE",
                        reason="Caller preferred language is Hinglish, but draft response contains no Hinglish markers (appears to be plain English).",
                        severity="HIGH"
                    )
                ],
                checks=ValidationChecks(language_consistency=CheckResult.FAIL),
                reasons=["Respond in conversational Hinglish (e.g. 'Haan ji, main aapki kya help kar sakta hoon?')."]
            )

    elif pref in ("kannada", "kn", "kn-in"):
        if not (is_kannada_unicode or any(w in words for w in ["nimma", "namma", "kanditha", "thilisi", "namaskara", "madthini", "haudu", "illa", "dayavittu"])):
            return ValidationResult(
                status=ValidationStatus.REGENERATE,
                violations=[
                    ValidationViolation(
                        check_name="LANGUAGE_CONSISTENCY",
                        violation_type="WRONG_LANGUAGE",
                        reason="Caller preferred language is Kannada, but draft response lacks Kannada script or vocabulary.",
                        severity="HIGH"
                    )
                ],
                checks=ValidationChecks(language_consistency=CheckResult.FAIL),
                reasons=["Respond in Kannada script (ಕನ್ನಡ)."]
            )

    elif pref in ("kanglish",):
        if not (is_kannada_unicode or any(w in words for w in ["nimma", "namma", "kanditha", "thilisi", "namaskara", "madthini", "haudu", "illa", "dayavittu", "hege", "saaman"])):
            return ValidationResult(
                status=ValidationStatus.REGENERATE,
                violations=[
                    ValidationViolation(
                        check_name="LANGUAGE_CONSISTENCY",
                        violation_type="WRONG_LANGUAGE",
                        reason="Caller preferred language is Kanglish, but draft response contains no Kanglish markers.",
                        severity="HIGH"
                    )
                ],
                checks=ValidationChecks(language_consistency=CheckResult.FAIL),
                reasons=["Respond in conversational Kanglish."]
            )

    elif pref in ("telugu", "te", "te-in"):
        telugu_words = [
            "mee", "maa", "kachithanga", "cheppandi", "namaskaram", "avunu", "kaadu", "dayachesi",
            "aina", "cheyyochu", "cheyyachu", "mundu", "lo", "gurinchi", "kavali", "undi", "ledu",
            "chesi", "cheyyandi", "ayindi", "avvaledu", "chesaru", "chesthanu", "chestunnanu", "chusthanu",
            "kuda", "mariyu", "telugu"
        ]
        if not (is_telugu_unicode or any(w in words for w in telugu_words)):
            return ValidationResult(
                status=ValidationStatus.REGENERATE,
                violations=[
                    ValidationViolation(
                        check_name="LANGUAGE_CONSISTENCY",
                        violation_type="WRONG_LANGUAGE",
                        reason="Caller preferred language is Telugu, but draft response lacks Telugu script or vocabulary.",
                        severity="HIGH"
                    )
                ],
                checks=ValidationChecks(language_consistency=CheckResult.FAIL),
                reasons=["Respond in Telugu script (తెలుగు)."]
            )

    elif pref in ("tenglish",):
        tenglish_words = [
            "mee", "maa", "kachithanga", "cheppandi", "namaskaram", "avunu", "kaadu", "dayachesi",
            "ela", "aina", "cheyyochu", "cheyyachu", "mundu", "lo", "gurinchi", "kavali", "undi", "ledu",
            "chesi", "cheyyandi", "ayindi", "avvaledu", "chesaru", "chesthanu", "chestunnanu", "chusthanu",
            "kuda", "mariyu", "telugu"
        ]
        if not (is_telugu_unicode or any(w in words for w in tenglish_words)):
            return ValidationResult(
                status=ValidationStatus.REGENERATE,
                violations=[
                    ValidationViolation(
                        check_name="LANGUAGE_CONSISTENCY",
                        violation_type="WRONG_LANGUAGE",
                        reason="Caller preferred language is Tenglish, but draft response contains no Tenglish markers.",
                        severity="HIGH"
                    )
                ],
                checks=ValidationChecks(language_consistency=CheckResult.FAIL),
                reasons=["Respond in conversational Tenglish."]
            )

    elif pref in ("malayalam", "ml", "ml-in"):
        if not (is_malayalam_unicode or any(w in words for w in ["ningalude", "njangalude", "theerchayayum", "parayamo", "namaskaram", "athe", "alla", "dayavayi"])):
            return ValidationResult(
                status=ValidationStatus.REGENERATE,
                violations=[
                    ValidationViolation(
                        check_name="LANGUAGE_CONSISTENCY",
                        violation_type="WRONG_LANGUAGE",
                        reason="Caller preferred language is Malayalam, but draft response lacks Malayalam script or vocabulary.",
                        severity="HIGH"
                    )
                ],
                checks=ValidationChecks(language_consistency=CheckResult.FAIL),
                reasons=["Respond in Malayalam script (മലയാളം)."]
            )

    elif pref in ("manglish",):
        if not (is_malayalam_unicode or any(w in words for w in ["ningalude", "njangalude", "theerchayayum", "parayamo", "namaskaram", "athe", "alla", "dayavayi", "engane"])):
            return ValidationResult(
                status=ValidationStatus.REGENERATE,
                violations=[
                    ValidationViolation(
                        check_name="LANGUAGE_CONSISTENCY",
                        violation_type="WRONG_LANGUAGE",
                        reason="Caller preferred language is Manglish, but draft response contains no Manglish markers.",
                        severity="HIGH"
                    )
                ],
                checks=ValidationChecks(language_consistency=CheckResult.FAIL),
                reasons=["Respond in conversational Manglish."]
            )

    elif pref in ("bengali", "bn", "bn-in", "benglish"):
        if not (is_bengali_unicode or any(w in words for w in ["apanar", "amader", "nishchoi", "bolun", "nomoshkar", "kotha"])):
            return ValidationResult(
                status=ValidationStatus.REGENERATE,
                violations=[
                    ValidationViolation(
                        check_name="LANGUAGE_CONSISTENCY",
                        violation_type="WRONG_LANGUAGE",
                        reason="Caller preferred language is Bengali, but draft response lacks Bengali script or vocabulary.",
                        severity="HIGH"
                    )
                ],
                checks=ValidationChecks(language_consistency=CheckResult.FAIL),
                reasons=["Respond in Bengali (বাংলা)."]
            )

    elif pref in ("marathi", "mr", "mr-in", "marathish"):
        if not (is_devanagari_unicode or any(w in words for w in ["tumcha", "amcha", "nakkich", "sanga", "namaskar", "boluya"])):
            return ValidationResult(
                status=ValidationStatus.REGENERATE,
                violations=[
                    ValidationViolation(
                        check_name="LANGUAGE_CONSISTENCY",
                        violation_type="WRONG_LANGUAGE",
                        reason="Caller preferred language is Marathi, but draft response lacks Marathi script or vocabulary.",
                        severity="HIGH"
                    )
                ],
                checks=ValidationChecks(language_consistency=CheckResult.FAIL),
                reasons=["Respond in Marathi (मराठी)."]
            )

    elif pref in ("gujarati", "gu", "gu-in", "gujlish"):
        if not (is_gujarati_unicode or any(w in words for w in ["tamaro", "amaro", "chokkas", "janavo", "namaste", "kari"])):
            return ValidationResult(
                status=ValidationStatus.REGENERATE,
                violations=[
                    ValidationViolation(
                        check_name="LANGUAGE_CONSISTENCY",
                        violation_type="WRONG_LANGUAGE",
                        reason="Caller preferred language is Gujarati, but draft response lacks Gujarati script or vocabulary.",
                        severity="HIGH"
                    )
                ],
                checks=ValidationChecks(language_consistency=CheckResult.FAIL),
                reasons=["Respond in Gujarati (ગુજરાતી)."]
            )

    elif pref in ("punjabi", "pa", "pa-in", "punglish"):
        if not (is_gurmukhi_unicode or any(w in words for w in ["tuhada", "sada", "zaroor", "dasso", "sat", "sri", "akal", "karo"])):
            return ValidationResult(
                status=ValidationStatus.REGENERATE,
                violations=[
                    ValidationViolation(
                        check_name="LANGUAGE_CONSISTENCY",
                        violation_type="WRONG_LANGUAGE",
                        reason="Caller preferred language is Punjabi, but draft response lacks Punjabi script or vocabulary.",
                        severity="HIGH"
                    )
                ],
                checks=ValidationChecks(language_consistency=CheckResult.FAIL),
                reasons=["Respond in Punjabi (ਪੰਜਾਬੀ)."]
            )

    elif pref in ("english", "en", "en-in", "en-us"):
        if is_any_indic_unicode:
            return ValidationResult(
                status=ValidationStatus.REGENERATE,
                violations=[
                    ValidationViolation(
                        check_name="LANGUAGE_CONSISTENCY",
                        violation_type="WRONG_LANGUAGE",
                        reason="Caller preferred language is English, but draft response contains non-English native script.",
                        severity="HIGH"
                    )
                ],
                checks=ValidationChecks(language_consistency=CheckResult.FAIL),
                reasons=["Respond in English only."]
            )

    return ValidationResult(status=ValidationStatus.VALID, checks=ValidationChecks(language_consistency=CheckResult.PASS_))

 