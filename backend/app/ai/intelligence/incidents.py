"""
Capability 8: Cross-Ticket Incident Discovery

Identifies relationships between apparently different tickets to detect
underlying incidents (e.g., multiple customers reporting payment failures
from the same root cause).
"""

from __future__ import annotations

import re
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class TicketSnapshot:
    """Lightweight snapshot of a ticket for similarity analysis."""
    ticket_id: int = 0
    subject: str = ""
    category: str = ""
    intent: str = ""
    entities: Dict[str, str] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    customer_id: int = 0
    tenant_id: str = "default"
    status: str = ""
    normalized_text: str = ""


@dataclass
class IncidentHypothesis:
    """A hypothesized incident linking related tickets."""
    incident_id: str = ""
    title: str = ""
    description: str = ""
    confidence: float = 0.0
    affected_tickets: List[int] = field(default_factory=list)
    affected_customer_count: int = 0
    root_cause_hint: str = ""
    category: str = ""
    time_window_start: Optional[datetime] = None
    time_window_end: Optional[datetime] = None
    severity: str = "MEDIUM"  # LOW, MEDIUM, HIGH, CRITICAL
    status: str = "candidate"  # "candidate", "investigating", "confirmed", "mitigated", "resolved"
    is_spike: bool = False
    spike_ratio: Optional[float] = None
    evidence: List[str] = field(default_factory=list)


class IncidentStateManager:
    """Tracks administrative lifecycle state for incident hypotheses."""
    _instance = None
    _statuses: Dict[str, str] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._statuses = {}
        return cls._instance

    @classmethod
    def get_status(cls, incident_id: str, default: str = "candidate") -> str:
        return cls._statuses.get(incident_id, default)

    @classmethod
    def set_status(cls, incident_id: str, status: str) -> None:
        cls._statuses[incident_id] = status

    @classmethod
    def reset(cls) -> None:
        cls._statuses.clear()


@dataclass
class SimilarityScore:
    """Similarity score between two tickets."""
    ticket_a: int = 0
    ticket_b: int = 0
    keyword_score: float = 0.0
    category_score: float = 0.0
    temporal_score: float = 0.0
    intent_score: float = 0.0
    overall: float = 0.0


class TicketSimilarityAnalyzer:
    """
    Analyzes similarity between tickets using multiple dimensions:
    keyword overlap (with code-mixed normalization and synonym mapping),
    category matching, temporal proximity, and intent matching.
    """

    # Category equivalence groups
    CATEGORY_GROUPS = {
        "payment": {"payment", "billing", "payments/finance", "charge", "refund"},
        "delivery": {"delivery", "shipping", "delivery/logistics", "tracking"},
        "security": {"security", "fraud", "unauthorized"},
        "account": {"account", "login", "account/auth", "password"},
    }

    # Customer support synonym canonicalization map
    SYNONYM_MAP: Dict[str, str] = {
        # Payment synonyms
        "payment": "payment",
        "billing": "payment",
        "money": "payment",
        "paisa": "payment",
        "panam": "payment",
        "kaasu": "payment",
        "cash": "payment",
        "amount": "payment",
        "charge": "payment",
        "charged": "deducted",
        "deduct": "deducted",
        "deducted": "deducted",
        "debit": "deducted",
        "debited": "deducted",
        "cut": "deducted",
        "kat": "deducted",
        "transaction": "payment",
        "refund": "refund",
        "wapas": "refund",
        "failed": "failed",
        "failure": "failed",
        "fail": "failed",
        "declined": "failed",
        "cancelled": "failed",
        "unsuccessful": "failed",
        "pending": "pending",
        # Delivery synonyms
        "delivery": "delivery",
        "deliver": "delivery",
        "delivered": "delivery",
        "shipping": "delivery",
        "shipment": "delivery",
        "courier": "delivery",
        "dispatch": "delivery",
        "tracking": "tracking",
        "track": "tracking",
        "parcel": "delivery",
        "package": "delivery",
        "order": "order",
        # Security/account synonyms
        "login": "login",
        "signin": "login",
        "password": "password",
        "otp": "otp",
        "auth": "login",
        "authentication": "login",
        "hacked": "security",
        "fraud": "security",
        "unauthorized": "security",
        "stole": "security",
        "stolen": "security",
        # Tamil synonyms
        "பணம்": "payment",
        "காசு": "payment",
        "கட்டணம்": "payment",
        "ஆர்டர்": "order",
        "டெலிவரி": "delivery",
        "பார்சல்": "delivery",
        "வரவில்லை": "delayed",
        "வரல": "delayed",
        "தாமதம்": "delayed",
        "ரீஃபண்ட்": "refund",
        "ரிட்டர்ன்": "refund",
        "கடவுச்சொல்": "password",
        "உள்நுழைவு": "login",
        # Pan-Indian Romanized delivery & delay synonyms
        "varala": "delayed",
        "varave": "delayed",
        "reach": "delivery",
        "aagala": "failed",
        "raledu": "delayed",
        "raaledu": "delayed",
        "bandilla": "delayed",
        "vannilla": "delayed",
        "asheni": "delayed",
        "aala nahi": "delayed",
        "nathi aavyo": "delayed",
        "nahi aaya": "delayed",
        "inka": "delayed",
        "innu": "delayed",
        "ithuvare": "delayed",
        "ekhono": "delayed",
        "ajun": "delayed",
        "haji": "delayed",
        "aje": "delayed",
        # Pan-Indian Romanized payment synonyms
        "dabbu": "payment",
        "duddu": "payment",
        "taka": "payment",
        "paise": "payment",
        "rupia": "payment",
        "chesanu": "payment",
        "maadiddini": "payment",
        "cheythu": "payment",
        "korechi": "payment",
        "kela": "payment",
        "kari didhu": "payment",
        "kar ditta": "payment",
        "cheyaledu": "failed",
        "madilla": "failed",
        "cheythilla": "failed",
        "korini": "failed",
        "kela nahi": "failed",
        "nathi karyu": "failed",
        "nahi kita": "failed",
        # Pan-Indian Native Script Synonyms
        "రాలేదు": "delayed",
        "ఆర్డర్": "order",
        "డెలివరీ": "delivery",
        "పేమెంట్": "payment",
        "డబ్బు": "payment",
        "బಂದಿಲ್ಲ": "delayed",
        "ಆರ್ಡರ್": "order",
        "ಡೆಲಿವರಿ": "delivery",
        "ಪೇಮೆಂಟ್": "payment",
        "ದುಡ್ಡು": "payment",
        "വന്നില്ല": "delayed",
        "ഓർഡർ": "order",
        "ഡെലിവറി": "delivery",
        "പേയ്മെന്റ്": "payment",
        "പണം": "payment",
        "আসেনি": "delayed",
        "অর্ডার": "order",
        "ডেলিভারি": "delivery",
        "পেমেন্ট": "payment",
        "টাকা": "payment",
        "आला नाही": "delayed",
        "ऑर्डर": "order",
        "डिलिव्हरी": "delivery",
        "पेमेंट": "payment",
        "पैसे": "payment",
        "નથી આવ્યો": "delayed",
        "ઓર્ડર": "order",
        "ડિલિવરી": "delivery",
        "પેમેન્ટ": "payment",
        "રૂપિયા": "payment",
        "ਨਹੀਂ ਆਇਆ": "delayed",
        "ਆਰਡਰ": "order",
        "ਡਿਲੀਵਰੀ": "delivery",
        "ਪੇਮੈਂਟ": "payment",
        "ਪੈਸੇ": "payment",
    }

    _normalizer_instance = None

    @classmethod
    def _get_normalizer(cls):
        if cls._normalizer_instance is None:
            try:
                from app.ai.intelligence.language import IndianLanguageNormalizer
                cls._normalizer_instance = IndianLanguageNormalizer()
            except Exception:
                cls._normalizer_instance = False
        return cls._normalizer_instance if cls._normalizer_instance is not False else None

    def compute_similarity(
        self,
        ticket_a: TicketSnapshot,
        ticket_b: TicketSnapshot,
        keyword_cache: Optional[Dict[int, Set[str]]] = None,
    ) -> SimilarityScore:
        """Compute multi-dimensional similarity between two tickets."""
        keyword_score = self._keyword_similarity(ticket_a, ticket_b, keyword_cache=keyword_cache)
        category_score = self._category_similarity(ticket_a, ticket_b)
        temporal_score = self._temporal_similarity(ticket_a, ticket_b)
        intent_score = self._intent_similarity(ticket_a, ticket_b)

        # Weighted aggregate
        overall = (
            keyword_score * 0.3
            + category_score * 0.25
            + temporal_score * 0.2
            + intent_score * 0.25
        )

        return SimilarityScore(
            ticket_a=ticket_a.ticket_id,
            ticket_b=ticket_b.ticket_id,
            keyword_score=round(keyword_score, 3),
            category_score=round(category_score, 3),
            temporal_score=round(temporal_score, 3),
            intent_score=round(intent_score, 3),
            overall=round(overall, 3),
        )

    def _keyword_similarity(
        self,
        a: TicketSnapshot,
        b: TicketSnapshot,
        keyword_cache: Optional[Dict[int, Set[str]]] = None,
    ) -> float:
        """Jaccard similarity on extracted keywords, including normalized text and subjects."""
        if keyword_cache is not None:
            words_a = keyword_cache.get(a.ticket_id)
            if words_a is None:
                text_a = f"{a.subject} {a.normalized_text}".strip()
                words_a = set(self._extract_keywords(text_a))
                keyword_cache[a.ticket_id] = words_a

            words_b = keyword_cache.get(b.ticket_id)
            if words_b is None:
                text_b = f"{b.subject} {b.normalized_text}".strip()
                words_b = set(self._extract_keywords(text_b))
                keyword_cache[b.ticket_id] = words_b
        else:
            text_a = f"{a.subject} {a.normalized_text}".strip()
            text_b = f"{b.subject} {b.normalized_text}".strip()
            words_a = set(self._extract_keywords(text_a))
            words_b = set(self._extract_keywords(text_b))

        if not words_a or not words_b:
            return 0.0

        intersection = words_a & words_b
        union = words_a | words_b
        return len(intersection) / len(union) if union else 0.0

    def _category_similarity(self, a: TicketSnapshot, b: TicketSnapshot) -> float:
        """Check if categories belong to the same equivalence group."""
        cat_a = (a.category or "").lower()
        cat_b = (b.category or "").lower()

        if cat_a == cat_b and cat_a:
            return 1.0

        for group_cats in self.CATEGORY_GROUPS.values():
            if cat_a in group_cats and cat_b in group_cats:
                return 0.8
        return 0.0

    def _temporal_similarity(self, a: TicketSnapshot, b: TicketSnapshot) -> float:
        """Score based on how close in time the tickets were created."""
        if not a.created_at or not b.created_at:
            return 0.3  # Unknown - neutral

        time_diff = abs((a.created_at - b.created_at).total_seconds())

        if time_diff < 3600:     # Within 1 hour
            return 1.0
        if time_diff < 14400:    # Within 4 hours
            return 0.8
        if time_diff < 86400:    # Within 1 day
            return 0.5
        if time_diff < 259200:   # Within 3 days
            return 0.2
        return 0.0

    def _intent_similarity(self, a: TicketSnapshot, b: TicketSnapshot) -> float:
        if a.intent == b.intent and a.intent:
            return 1.0
        # Related intents
        related_pairs = {
            frozenset({"PAYMENT_ISSUE", "REFUND_ISSUE"}),
            frozenset({"LOGIN_ISSUE", "SECURITY_ISSUE"}),
            frozenset({"DELIVERY_ISSUE", "UPDATE_ISSUE"}),
        }
        if frozenset({a.intent, b.intent}) in related_pairs:
            return 0.6
        return 0.0

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract meaningful keywords from text with code-mixed normalization and synonym canonicalization."""
        if not text:
            return []
        stopwords = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "my", "i", "me", "you", "we", "they", "it", "to", "for",
            "in", "on", "at", "of", "and", "or", "but", "not", "with",
            "this", "that", "can", "has", "have", "had", "do", "does",
            "from", "by", "account", "please", "help", "get", "sir", "madam",
        }
        # Code-mixed normalization if available
        norm_text = text
        normalizer = self._get_normalizer()
        if normalizer:
            try:
                norm_res = normalizer.normalize(text)
                norm_text = norm_res.normalized
            except Exception:
                pass

        # Multilingual semantic query expansion for cross-language clustering
        search_query = ""
        if any(ord(c) > 127 for c in text):
            try:
                from app.ai.intelligence.multilingual_engine import multilingual_service
                understanding = multilingual_service.understand(text)
                if understanding.normalized_search_query:
                    search_query = understanding.normalized_search_query
            except Exception:
                pass

        combined = f"{text.lower()} {norm_text.lower()} {search_query.lower()}"
        words = re.findall(r'[\u0600-\u0D7F]+|[a-z]+', combined)
        keywords: List[str] = []
        for w in words:
            if w in stopwords or len(w) <= 2:
                continue
            canonical = self.SYNONYM_MAP.get(w, w)
            keywords.append(canonical)
        return keywords


class IncidentDetector:
    """
    Detects incidents by clustering similar tickets, evaluating complaint spikes,
    and generating hypotheses about root causes.
    """

    SIMILARITY_THRESHOLD = 0.45  # Minimum similarity to consider tickets related
    MIN_CLUSTER_SIZE = 2         # Minimum tickets to form an incident

    def __init__(self):
        self.analyzer = TicketSimilarityAnalyzer()

    def detect_spike(
        self,
        tickets: List[TicketSnapshot],
        baseline_hours: float = 24.0,
        current_hours: float = 2.0,
        spike_ratio_threshold: float = 2.5,
    ) -> Dict[str, Any]:
        """
        Detect unusual complaint spikes using real timestamps against a defined baseline.

        Requires sufficient data:
        - At least 5 timestamped tickets total
        - Real historical tickets in the baseline window
        """
        valid_tickets = [t for t in tickets if t.created_at is not None]
        if len(valid_tickets) < 5:
            return {
                "is_spike": False,
                "spike_ratio": None,
                "reason": "insufficient_data",
                "details": f"Only {len(valid_tickets)} timestamped tickets available (minimum 5 required).",
            }

        sorted_tickets = sorted(valid_tickets, key=lambda t: t.created_at)
        max_time = sorted_tickets[-1].created_at
        min_time = sorted_tickets[0].created_at

        # Time span check
        total_seconds = (max_time - min_time).total_seconds()
        if total_seconds < current_hours * 3600:
            return {
                "is_spike": False,
                "spike_ratio": None,
                "reason": "insufficient_time_span",
                "details": f"Time span {total_seconds / 3600:.1f}h is shorter than evaluation window {current_hours}h.",
            }

        cutoff = max_time - timedelta(hours=current_hours)
        baseline_start = max_time - timedelta(hours=current_hours + baseline_hours)

        current_window_tickets = [t for t in valid_tickets if t.created_at >= cutoff]
        baseline_window_tickets = [
            t for t in valid_tickets if baseline_start <= t.created_at < cutoff
        ]

        if not baseline_window_tickets:
            return {
                "is_spike": False,
                "spike_ratio": None,
                "reason": "insufficient_baseline_data",
                "details": "No tickets found in historical baseline window to compute arrival rate.",
            }

        # Calculate arrival rates (tickets per hour)
        baseline_rate = len(baseline_window_tickets) / max(baseline_hours, 1.0)
        current_rate = len(current_window_tickets) / max(current_hours, 0.5)

        if baseline_rate <= 0:
            return {
                "is_spike": False,
                "spike_ratio": None,
                "reason": "zero_baseline",
                "details": "Baseline complaint rate is zero.",
            }

        spike_ratio = current_rate / baseline_rate
        is_spike = bool(spike_ratio >= spike_ratio_threshold and len(current_window_tickets) >= 3)

        return {
            "is_spike": is_spike,
            "spike_ratio": round(spike_ratio, 2),
            "current_rate": round(current_rate, 2),
            "baseline_rate": round(baseline_rate, 2),
            "current_count": len(current_window_tickets),
            "baseline_count": len(baseline_window_tickets),
        }

    def detect_incidents(
        self,
        tickets: List[TicketSnapshot],
        tenant_id: str = "default",
    ) -> List[IncidentHypothesis]:
        """
        Analyze a list of tickets and detect potential incidents.
        
        Args:
            tickets: List of ticket snapshots to analyze
            tenant_id: Tenant scope
        
        Returns:
            List of IncidentHypothesis objects
        """
        # Filter to same tenant
        tenant_tickets = [t for t in tickets if t.tenant_id == tenant_id]

        if len(tenant_tickets) < self.MIN_CLUSTER_SIZE:
            return []

        # Build similarity matrix with precomputed keywords
        keyword_cache: Dict[int, Set[str]] = {}
        for t in tenant_tickets:
            text = f"{t.subject} {t.normalized_text}".strip()
            keyword_cache[t.ticket_id] = set(self.analyzer._extract_keywords(text))

        similarities: List[SimilarityScore] = []
        for i, ticket_a in enumerate(tenant_tickets):
            for j, ticket_b in enumerate(tenant_tickets):
                if i >= j:
                    continue  # Skip duplicates and self-comparison
                sim = self.analyzer.compute_similarity(ticket_a, ticket_b, keyword_cache=keyword_cache)
                if sim.overall >= self.SIMILARITY_THRESHOLD:
                    similarities.append(sim)

        # Cluster tickets using connected components
        clusters = self._cluster_tickets(similarities, tenant_tickets)

        # Generate hypotheses
        hypotheses = []
        for idx, cluster in enumerate(clusters):
            if len(cluster) >= self.MIN_CLUSTER_SIZE:
                hypothesis = self._generate_hypothesis(idx, cluster, tenant_tickets)
                hypotheses.append(hypothesis)

        return hypotheses

    def _cluster_tickets(
        self,
        similarities: List[SimilarityScore],
        tickets: List[TicketSnapshot],
    ) -> List[List[int]]:
        """Simple connected-component clustering."""
        # Build adjacency list
        adj: Dict[int, Set[int]] = defaultdict(set)
        for sim in similarities:
            adj[sim.ticket_a].add(sim.ticket_b)
            adj[sim.ticket_b].add(sim.ticket_a)

        # Find connected components via BFS
        visited: Set[int] = set()
        clusters: List[List[int]] = []

        ticket_ids = {t.ticket_id for t in tickets}
        for tid in ticket_ids:
            if tid in visited or tid not in adj:
                continue
            # BFS
            cluster: List[int] = []
            queue = [tid]
            visited.add(tid)
            while queue:
                current = queue.pop(0)
                cluster.append(current)
                for neighbor in adj.get(current, set()):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
            clusters.append(cluster)

        return clusters

    def _generate_hypothesis(
        self,
        idx: int,
        ticket_ids: List[int],
        all_tickets: List[TicketSnapshot],
    ) -> IncidentHypothesis:
        """Generate an incident hypothesis from a cluster of tickets."""
        cluster_tickets = [t for t in all_tickets if t.ticket_id in ticket_ids]

        # Find common category
        categories = [t.category for t in cluster_tickets if t.category]
        common_category = max(set(categories), key=categories.count) if categories else "General"

        # Find common intent
        intents = [t.intent for t in cluster_tickets if t.intent]
        common_intent = max(set(intents), key=intents.count) if intents else ""

        # Time window
        created_times = [t.created_at for t in cluster_tickets if t.created_at]
        time_start = min(created_times) if created_times else None
        time_end = max(created_times) if created_times else None

        # Affected customers
        customer_ids = {t.customer_id for t in cluster_tickets}

        # Confidence based on cluster size and coherence
        confidence = min(0.5 + (len(ticket_ids) * 0.1), 0.95)

        # Generate title
        intent_name = common_intent.replace("_", " ").title() if common_intent else common_category
        title = f"Potential {common_category} Incident: {intent_name}"

        # Root cause hint
        root_cause = self._guess_root_cause(cluster_tickets, common_intent)

        # Severity based on size and priority
        severity = self._assess_severity(cluster_tickets)

        anchor_id = min(ticket_ids) if ticket_ids else (idx + 1)
        clean_cat = re.sub(r'[^A-Za-z0-9]', '', common_category).upper()[:4] or "GENR"
        incident_id = f"INC-{clean_cat}-{anchor_id:04d}"

        # Check for confirmed status or active state in IncidentStateManager (stable ID first, then legacy idx ID)
        status = IncidentStateManager.get_status(
            incident_id,
            default=IncidentStateManager.get_status(f"INC-{idx + 1:04d}", default="candidate"),
        )

        # Evaluate complaint spike if sufficient real timestamped tickets exist
        spike_info = self.detect_spike(cluster_tickets)
        is_spike = spike_info.get("is_spike", False)
        spike_ratio = spike_info.get("spike_ratio")

        evidence: List[str] = [
            f"{len(ticket_ids)} tickets grouped with category '{common_category}' and intent '{common_intent or 'similar'}'",
            root_cause,
        ]
        if is_spike and spike_ratio:
            evidence.append(f"Unusual complaint surge detected: {spike_ratio}x above historical baseline")
        elif time_start and time_end:
            duration_mins = max(round((time_end - time_start).total_seconds() / 60), 1)
            evidence.append(f"Cluster formed across {duration_mins} minute window")

        return IncidentHypothesis(
            incident_id=incident_id,
            title=title,
            description=f"{len(ticket_ids)} related tickets detected in category '{common_category}'",
            confidence=round(confidence, 2),
            affected_tickets=ticket_ids,
            affected_customer_count=len(customer_ids),
            root_cause_hint=root_cause,
            category=common_category,
            time_window_start=time_start,
            time_window_end=time_end,
            severity=severity,
            status=status,
            is_spike=is_spike,
            spike_ratio=spike_ratio,
            evidence=evidence,
        )

    def _guess_root_cause(self, tickets: List[TicketSnapshot], common_intent: str) -> str:
        """Simple heuristic to guess root cause."""
        if common_intent == "PAYMENT_ISSUE":
            return "Possible payment processing system failure"
        if common_intent == "DELIVERY_ISSUE":
            return "Possible shipping/logistics disruption"
        if common_intent == "LOGIN_ISSUE":
            return "Possible authentication service issue"
        if common_intent == "SECURITY_ISSUE":
            return "Possible security breach or suspicious activity spike"
        return "Multiple customers experiencing similar issues"

    def _assess_severity(self, tickets: List[TicketSnapshot]) -> str:
        """Assess incident severity based on ticket count and priorities."""
        count = len(tickets)
        if count >= 10:
            return "CRITICAL"
        if count >= 5:
            return "HIGH"
        if count >= 3:
            return "MEDIUM"
        return "LOW"
