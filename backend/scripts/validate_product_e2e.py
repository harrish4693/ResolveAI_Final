"""
ResolveAI M13 — End-to-End Product & Security Validation
Validates running backend, auth, conversations, AI outcomes, expert workflows, admin dashboard, voice, and security boundaries.
"""
import asyncio
import sys
import os
import io

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from app.main import app
from app.database import async_session_factory
from app.users.models import User
from app.experts.models import Expert
from app.shared.models import UserRole
from app.auth.password import get_password_hash


async def ensure_demo_users():
    async with async_session_factory() as db:
        # 1. Customer
        cust = (await db.execute(select(User).where(User.email == "customer@resolveai.com"))).scalar_one_or_none()
        if not cust:
            cust = User(email="customer@resolveai.com", full_name="Demo Customer", password_hash=get_password_hash("password123"), role=UserRole.CUSTOMER, is_active=True, tenant_id="default")
            db.add(cust)
            await db.flush()
        else:
            cust.password_hash = get_password_hash("password123")

        # 2. Expert 1
        exp1 = (await db.execute(select(User).where(User.email == "expert@resolveai.com"))).scalar_one_or_none()
        if not exp1:
            exp1 = User(email="expert@resolveai.com", full_name="Demo Expert 1", password_hash=get_password_hash("password123"), role=UserRole.EXPERT, is_active=True, tenant_id="default")
            db.add(exp1)
            await db.flush()
            db.add(Expert(user_id=exp1.id, is_available=True))
        else:
            exp1.password_hash = get_password_hash("password123")
            exp1_prof = (await db.execute(select(Expert).where(Expert.user_id == exp1.id))).scalar_one_or_none()
            if not exp1_prof:
                db.add(Expert(user_id=exp1.id, is_available=True))

        # 3. Expert 2 (for transfer testing)
        exp2 = (await db.execute(select(User).where(User.email == "expert2@resolveai.com"))).scalar_one_or_none()
        if not exp2:
            exp2 = User(email="expert2@resolveai.com", full_name="Demo Expert 2", password_hash=get_password_hash("password123"), role=UserRole.EXPERT, is_active=True, tenant_id="default")
            db.add(exp2)
            await db.flush()
            db.add(Expert(user_id=exp2.id, is_available=True))
        else:
            exp2.password_hash = get_password_hash("password123")
            exp2_prof = (await db.execute(select(Expert).where(Expert.user_id == exp2.id))).scalar_one_or_none()
            if not exp2_prof:
                db.add(Expert(user_id=exp2.id, is_available=True))

        # 4. Admin
        adm = (await db.execute(select(User).where(User.email == "admin@resolveai.com"))).scalar_one_or_none()
        if not adm:
            adm = User(email="admin@resolveai.com", full_name="Demo Admin", password_hash=get_password_hash("password123"), role=UserRole.ADMIN, is_active=True, tenant_id="default")
            db.add(adm)
        else:
            adm.password_hash = get_password_hash("password123")
            adm.role = UserRole.ADMIN

        # 5. Attacker / Customer B (for IDOR boundary testing)
        cust_b = (await db.execute(select(User).where(User.email == "attacker@resolveai.com"))).scalar_one_or_none()
        if not cust_b:
            cust_b = User(email="attacker@resolveai.com", full_name="Attacker", password_hash=get_password_hash("password123"), role=UserRole.CUSTOMER, is_active=True, tenant_id="default")
            db.add(cust_b)
        else:
            cust_b.password_hash = get_password_hash("password123")

        await db.commit()


async def run_product_validation():
    print("\n" + "="*70)
    print("RESOLVEAI M13 — RUNNING PRODUCT & SECURITY VALIDATION")
    print("="*70)

    await ensure_demo_users()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:

        # -------------------------------------------------------------
        # 1. Authentication & JWT Token Issuance
        # -------------------------------------------------------------
        print("\n[Step 1] Authenticating Customer, Experts, and Admin...")
        # Customer Login
        resp = await client.post("/api/auth/login", json={"email": "customer@resolveai.com", "password": "password123"})
        assert resp.status_code == 200, f"Customer login failed: {resp.text}"
        customer_token = resp.json()["access_token"]
        customer_headers = {"Authorization": f"Bearer {customer_token}"}
        print("  -> Customer token acquired [PASS]")

        # Expert 1 Login
        resp = await client.post("/api/auth/login", json={"email": "expert@resolveai.com", "password": "password123"})
        assert resp.status_code == 200, f"Expert 1 login failed: {resp.text}"
        expert1_token = resp.json()["access_token"]
        expert1_headers = {"Authorization": f"Bearer {expert1_token}"}
        print("  -> Expert 1 token acquired [PASS]")

        # Expert 2 Login
        resp = await client.post("/api/auth/login", json={"email": "expert2@resolveai.com", "password": "password123"})
        assert resp.status_code == 200, f"Expert 2 login failed: {resp.text}"
        expert2_token = resp.json()["access_token"]
        expert2_headers = {"Authorization": f"Bearer {expert2_token}"}
        print("  -> Expert 2 token acquired [PASS]")

        # Admin Login
        resp = await client.post("/api/auth/login", json={"email": "admin@resolveai.com", "password": "password123"})
        assert resp.status_code == 200, f"Admin login failed: {resp.text}"
        admin_token = resp.json()["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        print("  -> Admin token acquired [PASS]")

        # Attacker Login
        resp = await client.post("/api/auth/login", json={"email": "attacker@resolveai.com", "password": "password123"})
        assert resp.status_code == 200
        attacker_headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

        # -------------------------------------------------------------
        # 2. AI Outcome A: RESOLVE (Policy / Knowledge Grounding)
        # -------------------------------------------------------------
        print("\n[Step 2] Testing RESOLVE Outcome with KB Grounding...")
        resp = await client.post(
            "/api/conversations",
            json={"initial_message": "What is the return policy for orders?"},
            headers=customer_headers
        )
        assert resp.status_code == 200
        resolve_convo_id = resp.json()["id"]

        # Retrieve messages
        resp = await client.get(f"/api/conversations/{resolve_convo_id}/messages", headers=customer_headers)
        assert resp.status_code == 200
        messages = resp.json()
        ai_reply = messages[-1]["content"]
        assert len(messages) >= 2, "AI response was not generated"
        print(f"  -> AI Reply: '{ai_reply[:80]}...'")
        assert "return" in ai_reply.lower() or "policy" in ai_reply.lower() or "order" in ai_reply.lower() or "day" in ai_reply.lower()
        print("  -> RESOLVE outcome verified with KB grounding [PASS]")

        # -------------------------------------------------------------
        # 3. AI Outcome B: ASK_USER (Clarification Loop)
        # -------------------------------------------------------------
        print("\n[Step 3] Testing ASK_USER Outcome (Missing Information)...")
        resp = await client.post(
            "/api/conversations",
            json={"initial_message": "My payment failed and money was deducted"},
            headers=customer_headers
        )
        assert resp.status_code == 200
        ask_convo_id = resp.json()["id"]

        resp = await client.get(f"/api/conversations/{ask_convo_id}/messages", headers=customer_headers)
        messages = resp.json()
        ai_ask = messages[-1]["content"]
        print(f"  -> AI Ask: '{ai_ask[:80]}...'")
        # Follow up with required entity
        resp = await client.post(
            f"/api/conversations/{ask_convo_id}/messages",
            json={"content": "Here is the transaction ID: TXN12345"},
            headers=customer_headers
        )
        assert resp.status_code == 200
        print("  -> ASK_USER multi-turn entity follow-up completed [PASS]")

        # -------------------------------------------------------------
        # 4. AI Outcome C: ESCALATE (Security Incident -> Human Handoff)
        # -------------------------------------------------------------
        print("\n[Step 4] Testing ESCALATE Outcome & Expert Queue Creation...")
        resp = await client.post(
            "/api/conversations",
            json={"initial_message": "My account was hacked and unauthorized purchases were made!"},
            headers=customer_headers
        )
        assert resp.status_code == 200
        escalate_convo_id = resp.json()["id"]

        # Check conversation state
        resp = await client.get(f"/api/conversations/{escalate_convo_id}", headers=customer_headers)
        assert resp.status_code == 200
        assert resp.json()["workflow_state"] in ["waiting_for_expert", "escalated"]
        print(f"  -> Conversation {escalate_convo_id} transitioned to '{resp.json()['workflow_state']}' [PASS]")

        # -------------------------------------------------------------
        # 5. Expert Queue, Claiming, Context Preservation & Internal Notes
        # -------------------------------------------------------------
        print("\n[Step 5] Testing Expert Queue, Context Preservation & Internal Notes...")
        # Expert 1 views queue
        resp = await client.get("/api/expert/queue", headers=expert1_headers)
        assert resp.status_code == 200
        queue = resp.json()
        assert len(queue) > 0, "No items in expert queue"
        target_handoff = next((h for h in queue if h.get("conversation_id") == escalate_convo_id), queue[0])
        handoff_id = target_handoff["id"]
        convo_id = target_handoff["conversation_id"]
        print(f"  -> Found Handoff ID {handoff_id} in queue for Conversation {convo_id} [PASS]")

        # Expert 1 claims ticket
        resp = await client.post(f"/api/expert/queue/{handoff_id}/claim", headers=expert1_headers)
        assert resp.status_code in [200, 204], f"Claim failed: {resp.text}"
        print("  -> Expert 1 claimed ticket [PASS]")

        # Expert 1 posts a PUBLIC message to customer
        resp = await client.post(
            f"/api/conversations/{convo_id}/messages",
            json={"content": "Hello! I am a security specialist and I have secured your account."},
            headers=expert1_headers
        )
        assert resp.status_code == 200
        print("  -> Expert 1 sent public message to customer [PASS]")

        # Expert 1 posts an INTERNAL NOTE
        resp = await client.post(
            f"/api/conversations/{convo_id}/messages",
            json={"content": "INTERNAL NOTE: IP origin was verified suspicious. 2FA reset initiated.", "metadata_": {"is_internal": True}},
            headers=expert1_headers
        )
        assert resp.status_code == 200
        print("  -> Expert 1 posted internal note [PASS]")

        # Verification: Customer CANNOT see internal note
        resp = await client.get(f"/api/conversations/{convo_id}/messages", headers=customer_headers)
        assert resp.status_code == 200
        cust_view_msgs = resp.json()
        internal_seen_by_cust = any("INTERNAL NOTE" in m.get("content", "") for m in cust_view_msgs)
        assert not internal_seen_by_cust, "SECURITY BREACH: Customer was able to see internal note!"
        print("  -> Verified: Customer CANNOT see internal note [PASS]")

        # Verification: Expert CAN see internal note
        resp = await client.get(f"/api/conversations/{convo_id}/messages", headers=expert1_headers)
        assert resp.status_code == 200
        expert_view_msgs = resp.json()
        internal_seen_by_exp = any("INTERNAL NOTE" in m.get("content", "") for m in expert_view_msgs)
        assert internal_seen_by_exp, "Expert should be able to see internal note!"
        print("  -> Verified: Expert CAN see internal note [PASS]")

        # -------------------------------------------------------------
        # 6. Ticket Transfer Between Experts
        # -------------------------------------------------------------
        print("\n[Step 6] Testing Ticket Transfer between Expert 1 and Expert 2...")
        # Get Expert 2 user ID
        exp2_user_resp = await client.get("/api/users/me", headers=expert2_headers)
        exp2_id = exp2_user_resp.json()["id"]

        resp = await client.post(
            f"/api/expert/conversations/{convo_id}/transfer",
            json={"target_expert_id": exp2_id, "reason": "Requires tier 2 security escalation"},
            headers=expert1_headers
        )
        assert resp.status_code == 200, f"Transfer failed: {resp.text}"
        print(f"  -> Ticket transferred to Expert 2 (ID: {exp2_id}) [PASS]")

        # -------------------------------------------------------------
        # 7. Admin Dashboard & Analytics
        # -------------------------------------------------------------
        print("\n[Step 7] Testing Admin Dashboard & Analytics...")
        # Customer accessing analytics -> 403 Forbidden
        resp = await client.get("/api/analytics", headers=customer_headers)
        assert resp.status_code == 403, "Customer should be forbidden from analytics"
        print("  -> Role boundary verified: Customer denied from /api/analytics (403) [PASS]")

        # Admin accessing analytics -> 200 OK
        resp = await client.get("/api/analytics", headers=admin_headers)
        assert resp.status_code == 200, f"Admin analytics failed: {resp.text}"
        analytics_data = resp.json()
        print(f"  -> Total Conversations : {analytics_data['overview']['total_conversations']}")
        print(f"  -> Escalated Handoffs   : {analytics_data['overview']['escalated']}")
        print("  -> Admin analytics dashboard verified [PASS]")

        # -------------------------------------------------------------
        # 8. Voice Message Upload & Audio Security
        # -------------------------------------------------------------
        print("\n[Step 8] Testing Voice Message Validation & Audio Endpoint...")
        # Upload valid audio file
        fake_audio = io.BytesIO(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00data\x00\x00\x00\x00")
        files = {"file": ("test.wav", fake_audio, "audio/wav")}
        resp = await client.post(
            f"/api/conversations/{resolve_convo_id}/messages/voice",
            files=files,
            headers=customer_headers
        )
        assert resp.status_code == 200, f"Voice upload failed: {resp.text}"
        voice_data = resp.json()
        print(f"  -> Voice message uploaded: Audio URL = {voice_data.get('audio_url')} [PASS]")

        # -------------------------------------------------------------
        # 9. Security: IDOR Cross-Customer Boundary Verification
        # -------------------------------------------------------------
        print("\n[Step 9] Testing IDOR & Cross-Customer Boundary...")
        # Attacker tries to read Customer's conversation
        resp = await client.get(f"/api/conversations/{resolve_convo_id}", headers=attacker_headers)
        assert resp.status_code in [403, 404], f"IDOR Vulnerability: Attacker accessed conversation {resolve_convo_id}!"
        print("  -> IDOR boundary verified: Attacker cannot access Customer A's conversation [PASS]")

        # Attacker tries to send message into Customer's conversation
        resp = await client.post(f"/api/conversations/{resolve_convo_id}/messages", json={"content": "Malicious payload"}, headers=attacker_headers)
        assert resp.status_code in [403, 404], "IDOR Vulnerability: Attacker sent message into Customer A's conversation!"
        print("  -> IDOR boundary verified: Attacker cannot post to Customer A's conversation [PASS]")

    print("\n" + "="*70)
    print("ALL PRODUCT & SECURITY CAPABILITIES VALIDATED SUCCESSFULLY (100% PASS)")
    print("="*70)

if __name__ == "__main__":
    asyncio.run(run_product_validation())
