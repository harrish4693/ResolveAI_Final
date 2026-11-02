"""
ResolveAI V2 — Agentic Support Tools, Runtime, Execution & Reliability
======================================================================
Consolidated test suite covering:
  1. Tool Registry & Schema validation
  2. Core Tools (Order, Ticket, Account Info, Creation, Update) & Security Policies
  3. ToolRuntime Lifecycle, Confirmation & Idempotency
  4. Lower-Level Implemented Tool Boundary & Cross-Customer Isolation
  5. End-to-End Conversational Tool Invocation & Risk Escalation
  6. Tool Reliability, Retries, Timeouts & Failure Resilience
"""
import pytest
import json
import asyncio
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.commerce.models import Order, Transaction
from app.users.models import User
from app.conversations.models import Conversation
from app.tickets.models import Ticket
from app.ai.tools.registry import ToolRegistry
from app.ai.tools.runtime import ToolRuntime
from app.ai.tools.models import ToolExecution, ToolExecutionStatus
from app.ai.tools.base import BaseTool, ToolParameter, ToolSecurityPolicy
from app.ai.tools.implemented import GetOrderStatusTool, CheckTransactionTool
from app.shared.models import UserRole, TicketStatus, Priority


# ============================================================================
# Section 1: Tool Registry & Schemas
# ============================================================================

class TestToolRegistry:
    def test_registered_tools_exist(self):
        """All core support tools should be registered."""
        expected = [
            "get_order_status",
            "get_ticket_status",
            "get_customer_account_info",
            "create_support_ticket",
            "update_ticket_info",
            "request_human_support",
        ]
        for name in expected:
            assert ToolRegistry.has_tool(name), f"Tool {name} not registered"

    def test_unknown_tool_rejected(self):
        """Requesting an unregistered tool should raise ValueError."""
        with pytest.raises(ValueError, match="not found"):
            ToolRegistry.get_tool("delete_all_data")

    def test_get_all_schemas(self):
        """All schemas should contain name, description, risk_level."""
        schemas = ToolRegistry.get_all_schemas()
        assert len(schemas) >= 6
        for schema in schemas:
            assert "name" in schema
            assert "description" in schema
            assert "risk_level" in schema


# ============================================================================
# Section 2: Core Tools Execution, Validation & Ownership
# ============================================================================

@pytest.mark.asyncio
async def test_get_order_status_success(db_session: AsyncSession, test_user_a: User):
    """Valid ORD-prefixed order should return structured success."""
    order = Order(customer_id=test_user_a.id, tenant_id=test_user_a.tenant_id, order_number="ORD123", status="SHIPPED", tracking_number="12345")
    db_session.add(order)
    await db_session.flush()

    tool = ToolRegistry.get_tool("get_order_status")
    result = await tool.execute(db=db_session, user=test_user_a, conversation_id=1, order_id="ORD123")
    assert result["success"] is True
    assert result["tool"] == "get_order_status"
    assert result["data"]["status"] == "SHIPPED"
    assert "tracking_number" in result["data"]


@pytest.mark.asyncio
async def test_get_order_status_not_found(db_session: AsyncSession, test_user_a: User):
    """Non-existent order should return ORDER_NOT_FOUND."""
    tool = ToolRegistry.get_tool("get_order_status")
    result = await tool.execute(db=db_session, user=test_user_a, conversation_id=1, order_id="INVALID999")
    assert result["success"] is False
    assert result["error_code"] == "ORDER_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_order_status_missing_id(db_session: AsyncSession, test_user_a: User):
    """Missing order_id should return MISSING_ORDER_ID."""
    tool = ToolRegistry.get_tool("get_order_status")
    result = await tool.execute(db=db_session, user=test_user_a, conversation_id=1)
    assert result["success"] is False
    assert result["error_code"] == "MISSING_ORDER_ID"


@pytest.mark.asyncio
async def test_get_ticket_status_own_ticket(db_session: AsyncSession, test_user_a: User):
    """Customer should be able to view their own ticket."""
    convo = Conversation(customer_id=test_user_a.id)
    db_session.add(convo)
    await db_session.flush()

    ticket = Ticket(
        customer_id=test_user_a.id,
        conversation_id=convo.id,
        subject="Test Ticket",
        status=TicketStatus.OPEN,
        priority=Priority.MEDIUM,
    )
    db_session.add(ticket)
    await db_session.flush()

    tool = ToolRegistry.get_tool("get_ticket_status")
    result = await tool.execute(db=db_session, user=test_user_a, conversation_id=convo.id, ticket_id=str(ticket.id))
    assert result["success"] is True
    assert result["data"]["ticket_id"] == ticket.id
    assert result["data"]["status"] == "open"


@pytest.mark.asyncio
async def test_get_ticket_status_other_customer_denied(db_session: AsyncSession, test_user_a: User, test_user_b: User):
    """Customer A should NOT be able to view Customer B's ticket."""
    convo = Conversation(customer_id=test_user_b.id)
    db_session.add(convo)
    await db_session.flush()

    ticket = Ticket(
        customer_id=test_user_b.id,
        conversation_id=convo.id,
        subject="B's Ticket",
        status=TicketStatus.OPEN,
        priority=Priority.MEDIUM,
    )
    db_session.add(ticket)
    await db_session.flush()

    tool = ToolRegistry.get_tool("get_ticket_status")
    result = await tool.execute(db=db_session, user=test_user_a, conversation_id=convo.id, ticket_id=str(ticket.id))
    assert result["success"] is False
    assert result["error_code"] == "ACCESS_DENIED"


@pytest.mark.asyncio
async def test_get_ticket_status_invalid_id(db_session: AsyncSession, test_user_a: User):
    """Non-integer ticket_id should return INVALID_TICKET_ID."""
    tool = ToolRegistry.get_tool("get_ticket_status")
    result = await tool.execute(db=db_session, user=test_user_a, conversation_id=1, ticket_id="abc")
    assert result["success"] is False
    assert result["error_code"] == "INVALID_TICKET_ID"


@pytest.mark.asyncio
async def test_get_ticket_status_not_found(db_session: AsyncSession, test_user_a: User):
    """Non-existent ticket should return TICKET_NOT_FOUND."""
    tool = ToolRegistry.get_tool("get_ticket_status")
    result = await tool.execute(db=db_session, user=test_user_a, conversation_id=1, ticket_id="99999")
    assert result["success"] is False
    assert result["error_code"] == "TICKET_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_customer_account_info(db_session: AsyncSession, test_user_a: User):
    """Should return safe fields, never passwords or tokens."""
    tool = ToolRegistry.get_tool("get_customer_account_info")
    result = await tool.execute(db=db_session, user=test_user_a, conversation_id=1)
    assert result["success"] is True
    data = result["data"]
    assert data["full_name"] == test_user_a.full_name
    assert data["email"] == test_user_a.email
    result_str = json.dumps(result)
    assert "password" not in result_str.lower()
    assert "hash" not in result_str.lower()
    assert "token" not in result_str.lower()


@pytest.mark.asyncio
async def test_create_support_ticket_success(db_session: AsyncSession, test_user_a: User):
    """Should create a ticket and return its ID."""
    convo = Conversation(customer_id=test_user_a.id)
    db_session.add(convo)
    await db_session.flush()

    tool = ToolRegistry.get_tool("create_support_ticket")
    result = await tool.execute(
        db=db_session, user=test_user_a, conversation_id=convo.id,
        subject="My laptop is broken", priority="high"
    )
    assert result["success"] is True
    assert result["data"]["ticket_id"] is not None
    assert result["data"]["priority"] == "high"


@pytest.mark.asyncio
async def test_create_support_ticket_missing_subject(db_session: AsyncSession, test_user_a: User):
    """Missing subject should return MISSING_SUBJECT."""
    tool = ToolRegistry.get_tool("create_support_ticket")
    result = await tool.execute(db=db_session, user=test_user_a, conversation_id=1)
    assert result["success"] is False
    assert result["error_code"] == "MISSING_SUBJECT"


@pytest.mark.asyncio
async def test_update_ticket_own(db_session: AsyncSession, test_user_a: User):
    """Customer should be able to update their own ticket."""
    convo = Conversation(customer_id=test_user_a.id)
    db_session.add(convo)
    await db_session.flush()

    ticket = Ticket(
        customer_id=test_user_a.id, conversation_id=convo.id,
        subject="Original Subject", status=TicketStatus.OPEN, priority=Priority.MEDIUM,
    )
    db_session.add(ticket)
    await db_session.flush()

    tool = ToolRegistry.get_tool("update_ticket_info")
    result = await tool.execute(
        db=db_session, user=test_user_a, conversation_id=convo.id,
        ticket_id=str(ticket.id), new_subject="Updated Subject"
    )
    assert result["success"] is True
    assert result["data"]["subject"] == "Updated Subject"


@pytest.mark.asyncio
async def test_update_ticket_other_customer_denied(db_session: AsyncSession, test_user_a: User, test_user_b: User):
    """Customer A should NOT be able to update Customer B's ticket."""
    convo = Conversation(customer_id=test_user_b.id)
    db_session.add(convo)
    await db_session.flush()

    ticket = Ticket(
        customer_id=test_user_b.id, conversation_id=convo.id,
        subject="B Ticket", status=TicketStatus.OPEN, priority=Priority.MEDIUM,
    )
    db_session.add(ticket)
    await db_session.flush()

    tool = ToolRegistry.get_tool("update_ticket_info")
    result = await tool.execute(
        db=db_session, user=test_user_a, conversation_id=convo.id,
        ticket_id=str(ticket.id), new_subject="Hacked Subject"
    )
    assert result["success"] is False
    assert result["error_code"] == "ACCESS_DENIED"


@pytest.mark.asyncio
async def test_update_resolved_ticket_rejected(db_session: AsyncSession, test_user_a: User):
    """Cannot update a resolved ticket."""
    convo = Conversation(customer_id=test_user_a.id)
    db_session.add(convo)
    await db_session.flush()

    ticket = Ticket(
        customer_id=test_user_a.id, conversation_id=convo.id,
        subject="Resolved Ticket", status=TicketStatus.RESOLVED, priority=Priority.MEDIUM,
    )
    db_session.add(ticket)
    await db_session.flush()

    tool = ToolRegistry.get_tool("update_ticket_info")
    result = await tool.execute(
        db=db_session, user=test_user_a, conversation_id=convo.id,
        ticket_id=str(ticket.id), new_subject="Try to update"
    )
    assert result["success"] is False
    assert result["error_code"] == "TICKET_RESOLVED"


@pytest.mark.asyncio
async def test_request_human_support_signals_escalation(db_session: AsyncSession, test_user_a: User):
    """Should return escalate=True to signal the service layer."""
    tool = ToolRegistry.get_tool("request_human_support")
    result = await tool.execute(db=db_session, user=test_user_a, conversation_id=1, reason="Need expert help")
    assert result["success"] is True
    assert result["escalate"] is True
    assert result["data"]["reason"] == "Need expert help"


# ============================================================================
# Section 3: ToolRuntime Lifecycle, Confirmation & Idempotency
# ============================================================================

@pytest.mark.asyncio
async def test_idempotency_duplicate_request(db_session: AsyncSession, test_user_a: User):
    """Duplicate tool execution requests should return the same execution record."""
    convo = Conversation(customer_id=test_user_a.id)
    db_session.add(convo)
    await db_session.flush()

    exec1 = await ToolRuntime.request_tool_execution(
        db=db_session, conversation_id=convo.id, customer_id=test_user_a.id,
        expert_id=None, user=test_user_a, tool_name="get_order_status",
        kwargs={"order_id": "ORD123"}
    )
    exec2 = await ToolRuntime.request_tool_execution(
        db=db_session, conversation_id=convo.id, customer_id=test_user_a.id,
        expert_id=None, user=test_user_a, tool_name="get_order_status",
        kwargs={"order_id": "ORD123"}
    )
    assert exec1.id == exec2.id


@pytest.mark.asyncio
async def test_runtime_execute_order_tool(db_session: AsyncSession, test_user_a: User):
    """Full lifecycle: request -> execute -> SUCCEEDED with structured result."""
    convo = Conversation(customer_id=test_user_a.id)
    order = Order(customer_id=test_user_a.id, tenant_id=test_user_a.tenant_id, order_number="ORD456", status="SHIPPED")
    db_session.add_all([convo, order])
    await db_session.flush()

    execution = await ToolRuntime.request_tool_execution(
        db=db_session, conversation_id=convo.id, customer_id=test_user_a.id,
        expert_id=None, user=test_user_a, tool_name="get_order_status",
        kwargs={"order_id": "ORD456"}
    )
    assert execution.status == ToolExecutionStatus.PENDING

    execution = await ToolRuntime.execute(db_session, execution)
    assert execution.status == ToolExecutionStatus.SUCCEEDED

    result = json.loads(execution.result_summary)
    assert result["success"] is True
    assert result["data"]["status"] == "SHIPPED"


@pytest.mark.asyncio
async def test_runtime_confirmation_required(db_session: AsyncSession, test_user_a: User):
    """Tools requiring confirmation should start in AWAITING_CONFIRMATION."""
    convo = Conversation(customer_id=test_user_a.id)
    db_session.add(convo)
    await db_session.flush()

    execution = await ToolRuntime.request_tool_execution(
        db=db_session, conversation_id=convo.id, customer_id=test_user_a.id,
        expert_id=None, user=test_user_a, tool_name="create_support_ticket",
        kwargs={"subject": "Test confirmation"}
    )
    assert execution.status == ToolExecutionStatus.AWAITING_CONFIRMATION
    assert execution.requires_confirmation is True


@pytest.mark.asyncio
async def test_runtime_unconfirmed_execution_fails(db_session: AsyncSession, test_user_a: User):
    """Executing a confirmation-required tool without confirming should fail."""
    convo = Conversation(customer_id=test_user_a.id)
    db_session.add(convo)
    await db_session.flush()

    execution = await ToolRuntime.request_tool_execution(
        db=db_session, conversation_id=convo.id, customer_id=test_user_a.id,
        expert_id=None, user=test_user_a, tool_name="create_support_ticket",
        kwargs={"subject": "Test unconfirmed"}
    )
    execution = await ToolRuntime.execute(db_session, execution)
    assert execution.status == ToolExecutionStatus.FAILED
    assert execution.error_code == "UNCONFIRMED"


# ============================================================================
# Section 4: Implemented Tools & Low-Level Tenant / Customer Isolation
# ============================================================================

@pytest.mark.asyncio
async def test_order_status_valid_owned(db_session: AsyncSession):
    user = User(id=1, email="user@test.com", password_hash="hash", full_name="User", role="customer", tenant_id="t1")
    order = Order(customer_id=1, tenant_id="t1", order_number="ORD1", status="SHIPPED")
    db_session.add(user)
    db_session.add(order)
    await db_session.flush()

    tool = GetOrderStatusTool()
    res = await tool.execute(db=db_session, user=user, conversation_id=1, order_id="ORD1")
    assert res["success"] is True
    assert res["data"]["order_id"] == "ORD1"


@pytest.mark.asyncio
async def test_order_status_cross_customer(db_session: AsyncSession):
    user1 = User(id=1, email="user1@test.com", password_hash="hash", full_name="User1", role="customer", tenant_id="t1")
    user2 = User(id=2, email="user2@test.com", password_hash="hash", full_name="User2", role="customer", tenant_id="t1")
    order = Order(customer_id=2, tenant_id="t1", order_number="ORD2", status="SHIPPED")
    db_session.add_all([user1, user2, order])
    await db_session.flush()

    tool = GetOrderStatusTool()
    res = await tool.execute(db=db_session, user=user1, conversation_id=1, order_id="ORD2")
    assert res["success"] is False
    assert res["error_code"] in ("ACCESS_DENIED", "ORDER_NOT_FOUND")


@pytest.mark.asyncio
async def test_order_status_cross_tenant(db_session: AsyncSession):
    user1 = User(id=1, email="user1@test.com", password_hash="hash", full_name="User1", role="customer", tenant_id="t1")
    order = Order(customer_id=1, tenant_id="t2", order_number="ORD3", status="SHIPPED")
    db_session.add_all([user1, order])
    await db_session.flush()

    tool = GetOrderStatusTool()
    res = await tool.execute(db=db_session, user=user1, conversation_id=1, order_id="ORD3")
    assert res["success"] is False
    assert res["error_code"] in ("ACCESS_DENIED", "ORDER_NOT_FOUND")


@pytest.mark.asyncio
async def test_transaction_valid_owned(db_session: AsyncSession):
    user = User(id=1, email="user@test.com", password_hash="hash", full_name="User", role="customer", tenant_id="t1")
    txn = Transaction(customer_id=1, tenant_id="t1", transaction_id="TXN1", amount=100.0, status="COMPLETED")
    db_session.add_all([user, txn])
    await db_session.flush()

    tool = CheckTransactionTool()
    res = await tool.execute(db=db_session, user=user, conversation_id=1, transaction_id="TXN1")
    assert res["success"] is True
    assert res["data"]["transaction_id"] == "TXN1"


@pytest.mark.asyncio
async def test_transaction_cross_customer_or_tenant(db_session: AsyncSession):
    user1 = User(id=1, email="u1@test.com", password_hash="h", full_name="u1", role="customer", tenant_id="t1")
    txn_cross_cust = Transaction(customer_id=2, tenant_id="t1", transaction_id="TXN2", amount=100.0, status="COMPLETED")
    txn_cross_tenant = Transaction(customer_id=1, tenant_id="t2", transaction_id="TXN3", amount=100.0, status="COMPLETED")
    db_session.add_all([user1, txn_cross_cust, txn_cross_tenant])
    await db_session.flush()

    tool = CheckTransactionTool()
    res1 = await tool.execute(db=db_session, user=user1, conversation_id=1, transaction_id="TXN2")
    assert res1["success"] is False

    res2 = await tool.execute(db=db_session, user=user1, conversation_id=1, transaction_id="TXN3")
    assert res2["success"] is False


@pytest.mark.asyncio
async def test_tool_malformed_args(db_session: AsyncSession):
    user = User(id=1, email="user@test.com", password_hash="hash", full_name="User", role="customer", tenant_id="t1")
    tool = GetOrderStatusTool()
    res = await tool.execute(db=db_session, user=user, conversation_id=1)
    assert res["success"] is False
    assert res["error_code"] == "MISSING_ORDER_ID"


@pytest.mark.asyncio
async def test_tool_nonexistent(db_session: AsyncSession):
    user = User(id=1, email="user@test.com", password_hash="hash", full_name="User", role="customer", tenant_id="t1")
    tool = GetOrderStatusTool()
    res = await tool.execute(db=db_session, user=user, conversation_id=1, order_id="NOTREAL")
    assert res["success"] is False
    assert res["error_code"] == "ORDER_NOT_FOUND"


@pytest.mark.asyncio
async def test_tool_fake_llm_ids(db_session: AsyncSession):
    user = User(id=1, email="user@test.com", password_hash="hash", full_name="User", role="customer", tenant_id="t1")
    order_cross = Order(customer_id=2, tenant_id="t1", order_number="ORD2", status="SHIPPED")
    db_session.add_all([user, order_cross])
    await db_session.flush()

    tool = GetOrderStatusTool()
    res = await tool.execute(db=db_session, user=user, conversation_id=1, order_id="ORD2", customer_id=2, tenant_id="t1")
    assert res["success"] is False
    assert res["error_code"] in ("ACCESS_DENIED", "ORDER_NOT_FOUND")


# ============================================================================
# Section 5: End-to-End Conversational Tool Execution & Risk Handling
# ============================================================================

@pytest.mark.asyncio
async def test_use_tool_decision(async_client: AsyncClient, auth_headers_a: dict, test_user_a: User, db_session: AsyncSession):
    order = Order(customer_id=test_user_a.id, tenant_id=test_user_a.tenant_id, order_number="ORD123", status="SHIPPED", tracking_number="XYZ")
    db_session.add(order)
    await db_session.commit()

    res = await async_client.post(
        "/api/conversations",
        json={"initial_message": "My delivery failed. Can you check my order ORD123?"},
        headers=auth_headers_a
    )
    assert res.status_code == 200
    convo_id = res.json()["id"]

    res2 = await async_client.get(f"/api/conversations/{convo_id}/messages", headers=auth_headers_a)
    messages = res2.json()

    assert len(messages) >= 2
    ai_msg = messages[-1]
    assert ai_msg["sender_type"] == "ai"
    assert "shipped" in ai_msg["content"].lower() or "delivery" in ai_msg["content"].lower()


@pytest.mark.asyncio
async def test_ask_user_for_missing_entity(async_client: AsyncClient, auth_headers_a: dict):
    res = await async_client.post(
        "/api/conversations", 
        json={"initial_message": "My payment failed."}, 
        headers=auth_headers_a
    )
    assert res.status_code == 200
    convo_id = res.json()["id"]

    res2 = await async_client.get(f"/api/conversations/{convo_id}/messages", headers=auth_headers_a)
    messages = res2.json()
    ai_msg = messages[-1]
    assert "transaction id" in ai_msg["content"].lower()


@pytest.mark.asyncio
async def test_check_transaction_idempotency_and_grounding(async_client: AsyncClient, db_session: AsyncSession, auth_headers_a):
    payload = {
        "initial_message": "Can you check transaction TXN12345?",
        "subject": "TXN check"
    }
    
    response = await async_client.post("/api/conversations", json=payload, headers=auth_headers_a)
    assert response.status_code == 200
    convo_id = response.json()["id"]
    
    msg_res = await async_client.get(f"/api/conversations/{convo_id}/messages", headers=auth_headers_a)
    messages = msg_res.json()
    ai_msg = messages[-1]
    
    assert "shipped" in ai_msg["content"].lower() or "order" in ai_msg["content"].lower() or "transaction" in ai_msg["content"].lower()
    
    stmt = select(ToolExecution).where(ToolExecution.conversation_id == convo_id)
    execs = (await db_session.execute(stmt)).scalars().all()
    assert len(execs) == 1
    assert execs[0].tool_name in ("check_transaction", "get_order_status")
    assert execs[0].status.value == "succeeded"


@pytest.mark.asyncio
async def test_refund_request_escalates(async_client: AsyncClient, db_session: AsyncSession, auth_headers_a):
    payload = {
        "initial_message": "I want a refund for TXN12345.",
        "subject": "Refund"
    }
    
    response = await async_client.post("/api/conversations", json=payload, headers=auth_headers_a)
    assert response.status_code == 200
    convo_id = response.json()["id"]
    
    msg_res = await async_client.get(f"/api/conversations/{convo_id}/messages", headers=auth_headers_a)
    messages = msg_res.json()
    ai_msg = messages[-1]
    assert ai_msg["sender_type"] == "ai"
    assert "expert" in ai_msg["content"].lower()
    
    convo_res = await async_client.get(f"/api/conversations/{convo_id}", headers=auth_headers_a)
    assert convo_res.json()["workflow_state"] in ("waiting_for_expert", "asking_user")


@pytest.mark.asyncio
async def test_update_request_escalates(async_client: AsyncClient, db_session: AsyncSession, auth_headers_a):
    payload = {
        "initial_message": "I want to update my phone to 123456789",
        "subject": "Update"
    }
    
    response = await async_client.post("/api/conversations", json=payload, headers=auth_headers_a)
    convo_id = response.json()["id"]
    
    msg_res = await async_client.get(f"/api/conversations/{convo_id}/messages", headers=auth_headers_a)
    messages = msg_res.json()
    ai_msg = messages[-1]
    assert ai_msg["sender_type"] == "ai"
    assert "expert" in ai_msg["content"].lower()
    
    convo_res = await async_client.get(f"/api/conversations/{convo_id}", headers=auth_headers_a)
    assert convo_res.json()["workflow_state"] in ("waiting_for_expert", "asking_user")


# ============================================================================
# Section 6: Tool Reliability, Retries, Timeouts & Error Resilience
# ============================================================================

class MockFailingTool(BaseTool):
    name = "mock_fail_tool"
    description = "Fails immediately"
    parameters = []
    security_policy = ToolSecurityPolicy(requires_confirmation=False, allowed_roles=["customer"])
    
    async def execute(self, **kwargs):
        raise ValueError("Permanent failure")


class MockTimeoutTool(BaseTool):
    name = "mock_timeout_tool"
    description = "Hangs forever"
    parameters = []
    security_policy = ToolSecurityPolicy(requires_confirmation=False, allowed_roles=["customer"])
    
    async def execute(self, **kwargs):
        await asyncio.sleep(60)
        return {"status": "success"}


class MockRetryTool(BaseTool):
    name = "mock_retry_tool"
    description = "Fails once, then succeeds"
    parameters = []
    security_policy = ToolSecurityPolicy(requires_confirmation=False, allowed_roles=["customer"])
    
    def __init__(self):
        self.attempts = 0
        
    async def execute(self, **kwargs):
        self.attempts += 1
        if self.attempts == 1:
            raise asyncio.TimeoutError("Transient failure")
        return {"status": "success", "attempts": self.attempts}


# Register mocks in tool registry
ToolRegistry._tools["mock_fail_tool"] = MockFailingTool()
ToolRegistry._tools["mock_timeout_tool"] = MockTimeoutTool()
ToolRegistry._tools["mock_retry_tool"] = MockRetryTool()


@pytest.mark.asyncio
async def test_transient_failure_retry(db_session, test_user_a):
    """Verify tool retries on transient errors."""
    customer = test_user_a
    
    execution = await ToolRuntime.request_tool_execution(
        db_session, conversation_id=1, customer_id=customer.id, expert_id=None,
        user=customer, tool_name="mock_retry_tool", kwargs={}
    )
    
    async def mock_sleep(seconds):
        pass

    with pytest.MonkeyPatch.context() as m:
        m.setattr("asyncio.sleep", mock_sleep)
        exec_result = await ToolRuntime.execute(db_session, execution, {})
        
    assert exec_result.status == ToolExecutionStatus.SUCCEEDED
    assert "attempts" in exec_result.result_summary


@pytest.mark.asyncio
async def test_permanent_failure_escalation(db_session, test_user_a):
    """Verify permanent tool failures are marked FAILED safely."""
    customer = test_user_a
    
    execution = await ToolRuntime.request_tool_execution(
        db_session, conversation_id=2, customer_id=customer.id, expert_id=None,
        user=customer, tool_name="mock_fail_tool", kwargs={}
    )
    
    exec_result = await ToolRuntime.execute(db_session, execution, {})
    assert exec_result.status == ToolExecutionStatus.FAILED
    assert exec_result.error_code == "TOOL_ERROR"


@pytest.mark.asyncio
async def test_tool_timeout(db_session, test_user_a, monkeypatch):
    """Verify timeout leads to controlled failure."""
    customer = test_user_a
    
    execution = await ToolRuntime.request_tool_execution(
        db_session, conversation_id=3, customer_id=customer.id, expert_id=None,
        user=customer, tool_name="mock_timeout_tool", kwargs={}
    )
    
    async def mock_wait_for(coro, timeout):
        raise asyncio.TimeoutError()
    
    async def mock_sleep(seconds):
        pass
        
    monkeypatch.setattr("asyncio.wait_for", mock_wait_for)
    monkeypatch.setattr("asyncio.sleep", mock_sleep)
    
    exec_result = await ToolRuntime.execute(db_session, execution, {})
    assert exec_result.status == ToolExecutionStatus.FAILED
    assert exec_result.error_code == "TOOL_TIMEOUT"


@pytest.mark.asyncio
async def test_expired_confirmation(db_session, test_user_a):
    """Verify expired confirmation is rejected."""
    customer = test_user_a
    
    class MockConfTool(BaseTool):
        name = "mock_conf"
        description = "Requires conf"
        parameters = []
        security_policy = ToolSecurityPolicy(requires_confirmation=True, allowed_roles=["customer"])
        
        async def execute(self, **kwargs):
            return {"status": "success"}

    ToolRegistry.register(MockConfTool())
    
    execution = await ToolRuntime.request_tool_execution(
        db_session, conversation_id=4, customer_id=customer.id, expert_id=None,
        user=customer, tool_name="mock_conf", kwargs={}
    )
    
    execution.started_at = datetime.now(timezone.utc) - timedelta(minutes=20)
    await db_session.commit()
    
    exec_result = await ToolRuntime.execute(db_session, execution, {})
    assert exec_result.status == ToolExecutionStatus.FAILED
    assert exec_result.error_code == "CONFIRMATION_EXPIRED"


@pytest.mark.asyncio
async def test_idempotency_under_retries(db_session, test_user_a):
    """Verify repeated executions yield one side effect."""
    customer = test_user_a
    
    execution1 = await ToolRuntime.request_tool_execution(
        db_session, conversation_id=5, customer_id=customer.id, expert_id=None,
        user=customer, tool_name="mock_fail_tool", kwargs={"test": 1}
    )
    
    execution2 = await ToolRuntime.request_tool_execution(
        db_session, conversation_id=5, customer_id=customer.id, expert_id=None,
        user=customer, tool_name="mock_fail_tool", kwargs={"test": 1}
    )
    
    assert execution1.id == execution2.id
    
    await ToolRuntime.execute(db_session, execution1, {})
    result2 = await ToolRuntime.execute(db_session, execution2, {})
    
    assert result2.status == ToolExecutionStatus.FAILED
