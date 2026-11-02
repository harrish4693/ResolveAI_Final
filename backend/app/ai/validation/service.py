"""
M12.5 — Validation Service

Coordinates the validation rules sequentially.
If a deterministic rule fails with ESCALATE, it short-circuits.
If a rule returns REGENERATE, it aggregates the violations and returns.
"""

import logging

from app.ai.validation.models import (
    ResponseValidationContext,
    ValidationResult,
    ValidationStatus,
    ValidationChecks,
)
from app.ai.validation.rules import (
    check_structural,
    check_security,
    check_tool_truthfulness,
    check_action_truthfulness,
    check_contradiction,
    check_memory_consistency,
    check_intent_alignment,
    check_response_quality,
    check_language_consistency,
)
from app.ai.validation.llm import check_semantic_grounding

logger = logging.getLogger(__name__)


class ValidationService:

    @classmethod
    async def validate_response(cls, ctx: ResponseValidationContext) -> ValidationResult:
        final_result = ValidationResult(status=ValidationStatus.VALID)
        
        struct_res = check_structural(ctx)
        cls._merge_result(final_result, struct_res)
        if final_result.status == ValidationStatus.ESCALATE: 
            logger.info(f"Validation ESCALATE. Violations: {[v.violation_type for v in final_result.violations]}")
            return final_result
        
        sec_res = check_security(ctx)
        cls._merge_result(final_result, sec_res)
        if final_result.status == ValidationStatus.ESCALATE: 
            logger.info(f"Validation ESCALATE. Violations: {[v.violation_type for v in final_result.violations]}")
            return final_result
        
        tool_res = check_tool_truthfulness(ctx)
        cls._merge_result(final_result, tool_res)
        if final_result.status == ValidationStatus.ESCALATE: 
            logger.info(f"Validation ESCALATE. Violations: {[v.violation_type for v in final_result.violations]}")
            return final_result
        
        action_res = check_action_truthfulness(ctx)
        cls._merge_result(final_result, action_res)
        if final_result.status == ValidationStatus.ESCALATE: 
            logger.info(f"Validation ESCALATE. Violations: {[v.violation_type for v in final_result.violations]}")
            return final_result
        
        contra_res = check_contradiction(ctx)
        cls._merge_result(final_result, contra_res)
        if final_result.status == ValidationStatus.ESCALATE: 
            logger.info(f"Validation ESCALATE. Violations: {[v.violation_type for v in final_result.violations]}")
            return final_result
        
        mem_res = check_memory_consistency(ctx)
        cls._merge_result(final_result, mem_res)
        if final_result.status == ValidationStatus.ESCALATE: 
            logger.info(f"Validation ESCALATE. Violations: {[v.violation_type for v in final_result.violations]}")
            return final_result
        
        intent_res = check_intent_alignment(ctx)
        cls._merge_result(final_result, intent_res)
        if final_result.status == ValidationStatus.ESCALATE: 
            logger.info(f"Validation ESCALATE. Violations: {[v.violation_type for v in final_result.violations]}")
            return final_result
        
        if final_result.status == ValidationStatus.VALID:
            ground_res = await check_semantic_grounding(ctx)
            cls._merge_result(final_result, ground_res)
            
        qual_res = check_response_quality(ctx)
        cls._merge_result(final_result, qual_res)

        lang_res = check_language_consistency(ctx)
        cls._merge_result(final_result, lang_res)
        
        if final_result.status != ValidationStatus.VALID:
            logger.info(f"Response validation failed with status {final_result.status}. Violations: {[v.violation_type for v in final_result.violations]}")
            
        return final_result

    @staticmethod
    def _merge_result(final: ValidationResult, current: ValidationResult):
        """Merges the results, taking the most severe status."""
        final.violations.extend(current.violations)
        final.reasons.extend(current.reasons)
        
        # Update individual check statuses
        for field in current.checks.__dataclass_fields__:
            val = getattr(current.checks, field)
            if val != "SKIP":
                setattr(final.checks, field, val)

        # Status hierarchy: ESCALATE > REGENERATE > ASK_CLARIFICATION > VALID
        status_priority = {
            ValidationStatus.ESCALATE: 4,
            ValidationStatus.REGENERATE: 3,
            ValidationStatus.ASK_CLARIFICATION: 2,
            ValidationStatus.VALID: 1,
        }
        
        if status_priority[current.status] > status_priority[final.status]:
            final.status = current.status
