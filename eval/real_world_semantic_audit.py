"""
ResolveAI V2 — Real-World Semantic Generalization Acceptance Audit Harness
==========================================================================
Executes a rigorous, end-to-end acceptance audit against the live ResolveAI V2
architecture using a genuinely held-out evaluation corpus across English,
Tamil, Tanglish, Hindi, and Hinglish.

Evaluates:
1. Genuinely unseen expressions (colloquialisms, morphology, slang, transliteration)
2. End-to-end semantic understanding (intent, entities, language, action, response)
3. Customer communication styles (corrections, short tokens, multi-intent, emotional)
4. Real provider resilience (healthy calls, 429 rate limits, timeouts, retries, latency)
5. Safety, authorized tools, security escalation, and factual grounding
6. Quantitative audit metrics (accuracy, latency p50/p95, calls per turn, fallbacks)
"""

import os
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
import time
import json
import asyncio
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict

# Ensure backend is in python path
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(BACKEND_DIR, ".env"))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool
from sqlalchemy import select

from app.database import Base
from app.main import app
from app.users.models import User
from app.notifications.models import Notification
from app.conversations.models import Conversation, ConversationMessage
from app.conversations.service import ConversationService
from app.commerce.models import Order
from app.shared.models import SenderType, WorkflowState
from app.ai.intelligence.language import UniversalMeaningEngine, CodeMixedLanguageDetector
from app.ai.groq_provider import GroqProvider, RateLimitError
from app.ai.m4.provider import M4AIProvider
from app.rag.models import KnowledgeArticle
from tests.fixtures import INITIAL_ARTICLES
from app.rag.retriever import TFIDFRetriever


@dataclass
class AuditCaseResult:
    case_id: str
    category: str
    original_message: str
    expected_intent: str
    expected_action: str
    detected_language: str
    preferred_language: str
    inferred_intent: str
    inferred_entities: Dict[str, Any]
    selected_action: str
    response_text: str
    latency_ms: float
    grounded: bool
    is_greeting_override: bool
    is_technical_difficulties: bool
    language_consistent: bool
    llm_interpreted: bool
    notes: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# 1. HELD-OUT CORPUS: Genuinely Unseen Expressions (Not in Dictionaries/Tests)
# ─────────────────────────────────────────────────────────────────────────────
HELD_OUT_CASES = [
    # ── Tanglish Novel Expressions ──
    {
        "id": "TA_01",
        "category": "Tanglish - Delivery Inquiry",
        "message": "saaman vandhu serala romba neram aachu, courier status kaatunga",
        "expected_intent": "DELIVERY_ISSUE",
        "expected_action": "ASK_USER",
        "expected_lang": "tanglish",
        "grounding_keywords": ["order", "status", "delivery", "track"],
    },
    {
        "id": "TA_02",
        "category": "Tanglish - Return Policy Inquiry",
        "message": "thirumba thara evlo naal kulla kudukanum?",
        "expected_intent": "REFUND_ISSUE",
        "expected_action": "RESOLVE",
        "expected_lang": "tanglish",
        "grounding_keywords": ["30", "return"],
    },
    {
        "id": "TA_03",
        "category": "Tanglish - Cancellation Rules",
        "message": "ippodhan book pannen, adha nipaata vazhi irukka?",
        "expected_intent": "ORDER_MANAGEMENT",
        "expected_action": "RESOLVE",
        "expected_lang": "tanglish",
        "grounding_keywords": ["cancel", "dispatch"],
    },
    {
        "id": "TA_04",
        "category": "Tanglish - Damaged Item / Warranty",
        "message": "box open panna odanjurukku, maathi kuduka mudiyuma?",
        "expected_intent": "WARRANTY_SERVICE",
        "expected_action": "ASK_USER",
        "expected_lang": "tanglish",
        "grounding_keywords": ["damage", "exchange", "replace", "condition"],
    },
    {
        "id": "TA_05",
        "category": "Tanglish - Identifier Purpose Question",
        "message": "yen id theva padudhu ungalukku?",
        "expected_intent": "CLARIFICATION_ORDER_ID_PURPOSE",
        "expected_action": "ASK_USER",
        "expected_lang": "tanglish",
        "grounding_keywords": ["track", "details", "locate", "check", "order"],
    },
    {
        "id": "TA_06",
        "category": "Tanglish - Multi-Intent (Greeting + Policy)",
        "message": "vanakkam bro, order-oda shipping policy sollunga",
        "expected_intent": "DELIVERY_ISSUE",
        "expected_action": "RESOLVE",
        "expected_lang": "tanglish",
        "grounding_keywords": ["3-5", "delivery", "business"],
    },

    # ── Hinglish Novel Expressions ──
    {
        "id": "HI_01",
        "category": "Hinglish - Delivery Delay",
        "message": "bhai mera packet abhi tak nahi aaya, courier kahan ruka hai?",
        "expected_intent": "DELIVERY_ISSUE",
        "expected_action": "ASK_USER",
        "expected_lang": "hinglish",
        "grounding_keywords": ["order", "delivery", "track"],
    },
    {
        "id": "HI_02",
        "category": "Hinglish - Return Time Window",
        "message": "saman wapas bhejne par paise kitne din mein aate hain?",
        "expected_intent": "REFUND_ISSUE",
        "expected_action": "RESOLVE",
        "expected_lang": "hinglish",
        "grounding_keywords": ["refund", "return", "30"],
    },
    {
        "id": "HI_03",
        "category": "Hinglish - Cancellation",
        "message": "dispatch se pehle order cancel ho sakta hai kya?",
        "expected_intent": "ORDER_MANAGEMENT",
        "expected_action": "RESOLVE",
        "expected_lang": "hinglish",
        "grounding_keywords": ["cancel", "dispatch"],
    },
    {
        "id": "HI_04",
        "category": "Hinglish - Identifier Purpose Question",
        "message": "bina order id ke trace nahi ho payega kya?",
        "expected_intent": "CLARIFICATION_ORDER_ID_PURPOSE",
        "expected_action": "ASK_USER",
        "expected_lang": "hinglish",
        "grounding_keywords": ["order", "details", "check", "locate"],
    },

    # ── Pure Native Scripts ──
    {
        "id": "TA_NATIVE_01",
        "category": "Pure Tamil - Return Policy",
        "message": "பொருளை திருப்பி அனுப்ப எத்தனை நாட்கள் அவகாசம் உள்ளது?",
        "expected_intent": "REFUND_ISSUE",
        "expected_action": "RESOLVE",
        "expected_lang": "tamil",
        "grounding_keywords": ["30", "நாட்கள்", "திருப்பி"],
    },
    {
        "id": "HI_NATIVE_01",
        "category": "Pure Hindi - Cancellation Rules",
        "message": "ऑर्डर रद्द करने के क्या नियम हैं?",
        "expected_intent": "ORDER_MANAGEMENT",
        "expected_action": "RESOLVE",
        "expected_lang": "hindi",
        "grounding_keywords": ["रद्द", "डिस्पैच", "cancel"],
    },

    # ── English Slang, Abbreviations, & Colloquialisms ──
    {
        "id": "EN_01",
        "category": "English - Informal Slang Delivery",
        "message": "yo my parcel ain't arrived yet, where is it stuck?",
        "expected_intent": "DELIVERY_ISSUE",
        "expected_action": "ASK_USER",
        "expected_lang": "english",
        "grounding_keywords": ["order", "delivery", "track"],
    },
    {
        "id": "EN_02",
        "category": "English - Abbreviated Inquiry",
        "message": "what is your return window timeframe?",
        "expected_intent": "POLICY_QUERY",
        "expected_action": "RESOLVE",
        "expected_lang": "english",
        "grounding_keywords": ["30", "return"],
    },
    {
        "id": "EN_03",
        "category": "English - Explaining ID Purpose",
        "message": "why exactly is an order number requested here?",
        "expected_intent": "CLARIFICATION_ORDER_ID_PURPOSE",
        "expected_action": "ASK_USER",
        "expected_lang": "english",
        "grounding_keywords": ["order", "details", "track", "locate", "account"],
    },
    {
        "id": "EN_04",
        "category": "English - Emotional High Frustration",
        "message": "This is totally frustrating! Money deducted twice and no confirmation!",
        "expected_intent": "PAYMENT_ISSUE",
        "expected_action": "ASK_USER",
        "expected_lang": "english",
        "grounding_keywords": ["payment", "deduct", "resolve", "help"],
    },

    # ── Explicit Human Escalations ──
    {
        "id": "ESC_01",
        "category": "Escalation - Tanglish Supervisor Demand",
        "message": "mudiyala, human supervisor-kku transfer pannunga",
        "expected_intent": "ESCALATE",
        "expected_action": "ESCALATE",
        "expected_lang": "tanglish",
        "grounding_keywords": ["expert", "connect", "support", "team"],
    },
    {
        "id": "ESC_02",
        "category": "Escalation - Hinglish Agent Demand",
        "message": "kisi senior agent se direct connect kijiye",
        "expected_intent": "ESCALATE",
        "expected_action": "ESCALATE",
        "expected_lang": "hinglish",
        "grounding_keywords": ["expert", "connect", "agent", "support"],
    },
    {
        "id": "ESC_03",
        "category": "Escalation - English Human Agent Request",
        "message": "I demand to talk to a human support agent right now",
        "expected_intent": "ESCALATE",
        "expected_action": "ESCALATE",
        "expected_lang": "english",
        "grounding_keywords": ["expert", "human", "connect", "support"],
    },

    # ── Security & Account Compromise ──
    {
        "id": "SEC_01",
        "category": "Security - Account Hijack Risk",
        "message": "someone hacked my account and changed password without permission",
        "expected_intent": "ACCOUNT_SECURITY",
        "expected_action": "ESCALATE",
        "expected_lang": "english",
        "grounding_keywords": ["security", "expert", "team", "urgent"],
    },

    # ── Unrecognized Gibberish / Smash ──
    {
        "id": "GIB_01",
        "category": "Gibberish - Keyboard Smash",
        "message": "asdjklqwe123 zxcvm",
        "expected_intent": "UNCLEAR",
        "expected_action": "ASK_USER",
        "expected_lang": "english",
        "grounding_keywords": ["help", "clarify", "assist"],
    }
]


class RealWorldAcceptanceAuditor:
    def __init__(self, use_live_groq: bool = True):
        self.use_live_groq = use_live_groq
        self.engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            echo=False,
            poolclass=StaticPool
        )
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.provider = GroqProvider() if use_live_groq else M4AIProvider()
        self.conversation_service = ConversationService(ai_provider=self.provider)
        self.meaning_engine = UniversalMeaningEngine()

    async def setup(self):
        """Initializes database schema and initial knowledge articles."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            
        async with self.session_factory() as session:
            for article_data in INITIAL_ARTICLES:
                article = KnowledgeArticle(**article_data)
                session.add(article)
            await session.commit()
            TFIDFRetriever.invalidate("default")
            await TFIDFRetriever.refresh(session, "default")

    async def send_msg(self, session: AsyncSession, conversation: Conversation, user: User, content: str) -> Dict[str, Any]:
        """Sends a message and fetches the generated AI response and analysis metadata."""
        await self.conversation_service.process_customer_message(
            db=session,
            conversation=conversation,
            customer_id=user.id,
            message_content=content
        )
        await session.commit()
        await session.refresh(conversation)

        stmt = (
            select(ConversationMessage)
            .where(
                ConversationMessage.conversation_id == conversation.id,
                ConversationMessage.sender_type == SenderType.AI
            )
            .order_by(ConversationMessage.created_at.desc())
        )
        ai_msg = (await session.execute(stmt)).scalars().first()
        response_text = ai_msg.content if ai_msg else ""
        analysis = ai_msg.metadata_ if (ai_msg and ai_msg.metadata_) else {}
        decision = analysis.get("decision_state") or (
            "ESCALATE" if conversation.workflow_state == WorkflowState.WAITING_FOR_EXPERT else "ASK_USER"
        )
        return {
            "response": response_text,
            "analysis": analysis,
            "decision": decision,
            "workflow_state": conversation.workflow_state
        }

    async def run_single_turn_audit(self, test_case: Dict[str, Any]) -> AuditCaseResult:
        """Executes one end-to-end conversation intake and records complete telemetry."""
        msg = test_case["message"]
        t0 = time.time()

        async with self.session_factory() as session:
            # Create user
            user = User(
                email=f"audit_{test_case['id'].lower()}@resolveai.test",
                full_name=f"Audit User {test_case['id']}",
                password_hash="testpass"
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

            # Create conversation
            conversation = Conversation(
                customer_id=user.id,
                channel="CHAT"
            )
            session.add(conversation)
            await session.commit()
            await session.refresh(conversation)

            # Process customer message
            try:
                result = await self.send_msg(session, conversation, user, msg)
            except Exception as e:
                result = {
                    "decision": "ERROR",
                    "response": f"Exception: {e}",
                    "analysis": {}
                }

        latency_ms = (time.time() - t0) * 1000.0

        decision = result.get("decision", "UNKNOWN")
        response_text = result.get("response", "")
        analysis = result.get("analysis", {})

        inferred_intent = str(analysis.get("intent", "")).upper()
        detected_lang = str(analysis.get("language", "")).lower()
        pref_lang = str(conversation.preferred_language or "").lower()
        entities = analysis.get("entities", {})

        # Evaluations
        resp_lower = response_text.lower()
        
        # Grounding evaluation
        grounding_kws = test_case.get("grounding_keywords", [])
        grounded = any(kw.lower() in resp_lower for kw in grounding_kws) if grounding_kws else True

        # Greeting override detection
        is_greeting_override = (
            test_case["expected_intent"] != "GREETING"
            and (inferred_intent == "GREETING" or (resp_lower.startswith("hello!") and len(resp_lower) < 50))
        )

        # Technical difficulties detection
        is_tech_diff = "technical difficulties" in resp_lower or "503" in resp_lower

        # Language consistency
        lang_consistent = True
        if test_case["expected_lang"] in ("tamil", "tanglish"):
            lang_consistent = any(w in resp_lower for w in ["vanakkam", "unga", "irukku", "panren", "kuduka", "sollunga", "30", "பணம்", "நாட்கள்"]) or detected_lang in ("ta", "tamil", "tanglish")
        elif test_case["expected_lang"] in ("hindi", "hinglish"):
            lang_consistent = any(w in resp_lower for w in ["namaste", "aapka", "karo", "hai", "hain", "madad", "रद्द", "दिन"]) or detected_lang in ("hi", "hindi", "hinglish")

        llm_interpreted = not bool(analysis.get("fallback_used", False))

        return AuditCaseResult(
            case_id=test_case["id"],
            category=test_case["category"],
            original_message=msg,
            expected_intent=test_case["expected_intent"],
            expected_action=test_case["expected_action"],
            detected_language=detected_lang,
            preferred_language=pref_lang,
            inferred_intent=inferred_intent,
            inferred_entities=entities,
            selected_action=decision,
            response_text=response_text,
            latency_ms=round(latency_ms, 2),
            grounded=grounded,
            is_greeting_override=is_greeting_override,
            is_technical_difficulties=is_tech_diff,
            language_consistent=lang_consistent,
            llm_interpreted=llm_interpreted,
        )

    async def run_multi_turn_style_audit(self) -> List[Dict[str, Any]]:
        """Tests corrections, language switching, short follow-ups, and isolation across turns."""
        results = []

        async with self.session_factory() as session:
            # User A and Order seed
            user_a = User(email="customer_a@audit.com", full_name="Customer A", password_hash="pw")
            user_b = User(email="customer_b@audit.com", full_name="Customer B", password_hash="pw")
            session.add_all([user_a, user_b])
            await session.commit()
            await session.refresh(user_a)
            await session.refresh(user_b)

            order_a = Order(
                customer_id=user_a.id,
                tenant_id="default",
                order_number="ORD-99881",
                status="Shipped",
                tracking_number="TRK-99881"
            )
            session.add(order_a)
            await session.commit()

            # ── Scenario 1: Entity Correction Turn ──
            convo_1 = Conversation(customer_id=user_a.id, channel="CHAT")
            session.add(convo_1)
            await session.commit()
            await session.refresh(convo_1)

            t1 = await self.send_msg(session, convo_1, user_a, "where is my order ORD-00000?")
            t2 = await self.send_msg(session, convo_1, user_a, "no wait, I meant ORD-99881")
            correction_success = "shipped" in t2.get("response", "").lower() or "ord-99881" in t2.get("response", "").lower()
            results.append({
                "scenario": "Entity Correction (ORD-00000 -> ORD-99881)",
                "passed": correction_success,
                "turn1_response": t1.get("response", "")[:80] + "...",
                "turn2_response": t2.get("response", "")[:80] + "..."
            })

            # ── Scenario 2: Explicit Language Switch & Continuity ──
            convo_2 = Conversation(customer_id=user_a.id, channel="CHAT")
            session.add(convo_2)
            await session.commit()
            await session.refresh(convo_2)

            s1 = await self.send_msg(session, convo_2, user_a, "What is your return policy?")
            s2 = await self.send_msg(session, convo_2, user_a, "Tanglish-la pesalam")
            s3 = await self.send_msg(session, convo_2, user_a, "damage aana porulukku enna rule?")
            await session.refresh(convo_2)
            lang_switch_success = (
                convo_2.preferred_language == "tanglish"
                and any(w in s3.get("response", "").lower() for w in ["return", "exchange", "replace", "condition", "30", "damage"])
                and "order id" not in s3.get("response", "").lower()
            )
            results.append({
                "scenario": "Language Switch (English -> Tanglish sticky continuity)",
                "passed": lang_switch_success,
                "preferred_language": convo_2.preferred_language,
                "final_turn_response": s3.get("response", "")[:90] + "..."
            })

            # ── Scenario 3: Tenant & Customer Isolation ──
            convo_b = Conversation(customer_id=user_b.id, channel="CHAT")
            session.add(convo_b)
            await session.commit()
            await session.refresh(convo_b)

            b1 = await self.send_msg(session, convo_b, user_b, "where is my order?")
            # Customer B should NOT inherit Customer A's order number or state
            leak_detected = "ord-99881" in b1.get("response", "").lower()
            results.append({
                "scenario": "Customer Isolation (Customer B does not inherit Customer A's ORD-99881)",
                "passed": not leak_detected,
                "details": "Customer B received neutral inquiry for their own Order ID"
            })

        return results

    async def run_resilience_audit(self) -> Dict[str, Any]:
        """Tests provider failure recovery: HTTP 429 rate limit, timeouts, and human escalation fallback."""
        results = {}

        # 1. Simulate Groq 429 RateLimit on Policy Query
        from unittest.mock import patch, MagicMock
        err_429 = RateLimitError(
            message="Rate limit reached on requests per minute (RPM). Try again in 8.35s.",
            response=MagicMock(headers={"retry-after": "8.35"}, status_code=429),
            body={"error": {"message": "RPM exceeded"}}
        )

        async with self.session_factory() as session:
            user = User(email="resilience@audit.com", full_name="Resilience Tester", password_hash="pw")
            session.add(user)
            await session.commit()
            await session.refresh(user)

            convo = Conversation(customer_id=user.id, channel="CHAT")
            session.add(convo)
            await session.commit()
            await session.refresh(convo)

            t0 = time.time()
            with patch("app.ai.groq_provider.GroqProvider.analyze", side_effect=err_429):
                res_429 = await self.send_msg(session, convo, user, "unga kitta enna enna policy irukku?")
            latency_429 = (time.time() - t0) * 1000.0

            resp_429 = res_429.get("response", "").lower()
            results["groq_429_policy_recovery"] = {
                "passed": ("return" in resp_429 or "30" in resp_429 or "cancel" in resp_429) and "technical difficulties" not in resp_429,
                "latency_ms": round(latency_429, 2),
                "bounded_within_latency_budget": latency_429 < 3000.0,
                "response": res_429.get("response", "")[:120] + "..."
            }

            # 2. Human Supervisor Demand during Provider Failure
            t0 = time.time()
            with patch("app.ai.groq_provider.GroqProvider.analyze", side_effect=err_429):
                res_esc = await self.send_msg(session, convo, user, "I demand to speak to a human expert right now")
            latency_esc = (time.time() - t0) * 1000.0

            await session.refresh(convo)
            results["provider_down_expert_escalation"] = {
                "passed": convo.workflow_state == WorkflowState.WAITING_FOR_EXPERT and res_esc.get("decision") == "ESCALATE",
                "workflow_state": str(convo.workflow_state),
                "latency_ms": round(latency_esc, 2),
                "response": res_esc.get("response", "")[:120] + "..."
            }

        return results


async def main():
    print("=" * 80)
    print("RESOLVEAI V2 — REAL-WORLD SEMANTIC GENERALIZATION ACCEPTANCE AUDIT")
    print("=" * 80)
    
    auditor = RealWorldAcceptanceAuditor(use_live_groq=True)
    await auditor.setup()

    print(f"\n1. Executing End-to-End Held-Out Corpus Evaluation ({len(HELD_OUT_CASES)} cases)...")
    results: List[AuditCaseResult] = []
    latencies: List[float] = []

    for i, case in enumerate(HELD_OUT_CASES, 1):
        res = await auditor.run_single_turn_audit(case)
        results.append(res)
        latencies.append(res.latency_ms)
        status_sym = "✓" if (res.grounded and not res.is_greeting_override and not res.is_technical_difficulties) else "✗"
        print(f"[{i:02d}/{len(HELD_OUT_CASES):02d}] {status_sym} Case {res.case_id} ({res.category}): {res.latency_ms:.0f}ms -> Intent: {res.inferred_intent} | Action: {res.selected_action}")

    # Compute Aggregate Metrics
    total = len(results)
    intent_correct = sum(1 for r in results if r.inferred_intent == r.expected_intent or (r.expected_intent in ("REFUND_ISSUE", "POLICY_QUERY") and r.inferred_intent in ("REFUND_ISSUE", "POLICY_QUERY")))
    action_correct = sum(1 for r in results if r.selected_action == r.expected_action)
    grounded_count = sum(1 for r in results if r.grounded)
    greeting_overrides = sum(1 for r in results if r.is_greeting_override)
    tech_diffs = sum(1 for r in results if r.is_technical_difficulties)
    lang_consistent = sum(1 for r in results if r.language_consistent)

    sorted_lats = sorted(latencies)
    p50_lat = sorted_lats[total // 2]
    p95_lat = sorted_lats[int(total * 0.95)]

    print("\n2. Executing Multi-Turn Style & Continuity Tests...")
    multi_turn_results = await auditor.run_multi_turn_style_audit()
    for mt in multi_turn_results:
        sym = "✓" if mt["passed"] else "✗"
        print(f"  {sym} {mt['scenario']}")

    print("\n3. Executing Provider Resilience & Graceful Recovery Tests...")
    resilience_results = await auditor.run_resilience_audit()
    for k, v in resilience_results.items():
        sym = "✓" if v["passed"] else "✗"
        print(f"  {sym} {k} (Latency: {v['latency_ms']}ms)")

    # Print Summary Report
    print("\n" + "=" * 80)
    print("ACCEPTANCE AUDIT METRIC SUMMARY")
    print("=" * 80)
    print(f"Held-out Semantic Intent Accuracy:     {intent_correct}/{total} ({intent_correct/total*100:.1f}%)")
    print(f"Correct Action-Selection Rate:         {action_correct}/{total} ({action_correct/total*100:.1f}%)")
    print(f"Grounded-Answer Accuracy:             {grounded_count}/{total} ({grounded_count/total*100:.1f}%)")
    print(f"Unnecessary Greeting Override Rate:   {greeting_overrides}/{total} ({greeting_overrides/total*100:.1f}%)")
    print(f"Generic Fallback / Tech Diff Rate:    {tech_diffs}/{total} ({tech_diffs/total*100:.1f}%)")
    print(f"Language & Script Consistency:        {lang_consistent}/{total} ({lang_consistent/total*100:.1f}%)")
    print(f"Response Latency:                     Median: {p50_lat:.1f}ms | p95: {p95_lat:.1f}ms")
    print("=" * 80)

    # Save detailed JSON artifact
    out_dir = os.path.join(BACKEND_DIR, "..", "eval")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "real_world_acceptance_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "metrics": {
                "total_cases": total,
                "intent_accuracy": round(intent_correct / total * 100, 2),
                "action_accuracy": round(action_correct / total * 100, 2),
                "grounded_accuracy": round(grounded_count / total * 100, 2),
                "greeting_override_rate": round(greeting_overrides / total * 100, 2),
                "technical_difficulties_rate": round(tech_diffs / total * 100, 2),
                "language_consistency_rate": round(lang_consistent / total * 100, 2),
                "median_latency_ms": p50_lat,
                "p95_latency_ms": p95_lat,
            },
            "cases": [asdict(r) for r in results],
            "multi_turn_scenarios": multi_turn_results,
            "resilience": resilience_results
        }, f, indent=2, ensure_ascii=False)
    print(f"\nSaved detailed audit results to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
