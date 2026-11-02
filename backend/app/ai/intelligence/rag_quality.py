"""
Capability 2: Advanced RAG Quality Verification

Verifies that RAG retrieval results are relevant, non-contradictory,
and properly sourced. Detects hallucination risk and stale content.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RAGQualityResult:
    """Result of RAG quality verification."""
    is_relevant: bool = False
    relevance_score: float = 0.0       # 0-1
    has_contradiction: bool = False
    contradiction_details: str = ""
    hallucination_risk: float = 0.0    # 0-1
    freshness_ok: bool = True
    source_verified: bool = False
    quality_grade: str = "F"           # A, B, C, D, F
    issues: List[str] = field(default_factory=list)


class RAGQualityVerifier:
    """
    Validates RAG retrieval results for quality, relevance, and safety.
    Runs after retrieval but before response generation.
    """

    RELEVANCE_THRESHOLD = 0.1       # Minimum relevance score
    HIGH_RELEVANCE_THRESHOLD = 0.3  # Good relevance

    def verify(
        self,
        query: str,
        rag_results: List[Dict[str, Any]],
        intent: str = "",
    ) -> RAGQualityResult:
        """
        Verify the quality of RAG retrieval results.
        
        Args:
            query: The original search query
            rag_results: List of retrieved articles/chunks
            intent: Detected customer intent
        
        Returns:
            RAGQualityResult with quality assessment.
        """
        result = RAGQualityResult()
        issues: List[str] = []

        if not rag_results:
            result.quality_grade = "F"
            result.issues = ["No RAG results retrieved"]
            return result

        # 1. Relevance check
        relevance = self._check_relevance(query, rag_results, intent)
        result.relevance_score = relevance
        result.is_relevant = relevance >= self.RELEVANCE_THRESHOLD

        if not result.is_relevant:
            issues.append(f"Low relevance score: {relevance:.2f}")

        # 2. Contradiction detection
        has_contradiction, details = self._check_contradictions(rag_results)
        result.has_contradiction = has_contradiction
        result.contradiction_details = details
        if has_contradiction:
            issues.append(f"Contradiction detected: {details}")

        # 3. Hallucination risk assessment
        result.hallucination_risk = self._assess_hallucination_risk(
            query, rag_results, intent
        )
        if result.hallucination_risk > 0.6:
            issues.append(f"High hallucination risk: {result.hallucination_risk:.2f}")

        # 4. Source verification
        result.source_verified = self._verify_sources(rag_results)
        if not result.source_verified:
            issues.append("Source verification failed")

        # 5. Freshness check
        result.freshness_ok = self._check_freshness(rag_results)
        if not result.freshness_ok:
            issues.append("Stale content detected")

        # 6. Grade assignment
        result.quality_grade = self._assign_grade(result)
        result.issues = issues

        return result

    def _check_relevance(
        self,
        query: str,
        results: List[Dict[str, Any]],
        intent: str,
    ) -> float:
        """Check result relevance via score and keyword overlap."""
        if not results:
            return 0.0

        # Use existing similarity scores if available
        scores = [r.get("score", 0) for r in results]
        best_score = max(scores) if scores else 0.0

        # Keyword overlap check
        query_words = set(re.findall(r'\b\w{3,}\b', query.lower()))
        if query_words:
            best_overlap = 0.0
            for r in results:
                content = (r.get("title", "") + " " + r.get("content", "")).lower()
                content_words = set(re.findall(r'\b\w{3,}\b', content))
                if content_words:
                    overlap = len(query_words & content_words) / len(query_words)
                    best_overlap = max(best_overlap, overlap)
            
            # Combine score and keyword overlap
            return (best_score * 0.6 + best_overlap * 0.4)

        return best_score

    def _check_contradictions(self, results: List[Dict[str, Any]]) -> tuple[bool, str]:
        """Check for contradictions between retrieved articles."""
        if len(results) < 2:
            return False, ""

        # Simple contradiction detection: look for opposing statements
        contradiction_pairs = [
            ("refund", "non-refundable"),
            ("free", "charges apply"),
            ("available", "unavailable"),
            ("supported", "not supported"),
        ]

        contents = [r.get("content", "").lower() for r in results]
        
        for positive, negative in contradiction_pairs:
            has_positive = any(positive in c for c in contents)
            has_negative = any(negative in c for c in contents)
            if has_positive and has_negative:
                return True, f"Conflicting information about '{positive}'"

        return False, ""

    def _assess_hallucination_risk(
        self,
        query: str,
        results: List[Dict[str, Any]],
        intent: str,
    ) -> float:
        """Assess the risk of hallucination if we use these results."""
        risk = 0.0

        # Low relevance = high hallucination risk
        scores = [r.get("score", 0) for r in results]
        best_score = max(scores) if scores else 0.0
        if best_score < 0.1:
            risk += 0.4
        elif best_score < 0.2:
            risk += 0.2

        # Specific intents with no matching category
        result_categories = {r.get("category", "").lower() for r in results}
        intent_categories = {
            "PAYMENT_ISSUE": {"payment", "billing", "refund"},
            "DELIVERY_ISSUE": {"delivery", "shipping", "logistics"},
            "SECURITY_ISSUE": {"security", "account"},
            "LOGIN_ISSUE": {"account", "login", "auth"},
        }
        
        expected = intent_categories.get(intent, set())
        if expected and not (expected & result_categories):
            risk += 0.3

        # Very short content → higher risk
        for r in results:
            if len(r.get("content", "")) < 20:
                risk += 0.1
                break

        return min(1.0, risk)

    def _verify_sources(self, results: List[Dict[str, Any]]) -> bool:
        """Verify that results have proper source attribution."""
        for r in results:
            if r.get("id") and r.get("title"):
                return True  # At least one properly sourced result
        return False

    def _check_freshness(self, results: List[Dict[str, Any]]) -> bool:
        """Check that results are not marked as stale/archived."""
        for r in results:
            if r.get("is_archived") or r.get("is_stale"):
                return False
        return True

    def _assign_grade(self, result: RAGQualityResult) -> str:
        """Assign a letter grade to the RAG quality."""
        score = 0
        
        if result.is_relevant:
            score += 30
        if result.relevance_score > self.HIGH_RELEVANCE_THRESHOLD:
            score += 20
        if not result.has_contradiction:
            score += 15
        if result.hallucination_risk < 0.3:
            score += 15
        if result.source_verified:
            score += 10
        if result.freshness_ok:
            score += 10

        if score >= 85:
            return "A"
        if score >= 70:
            return "B"
        if score >= 55:
            return "C"
        if score >= 40:
            return "D"
        return "F"


class QueryPreprocessor:
    """
    Preprocesses queries before RAG retrieval to improve result quality.
    """

    def preprocess(self, query: str, intent: str = "", entities: Dict[str, str] = None) -> str:
        """
        Preprocess the query for better RAG retrieval.
        
        Adds intent context and entity information to improve matches.
        """
        parts = [query]

        # Add intent as context
        if intent:
            intent_readable = intent.replace("_", " ").lower()
            parts.append(intent_readable)

        # Add entity values
        if entities:
            for key, value in entities.items():
                parts.append(f"{key.replace('_', ' ')}: {value}")

        return " ".join(parts)

    def deduplicate_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate results based on article ID."""
        seen_ids = set()
        unique = []
        for r in results:
            rid = r.get("id", id(r))
            if rid not in seen_ids:
                seen_ids.add(rid)
                unique.append(r)
        return unique
