import pytest
from httpx import AsyncClient
from app.users.models import User
from app.auth.password import get_password_hash
from app.auth.jwt import create_access_token


# ============================================================================
# Section 1: Conversation & Ticket Flow (Core Endpoints)
# ============================================================================

@pytest.mark.asyncio
async def test_conversation_flow(async_client: AsyncClient, auth_headers_a):
    # 1. Create a conversation
    response = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "Hello, I have a payment issue.", "subject": "Payment Problem"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["customer_id"] > 0
    convo_id = data["id"]
    
    # 2. Check ticket was created
    ticket_res = await async_client.get("/api/tickets", headers=auth_headers_a)
    assert ticket_res.status_code == 200
    tickets = ticket_res.json()
    assert len(tickets) == 1
    assert tickets[0]["conversation_id"] == convo_id
    assert tickets[0]["subject"] == "Payment Problem"
    assert "metadata_" not in tickets[0] # No internal fields exposed
    
    # 2b. Check ticket summary
    summary_res = await async_client.get("/api/tickets/summary", headers=auth_headers_a)
    assert summary_res.status_code == 200
    summary = summary_res.json()
    assert summary["ai_processing"] >= 1
    
    # 2c. Check conversation list and detail
    convo_list_res = await async_client.get("/api/conversations", headers=auth_headers_a)
    assert convo_list_res.status_code == 200
    assert len(convo_list_res.json()) >= 1
    
    convo_detail_res = await async_client.get(f"/api/conversations/{convo_id}", headers=auth_headers_a)
    assert convo_detail_res.status_code == 200
    assert convo_detail_res.json()["id"] == convo_id

    # 3. Check messages (Should have customer initial message + AI response)
    msg_res = await async_client.get(f"/api/conversations/{convo_id}/messages", headers=auth_headers_a)
    assert msg_res.status_code == 200
    messages = msg_res.json()
    assert len(messages) == 2
    assert messages[0]["sender_type"] == "customer"
    assert messages[0]["content"] == "Hello, I have a payment issue."
    assert messages[1]["sender_type"] == "ai"
    assert "transaction id" in messages[1]["content"].lower()

    # 4. Add another message
    new_msg_res = await async_client.post(
        f"/api/conversations/{convo_id}/messages",
        headers=auth_headers_a,
        json={"content": "What about my password?"}
    )
    assert new_msg_res.status_code == 200
    messages = new_msg_res.json()
    assert len(messages) == 4
    assert messages[2]["sender_type"] == "customer"
    assert messages[2]["content"] == "What about my password?"
    assert messages[3]["sender_type"] == "ai"
    assert "password" in messages[3]["content"].lower() or "security" in messages[3]["content"].lower()


@pytest.mark.asyncio
async def test_conversation_security_404(async_client: AsyncClient, auth_headers_a, auth_headers_b):
    # User A creates conversation
    response = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "Secret message"}
    )
    convo_id = response.json()["id"]

    # User B tries to access User A's conversation
    res = await async_client.get(f"/api/conversations/{convo_id}", headers=auth_headers_b)
    assert res.status_code == 404

    # User B tries to access User A's messages
    res_msg = await async_client.get(f"/api/conversations/{convo_id}/messages", headers=auth_headers_b)
    assert res_msg.status_code == 404

    # User B tries to post to User A's conversation
    res_post = await async_client.post(
        f"/api/conversations/{convo_id}/messages",
        headers=auth_headers_b,
        json={"content": "I am a hacker"}
    )
    assert res_post.status_code == 404
    
    # Get User A's ticket ID
    ticket_res = await async_client.get("/api/tickets", headers=auth_headers_a)
    ticket_id = ticket_res.json()[0]["id"]
    
    # User B tries to access User A's ticket
    ticket_res_b = await async_client.get(f"/api/tickets/{ticket_id}", headers=auth_headers_b)
    assert ticket_res_b.status_code == 404


@pytest.mark.asyncio
async def test_expert_voice_channel_connection(
    async_client: AsyncClient,
    auth_headers_a,
    auth_headers_expert,
    monkeypatch,
):
    from app.config import settings
    monkeypatch.setattr(settings, "livekit_url", "wss://livekit.example.com")
    monkeypatch.setattr(settings, "livekit_api_key", "devkey")
    monkeypatch.setattr(settings, "livekit_api_secret", "secretsecretsecretsecretsecretsecretsecret32")

    # 1. Customer creates a voice channel conversation
    response = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "Need help on voice call", "channel": "voice"}
    )
    assert response.status_code == 200
    convo_id = response.json()["id"]

    # 2. Expert connects to the voice channel
    token_res = await async_client.post(
        "/api/audio/livekit/token",
        headers=auth_headers_expert,
        json={"conversation_id": convo_id}
    )
    assert token_res.status_code == 200
    token_data = token_res.json()
    assert token_data["token"]
    assert token_data["participant_identity"].startswith("expert-")
    assert token_data["room_name"] == f"resolveai-convo-{convo_id}"

    # 3. Expert speaks in the voice channel
    utterance_res = await async_client.post(
        "/api/audio/livekit/utterance",
        headers=auth_headers_expert,
        json={
            "conversation_id": convo_id,
            "utterance_id": "test_expert_utt_1",
            "transcript": "Hello, this is support. I can assist you directly on this call."
        }
    )
    assert utterance_res.status_code == 200
    assert utterance_res.json()["status"] == "expert_message"

    # 4. Verify message exists in conversation
    msgs_res = await async_client.get(f"/api/conversations/{convo_id}/messages", headers=auth_headers_a)
    assert msgs_res.status_code == 200
    msgs = msgs_res.json()
    expert_msgs = [m for m in msgs if m["sender_type"] == "expert"]
    assert len(expert_msgs) == 1
    assert "assist you directly" in expert_msgs[0]["content"]


@pytest.mark.asyncio
async def test_end_livekit_call_mutual_termination(
    async_client: AsyncClient,
    auth_headers_a,
    auth_headers_b,
    auth_headers_expert,
):
    # 1. Customer A creates a voice conversation
    response = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "Voice call test", "channel": "voice"}
    )
    assert response.status_code == 200
    convo_id = response.json()["id"]

    # 2. Expert connects to the call
    await async_client.post(
        "/api/audio/livekit/token",
        headers=auth_headers_expert,
        json={"conversation_id": convo_id}
    )

    # 3. User B (unauthorized customer) tries to end call -> 403 Forbidden
    res_b = await async_client.post(
        "/api/audio/livekit/end-call",
        headers=auth_headers_b,
        json={"conversation_id": convo_id}
    )
    assert res_b.status_code == 403

    # 4. Expert ends call -> 200 OK with ended_by="expert"
    res_expert_end = await async_client.post(
        "/api/audio/livekit/end-call",
        headers=auth_headers_expert,
        json={"conversation_id": convo_id}
    )
    assert res_expert_end.status_code == 200
    assert res_expert_end.json()["status"] == "call_ended"
    assert res_expert_end.json()["ended_by"] == "expert"

    # 5. Customer A ends call -> 200 OK with ended_by="customer"
    res_cust_end = await async_client.post(
        "/api/audio/livekit/end-call",
        headers=auth_headers_a,
        json={"conversation_id": convo_id}
    )
    assert res_cust_end.status_code == 200
    assert res_cust_end.json()["status"] == "call_ended"
    assert res_cust_end.json()["ended_by"] == "customer"


# ============================================================================
# Section 2: Conversational Pipeline (M4 Pipeline Decisions & Multiturn)
# ============================================================================

@pytest.mark.asyncio
async def test_m4_password_question_resolve(async_client: AsyncClient, auth_headers_a):
    response = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "How do I reset my password?", "subject": "Password reset"}
    )
    assert response.status_code == 200
    convo_id = response.json()["id"]
    
    msg_res = await async_client.get(f"/api/conversations/{convo_id}/messages", headers=auth_headers_a)
    messages = msg_res.json()
    
    ai_msg = messages[-1]
    assert ai_msg["sender_type"] == "ai"
    assert "Forgot Password" in ai_msg["content"] # Based on seed knowledge


@pytest.mark.asyncio
async def test_m4_payment_missing_txn_id(async_client: AsyncClient, auth_headers_a):
    # Missing TXN ID
    response = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "My payment failed yesterday.", "subject": "Payment fail"}
    )
    convo_id = response.json()["id"]
    
    msg_res = await async_client.get(f"/api/conversations/{convo_id}/messages", headers=auth_headers_a)
    messages = msg_res.json()
    ai_msg = messages[-1]
    assert "transaction ID" in ai_msg["content"]
    
    # Check workflow state
    convo_res = await async_client.get(f"/api/conversations/{convo_id}", headers=auth_headers_a)
    assert convo_res.json()["workflow_state"] == "asking_user"


@pytest.mark.asyncio
async def test_m4_payment_with_txn_id_resolves(async_client: AsyncClient, auth_headers_a):
    # With TXN ID
    response = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "My payment failed. TXN12345", "subject": "Payment fail"}
    )
    convo_id = response.json()["id"]
    
    msg_res = await async_client.get(f"/api/conversations/{convo_id}/messages", headers=auth_headers_a)
    messages = msg_res.json()
    ai_msg = messages[-1]
    # Now it should use the get_order_status tool (M12.3)
    assert "shipped" in ai_msg["content"].lower() or "order" in ai_msg["content"].lower() or "transaction" in ai_msg["content"].lower()


@pytest.mark.asyncio
async def test_m4_security_incident_escalates(async_client: AsyncClient, auth_headers_a):
    response = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "Someone accessed my account and stole money!", "subject": "Hacked"}
    )
    convo_id = response.json()["id"]
    
    msg_res = await async_client.get(f"/api/conversations/{convo_id}/messages", headers=auth_headers_a)
    messages = msg_res.json()
    ai_msg = messages[-1]
    
    assert "expert" in ai_msg["content"].lower() and ("escalat" in ai_msg["content"].lower() or "join" in ai_msg["content"].lower())
    
    convo_res = await async_client.get(f"/api/conversations/{convo_id}", headers=auth_headers_a)
    assert convo_res.json()["workflow_state"] == "waiting_for_expert"
    
    ticket_res = await async_client.get("/api/tickets", headers=auth_headers_a)
    ticket = next(t for t in ticket_res.json() if t["conversation_id"] == convo_id)
    assert ticket["status"] == "escalated"


@pytest.mark.asyncio
async def test_m4_normal_security_not_critical(async_client: AsyncClient, auth_headers_a):
    response = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "How do I lock my account?", "subject": "Security settings"}
    )
    convo_id = response.json()["id"]
    
    msg_res = await async_client.get(f"/api/conversations/{convo_id}/messages", headers=auth_headers_a)
    ai_msg = msg_res.json()[-1]
    # Uses RAG instead of immediate escalation
    assert "temporarily locked" in ai_msg["content"].lower() or "locked" in ai_msg["content"].lower()


@pytest.mark.asyncio
async def test_m4_unknown_question(async_client: AsyncClient, auth_headers_a):
    response = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "What is the capital of France?", "subject": "Unknown"}
    )
    convo_id = response.json()["id"]
    
    msg_res = await async_client.get(f"/api/conversations/{convo_id}/messages", headers=auth_headers_a)
    ai_msg = msg_res.json()[-1]
    assert "provide more details" in ai_msg["content"].lower() or "trouble understanding" in ai_msg["content"].lower()
    
    convo_res = await async_client.get(f"/api/conversations/{convo_id}", headers=auth_headers_a)
    assert convo_res.json()["workflow_state"] == "asking_user"


@pytest.mark.asyncio
async def test_m4_tamil_input(async_client: AsyncClient, auth_headers_a):
    # The language detector detects Tamil if script matches or keywords
    response = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "ennoda panam illai", "subject": "Tamil issue"}
    )
    convo_id = response.json()["id"]
    msg_res = await async_client.get(f"/api/conversations/{convo_id}/messages", headers=auth_headers_a)
    messages = msg_res.json()
    ai_msg = messages[-1]
    
    # It should classify as PAYMENT_ISSUE and ask for transaction ID
    assert "transaction ID" in ai_msg["content"]


@pytest.mark.asyncio
async def test_m4_multi_turn_context(async_client: AsyncClient, auth_headers_a):
    # 1. Start payment issue without TXN
    response = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "My payment failed yesterday.", "subject": "Payment fail"}
    )
    convo_id = response.json()["id"]
    
    # 2. Add message with TXN ID
    response2 = await async_client.post(
        f"/api/conversations/{convo_id}/messages",
        headers=auth_headers_a,
        json={"content": "It is TXN98765"}
    )
    
    messages = response2.json()
    ai_msg = messages[-1]
    
    # Should now use get_order_status tool because intent PAYMENT_ISSUE was preserved and txn id added
    assert "shipped" in ai_msg["content"].lower() or "order" in ai_msg["content"].lower() or "transaction" in ai_msg["content"].lower()


# ============================================================================
# Section 3: Admin & Analytics Endpoints (M8)
# ============================================================================

@pytest.mark.asyncio
async def test_admin_analytics(async_client: AsyncClient, auth_headers_admin: dict):
    response = await async_client.get("/api/analytics", headers=auth_headers_admin)
    assert response.status_code == 200
    data = response.json()
    assert "overview" in data
    assert "intents" in data
    
    overview = data["overview"]
    assert "total_conversations" in overview
    assert "ai_resolved" in overview
    assert "expert_resolved" in overview
    assert "escalated" in overview
    
    # Intents is a list
    assert isinstance(data["intents"], list)


@pytest.mark.asyncio
async def test_non_admin_cannot_access_analytics(async_client: AsyncClient, auth_headers_expert: dict, auth_headers_a: dict):
    res_expert = await async_client.get("/api/analytics", headers=auth_headers_expert)
    assert res_expert.status_code == 403
    
    res_customer = await async_client.get("/api/analytics", headers=auth_headers_a)
    assert res_customer.status_code == 403
