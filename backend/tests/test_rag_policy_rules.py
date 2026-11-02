import pytest
import asyncio
from app.database import async_session_factory
from app.rag.retriever import TFIDFRetriever
from app.rag.models import KnowledgeArticle
from sqlalchemy import select

@pytest.mark.asyncio
async def test_all_18_policies_exist_and_expanded():
    """Verify that all 18 policies exist in PostgreSQL with detailed sections."""
    async with async_session_factory() as session:
        for i in range(1, 19):
            code = f"POL-{i:03d}"
            stmt = select(KnowledgeArticle).where(
                KnowledgeArticle.title.like(f"{code}%"),
                KnowledgeArticle.tenant_id == "default"
            )
            res = await session.execute(stmt)
            art = res.scalar_one_or_none()
            assert art is not None, f"Policy {code} missing in database"
            assert art.is_active is True, f"Policy {code} should be active"
            assert len(art.content) > 500, f"Policy {code} content is too short: {len(art.content)} chars"
            
            # Verify required structural sections are present
            assert "**Purpose.**" in art.content, f"{code} missing Purpose section"
            assert "**Scope.**" in art.content, f"{code} missing Scope section"
            assert "**Rules.**" in art.content, f"{code} missing Rules section"
            assert "[CORE]" in art.content or "[EXT]" in art.content, f"{code} missing CORE/EXT markings"
            assert "**Resolution Steps" in art.content, f"{code} missing Resolution Steps"
            assert "**Customer Response Examples.**" in art.content, f"{code} missing Examples"
            assert "**Escalation" in art.content, f"{code} missing Escalation Triggers"
            assert "**Related Policies.**" in art.content, f"{code} missing Related Policies"

@pytest.mark.asyncio
async def test_policy_core_rules_intact():
    """Verify specific CORE business rules are preserved exactly."""
    async with async_session_factory() as session:
        # POL-001: 24/7 AI, Mon-Fri 9-6 human
        p1 = (await session.execute(select(KnowledgeArticle).where(KnowledgeArticle.title.like("POL-001%")))).scalar_one()
        assert "24 hours a day, 7 days a week" in p1.content
        assert "Monday through Friday, 9:00 AM to 6:00 PM EST" in p1.content
        assert "United States" in p1.content
        assert "USD ($)" in p1.content

        # POL-003: 3-5 business days, 48 hours late, 5 days lost
        p3 = (await session.execute(select(KnowledgeArticle).where(KnowledgeArticle.title.like("POL-003%")))).scalar_one()
        assert "3–5 business days from the shipment date" in p3.content
        assert "48 hours" in p3.content
        assert "5 days past the estimated delivery date" in p3.content

        # POL-004: Cancellation allowed only CREATED/PROCESSING
        p4 = (await session.execute(select(KnowledgeArticle).where(KnowledgeArticle.title.like("POL-004%")))).scalar_one()
        assert "CREATED" in p4.content and "PROCESSING" in p4.content
        assert "SHIPPED" in p4.content

        # POL-006: 30 days return
        p6 = (await session.execute(select(KnowledgeArticle).where(KnowledgeArticle.title.like("POL-006%")))).scalar_one()
        assert "within 30 calendar days" in p6.content
        assert "original packaging and condition" in p6.content

        # POL-007: Refund 24h processing, 3-5 days bank
        p7 = (await session.execute(select(KnowledgeArticle).where(KnowledgeArticle.title.like("POL-007%")))).scalar_one()
        assert "up to 24 hours" in p7.content
        assert "3–5 business days" in p7.content
        assert "original payment method" in p7.content

        # POL-008: Pending 15 min, failed reversal 24-48 hours
        p8 = (await session.execute(select(KnowledgeArticle).where(KnowledgeArticle.title.like("POL-008%")))).scalar_one()
        assert "15 minutes" in p8.content
        assert "24–48 hours" in p8.content

        # POL-011: 5 failed attempts locks for 30 minutes
        p11 = (await session.execute(select(KnowledgeArticle).where(KnowledgeArticle.title.like("POL-011%")))).scalar_one()
        assert "5 consecutive failed login attempts" in p11.content
        assert "locked for 30 minutes" in p11.content
        assert "at least 8 characters" in p11.content

        # POL-012: Critical fraud priority
        p12 = (await session.execute(select(KnowledgeArticle).where(KnowledgeArticle.title.like("POL-012%")))).scalar_one()
        assert "CRITICAL priority" in p12.content

@pytest.mark.asyncio
async def test_rag_retrieval_for_policies():
    """Verify RAG retrieval returns the improved policy articles for customer queries."""
    retriever = TFIDFRetriever()
    async with async_session_factory() as session:
        # Query 1: Returns
        res = await retriever.search("how many days do I have to return my delivered item", session, top_k=3, tenant_id="default")
        assert res["status"] == "RAG_SUCCESS"
        assert len(res["results"]) > 0
        titles = [r["title"] for r in res["results"]]
        assert any("POL-006" in t for t in titles), f"POL-006 not retrieved: {titles}"

        # Query 2: Cancellation
        res = await retriever.search("can I cancel my order if it has already shipped", session, top_k=3, tenant_id="default")
        assert res["status"] == "RAG_SUCCESS"
        titles = [r["title"] for r in res["results"]]
        assert any("POL-004" in t for t in titles), f"POL-004 not retrieved: {titles}"

        # Query 3: Address Change
        res = await retriever.search("I entered the wrong shipping address, change delivery address", session, top_k=3, tenant_id="default")
        assert res["status"] == "RAG_SUCCESS"
        titles = [r["title"] for r in res["results"]]
        assert any("POL-005" in t for t in titles), f"POL-005 not retrieved: {titles}"

        # Query 4: Account Locked
        res = await retriever.search("my account is locked after failed password attempts", session, top_k=3, tenant_id="default")
        assert res["status"] == "RAG_SUCCESS"
        titles = [r["title"] for r in res["results"]]
        assert any("POL-011" in t for t in titles), f"POL-011 not retrieved: {titles}"

        # Query 5: Security / Fraud
        res = await retriever.search("someone hacked my account unauthorized charges on my card", session, top_k=3, tenant_id="default")
        assert res["status"] == "RAG_SUCCESS"
        titles = [r["title"] for r in res["results"]]
        assert any("POL-012" in t for t in titles), f"POL-012 not retrieved: {titles}"

@pytest.mark.asyncio
async def test_tenant_isolation_in_rag():
    """Verify tenant isolation works between default and tenant_b."""
    retriever = TFIDFRetriever()
    async with async_session_factory() as session:
        # Default tenant search must NOT retrieve tenant_b articles
        res_default = await retriever.search("return policy 90 days tenant b", session, top_k=5, tenant_id="default")
        for r in res_default["results"]:
            assert "POL-B01" not in r["title"]
            assert "tenant_b" not in r["title"].lower()

        # Tenant_b search must only retrieve tenant_b articles
        res_b = await retriever.search("return policy", session, top_k=5, tenant_id="tenant_b")
        for r in res_b["results"]:
            assert "POL-006" not in r["title"]
            assert "POL-B01" in r["title"] or "TS-B01" in r["title"] or "TenantB" in r["title"]
