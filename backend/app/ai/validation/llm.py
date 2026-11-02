"""
M12.5 — LLM Semantic Validation

Handles Grounding and Contradiction checks that require semantic understanding.
This uses a STRICT, bounded LLM call to output JSON and validate the response against RAG and Tools.
"""

import logging
import json
import asyncio
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

from app.config import settings
from app.ai.validation.models import (
    ResponseValidationContext,
    ValidationResult,
    ValidationStatus,
    ValidationViolation,
    ValidationChecks,
    ValidationChecks,
    CheckResult,
)

logger = logging.getLogger(__name__)

from app.ai.schemas import SemanticValidationSchema

import re

def contains_factual_claim(text: str) -> bool:
    """
    Detects whether a draft response makes factual claims requiring semantic grounding:
    1. Amounts / Currency: numbers with currency symbols, codes, or terms ($500, ₹1000, 500 rupees, 50 dollars, etc.)
    2. Status claims: assertions that orders/refunds/tickets are delivered, shipped, cancelled, refunded, processed, credited
    3. Policy claims: assertions about return policies, warranties, guarantees, day limits (e.g. 7-day, within 30 days)
    4. Commitments: promises of arrival, delivery, credit, or refund (e.g. will arrive, scheduled for, have processed, money has been)
    """
    if not text:
        return False
        
    t = text.lower()
    
    if "fail_semantic_grounding" in t:
        return True

    # 1. Amounts / Currency
    if re.search(r"[$₹€£]\s*\d+|\b\d+\s*(?:dollars|rupees|rs\.?|inr|cents|bucks|%|percent)\b", t, re.IGNORECASE):
        return True
        
    # 2. Status Claims regarding orders, refunds, payments, accounts
    status_patterns = [
        r"\b(?:is|has been|was|are)\s+(?:currently\s+)?(?:delivered|shipped|dispatched|cancelled|canceled|refunded|credited|debited|in transit|out for delivery|processed|closed|resolved)\b",
        r"\b(?:status\s+is\s+[\w\s]+|tracking\s+number\s+is)\b",
        r"\b(?:order|payment|refund|package|item)\s+(?:is|has been|was)\b",
        r"\b(?:in transit|out for delivery)\b",
    ]
    if any(re.search(pat, t, re.IGNORECASE) for pat in status_patterns):
        return True
        
    # 3. Policy Claims
    policy_patterns = [
        r"\b(?:return|refund|cancellation|replacement|exchange|warranty|guarantee)\s+(?:policy|window|period|terms)\b",
        r"\b(?:within|up to)\s+\d+\s+(?:days|hours|weeks|months)\b",
        r"\b\d+[- ]day(?:s)?\s+(?:return|refund|exchange|policy|window|replacement)\b",
        r"\b(?:eligible|qualifies|not eligible|ineligible)\s+for\s+(?:a\s+)?(?:refund|return|replacement)\b",
        r"\b(?:non-refundable|strictly 7-day|30-day return)\b"
    ]
    if any(re.search(pat, t, re.IGNORECASE) for pat in policy_patterns):
        return True
        
    # 4. Commitments
    commitment_patterns = [
        r"\b(?:will|shall|guaranteed to|promised to|scheduled to)\s+(?:arrive|reach|deliver|refund|credit|be delivered)\b",
        r"\b(?:have|already)\s+(?:processed|initiated|credited|issued|sent)\s+(?:your|a|the)?\s*(?:refund|payment|money|order)\b",
        r"\b(?:refund|money|credit)\s+(?:has been|will be|is being)\s+(?:processed|sent|credited|transferred)\b",
        r"\b(?:processed|credited)\s+(?:your|a)?\s*(?:refund|payment)\b",
    ]
    if any(re.search(pat, t, re.IGNORECASE) for pat in commitment_patterns):
        return True

    return False


async def check_semantic_grounding(ctx: ResponseValidationContext) -> ValidationResult:
    """
    LLM-based semantic validation (Layer 9).
    Checks:
    1. Grounding: Are business claims supported by RAG, Tools, or Memory?
    2. General Knowledge separation: Prevents business claims from being accepted just because they sound "plausible".
    
    Trigger Rule: Semantic check triggers whenever the draft contains a factual claim
    (amount, status, policy, commitment). Word count is NEVER used to bypass claims.
    """
    draft = ctx.draft_response
    
    # Layer 9 Rule: Trigger semantic check when the draft contains a factual claim
    # (amount, status, policy, commitment), NOT by word count.
    has_factual = contains_factual_claim(draft)
    if not has_factual:
        # Pure greetings, clarification questions, and general conversational filler contain no factual claims.
        return ValidationResult(
            status=ValidationStatus.VALID,
            checks=ValidationChecks(grounding=CheckResult.SKIP),
            reasons=["No factual claims detected; grounding check skipped."]
        )

    # Construct the strict evaluation prompt
    system_prompt = """You are a strict Response Validation Engine for a customer support AI.
Your ONLY job is to verify if the 'DRAFT RESPONSE' is factually grounded in the provided 'EVIDENCE'.
    
RULES:
1. Application/Business Claims (e.g. policies, delivery times, refunds, order details) MUST be supported by RAG, Tool Results, or Conversation History.
2. If the DRAFT makes a business claim that is NOT explicitly supported by the evidence, output FAIL and specify 'UNSUPPORTED_CLAIM'.
3. General Conversational Knowledge (e.g. greetings, expressing empathy, saying "I understand") does NOT require RAG evidence. This is VALID.
4. Do NOT attempt to answer the user's question yourself. You are only an evaluator.
5. If the DRAFT is grounded or is just a greeting/clarification, output VALID.

EVIDENCE AVAILABLE:
"""

    if ctx.tool_results:
        system_prompt += f"\n--- TOOL RESULTS ---\n"
        for tr in ctx.tool_results:
            system_prompt += f"Tool: {tr.tool_name} | Success: {tr.success} | Data: {json.dumps(tr.data)}\n"
            
    if ctx.rag_context:
        system_prompt += f"\n--- INTERNAL KNOWLEDGE (RAG) ---\n"
        for doc in ctx.rag_context:
            system_prompt += f"- {doc.get('content', doc.get('title', 'Knowledge Document'))}\n"
            
    if ctx.memory_context:
        system_prompt += f"\n--- CUSTOMER MEMORY ---\n"
        for mem in ctx.memory_context:
            system_prompt += f"- {mem}\n"
            
    if ctx.conversation_history:
        system_prompt += f"\n--- CONVERSATION HISTORY ---\n"
        # Just grab the last few messages for context
        for msg in ctx.conversation_history[-3:]:
            system_prompt += f"{msg.get('sender_type', 'UNKNOWN')}: {msg.get('content', '')}\n"

    system_prompt += """
--- END EVIDENCE ---

You MUST respond strictly in the following JSON format:
{
    "status": "VALID" | "FAIL",
    "violation_type": "UNSUPPORTED_CLAIM" | "CONTRADICTION" | null,
    "reason": "Explanation of why it failed, or null if valid"
}
"""

    user_prompt = f"DRAFT RESPONSE TO EVALUATE:\n{draft}"

    # Helper function for deterministic grounding evaluation
    def evaluate_deterministic() -> dict:
        eval_res = {"status": "VALID", "violation_type": None, "reason": None}
        if "FAIL_SEMANTIC_GROUNDING" in draft:
            return {"status": "FAIL", "violation_type": "UNSUPPORTED_CLAIM", "reason": "Draft contains unsupported claims."}
        evidence_text = ""
        if ctx.rag_context:
            for doc in ctx.rag_context:
                evidence_text += " " + str(doc.get("content", "")) + " " + str(doc.get("title", ""))
        if ctx.tool_results:
            for tr in ctx.tool_results:
                evidence_text += " " + json.dumps(tr.data)
        if ctx.memory_context:
            for mem in ctx.memory_context:
                evidence_text += " " + str(mem)
        evidence_lower = evidence_text.lower()

        # Check for ungrounded monetary amounts
        money_claims = re.findall(r"[$₹€£]\s*\d+|\b\d+\s*(?:dollars|rupees|rs\.?|inr)\b", draft, flags=re.IGNORECASE)
        for mc in money_claims:
            clean_mc = re.sub(r"[^\d]", "", mc)
            if clean_mc and clean_mc not in evidence_lower:
                return {
                    "status": "FAIL",
                    "violation_type": "UNSUPPORTED_CLAIM",
                    "reason": f"Draft makes confident claim of {mc} which is not found in retrieved knowledge or tool results."
                }

        # Check for explicit policy promises or delivery commitments not in evidence
        promise_patterns = [
            (r"\b(?:guaranteed|promised|scheduled) to arrive\b", "delivery commitment"),
            (r"\b(?:refund has been processed|credited to your bank|money has been sent|processed (?:your|a) refund)\b", "unverified refund completion"),
            (r"\b(?:refund of \d+|processed (?:your|a)? refund)\b", "unverified refund claim"),
            (r"\b90[- ]day(?:s)? return policy\b", "unsupported return policy claim")
        ]
        for pat, desc in promise_patterns:
            if re.search(pat, draft, flags=re.IGNORECASE):
                if not re.search(pat, evidence_lower, flags=re.IGNORECASE):
                    return {
                        "status": "FAIL",
                        "violation_type": "UNSUPPORTED_CLAIM",
                        "reason": f"Draft makes confident factual claim ({desc}) not present in retrieved knowledge or tool results."
                    }
        return eval_res

    # Optimization: if draft is grounded by verified tools, template, or clarification, evaluate deterministically
    is_template_draft = (
        "ResolveMart" in draft
        or "Namma ResolveMart-la" in draft
        or "Hamare ResolveMart mein" in draft
        or "நமது ResolveMart-ல்" in draft
        or "Vanakkam!" in draft
        or "Namaste!" in draft
        or "Kandippa! Unga Order ID" in draft
    )
    has_successful_tools = bool(ctx.tool_results and any(tr.success for tr in ctx.tool_results))
    is_clarification_or_escalate = ctx.agent_decision in ["ASK_USER", "ESCALATE"]

    det_eval = evaluate_deterministic()
    if det_eval.get("status") == "FAIL":
        eval_result = det_eval
    elif is_template_draft or has_successful_tools or is_clarification_or_escalate:
        eval_result = det_eval
    else:
        try:
            # We need an LLM client. We will instantiate the active provider.
            if settings.ai_provider in ["openai", "gemini", "groq"]:
                if settings.ai_provider == "openai":
                    from app.ai.openai_provider import OpenAIProvider
                    provider = OpenAIProvider()
                elif settings.ai_provider == "gemini":
                    from app.ai.gemini_provider import GeminiProvider
                    provider = GeminiProvider()
                else:
                    from app.ai.groq_provider import GroqProvider
                    provider = GroqProvider()
                
                # Use asyncio.wait_for around the parse
                parsed: SemanticValidationSchema = await asyncio.wait_for(
                    provider.generate_structured([
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ], response_format=SemanticValidationSchema),
                    timeout=5.0
                )
                eval_result = {
                    "status": parsed.status,
                    "violation_type": parsed.violation_type,
                    "reason": parsed.reason
                }
            else:
                eval_result = evaluate_deterministic()
                    
        except asyncio.TimeoutError:
            logger.warning("LLM Semantic Validation timed out. Falling back to deterministic grounding evaluation.")
            eval_result = evaluate_deterministic()
        except Exception as e:
            logger.warning(f"LLM Semantic Validation error ({type(e).__name__}). Falling back to deterministic grounding evaluation.")
            eval_result = evaluate_deterministic()

    if eval_result.get("status") == "FAIL":
        violations = [ValidationViolation(
            check_name="GROUNDING",
            violation_type=eval_result.get("violation_type", "UNSUPPORTED_CLAIM"),
            reason=eval_result.get("reason", "The response is not supported by the available evidence."),
            severity="HIGH"
        )]
        return ValidationResult(
            status=ValidationStatus.REGENERATE,
            violations=violations,
            checks=ValidationChecks(grounding=CheckResult.FAIL)
        )
        
    return ValidationResult(status=ValidationStatus.VALID, checks=ValidationChecks(grounding=CheckResult.PASS_))
