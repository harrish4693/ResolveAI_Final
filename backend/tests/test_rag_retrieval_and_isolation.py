import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.rag.models import KnowledgeArticle
from app.users.models import User
from app.auth.password import get_password_hash
from app.auth.jwt import create_access_token
from app.rag.retriever import FAISSRetriever, TFIDFRetriever
from app.config import settings


# ============================================================================
# Section 1: Tenant-Scoped Fixtures
# ============================================================================

@pytest_asyncio.fixture
async def admin_a(db_session: AsyncSession):
    user = User(
        email="admin_a@tenant_a.com",
        full_name="Admin A",
        password_hash=get_password_hash("Test1234"),
        role="admin",
        tenant_id="tenant_a"
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_b(db_session: AsyncSession):
    user = User(
        email="admin_b@tenant_b.com",
        full_name="Admin B",
        password_hash=get_password_hash("Test1234"),
        role="admin",
        tenant_id="tenant_b"
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def auth_a(admin_a):
    token = create_access_token(admin_a.id, "admin")
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def auth_b(admin_b):
    token = create_access_token(admin_b.id, "admin")
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def customer_a(db_session: AsyncSession):
    user = User(
        email="customer_a@tenant_a.com",
        full_name="Customer A",
        password_hash=get_password_hash("Test1234"),
        role="customer",
        tenant_id="tenant_a"
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def auth_customer_a(customer_a):
    token = create_access_token(customer_a.id, "customer")
    return {"Authorization": f"Bearer {token}"}


# ============================================================================
# Section 2: Knowledge CRUD & Tenant Isolation (API Level)
# ============================================================================

@pytest.mark.asyncio
async def test_schema_create_tenant_ownership(async_client: AsyncClient, auth_a):
    """1. API/create accepts valid tenant ownership and 2. preserves it in DB."""
    payload = {
        "title": "Tenant A Policy",
        "content": "Policy content",
        "category": "GENERAL",
        "tenant_id": "tenant_a" # Valid because it matches user's tenant
    }
    resp = await async_client.post("/api/knowledge", json=payload, headers=auth_a)
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Tenant A Policy"
    assert data["tenant_id"] == "tenant_a"


@pytest.mark.asyncio
async def test_schema_rejects_cross_tenant_ownership(async_client: AsyncClient, auth_a):
    """3. Invalid/cross-tenant ownership is rejected."""
    payload = {
        "title": "Malicious Policy",
        "content": "Content",
        "category": "GENERAL",
        "tenant_id": "tenant_b" # Trying to create for tenant_b using admin_a
    }
    resp = await async_client.post("/api/knowledge", json=payload, headers=auth_a)
    assert resp.status_code == 403
    assert "Cannot create article for different tenant" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_crud_isolation_read(async_client: AsyncClient, auth_a, auth_b):
    """4. Tenant A cannot read Tenant B article."""
    resp = await async_client.post("/api/knowledge", json={
        "title": "Tenant B Policy",
        "content": "B Content",
        "category": "GENERAL"
    }, headers=auth_b)
    assert resp.status_code == 200
    
    resp_a = await async_client.get("/api/knowledge", headers=auth_a)
    assert resp_a.status_code == 200
    titles = [a["title"] for a in resp_a.json()]
    assert "Tenant B Policy" not in titles


@pytest.mark.asyncio
async def test_customer_cannot_read_internal_knowledge(async_client: AsyncClient, auth_a, auth_customer_a):
    """Customer cannot read internal knowledge base articles."""
    resp = await async_client.post("/api/knowledge", json={
        "title": "Confidential Staff SOP",
        "content": "Internal guidance only",
        "category": "INTERNAL"
    }, headers=auth_a)
    assert resp.status_code == 200

    resp_admin = await async_client.get("/api/knowledge", headers=auth_a)
    assert resp_admin.status_code == 200
    admin_titles = [a["title"] for a in resp_admin.json()]
    assert "Confidential Staff SOP" in admin_titles

    resp_cust = await async_client.get("/api/knowledge", headers=auth_customer_a)
    assert resp_cust.status_code == 200
    assert resp_cust.json() == []


@pytest.mark.asyncio
async def test_crud_isolation_update(async_client: AsyncClient, auth_a, auth_b):
    """5. Tenant A cannot update Tenant B article."""
    resp = await async_client.post("/api/knowledge", json={
        "title": "Tenant B Policy",
        "content": "B Content",
        "category": "GENERAL"
    }, headers=auth_b)
    article_id = resp.json()["id"]

    resp_a = await async_client.put(f"/api/knowledge/{article_id}", json={
        "title": "Hacked Title",
        "content": "B Content",
        "category": "GENERAL"
    }, headers=auth_a)
    assert resp_a.status_code == 404


@pytest.mark.asyncio
async def test_faiss_freshness_update(async_client: AsyncClient, auth_a, db_session: AsyncSession, monkeypatch):
    """Confirm updating article in FAISS reflects immediately without restart."""
    monkeypatch.setattr(settings, "openai_api_key", "test_key")
    async def mock_get_embeddings(texts):
        return [[0.1] * 1536 for _ in texts]
    monkeypatch.setattr(FAISSRetriever, "_get_embeddings", mock_get_embeddings)
    
    resp = await async_client.post("/api/knowledge", json={
        "title": "Version 1 Policy",
        "content": "This is version 1",
        "category": "GENERAL"
    }, headers=auth_a)
    article_id = resp.json()["id"]
    
    retriever = FAISSRetriever()
    search_res = await retriever.search("query", db_session, tenant_id="tenant_a")
    assert search_res["status"] == "RAG_SUCCESS"
    assert "Version 1 Policy" in [r["title"] for r in search_res["results"]]
    
    await async_client.put(f"/api/knowledge/{article_id}", json={
        "title": "Version 2 Policy",
        "content": "This is version 2",
        "category": "GENERAL"
    }, headers=auth_a)
    
    search_res2 = await retriever.search("query", db_session, tenant_id="tenant_a")
    assert search_res2["status"] == "RAG_SUCCESS"
    titles = [r["title"] for r in search_res2["results"]]
    assert "Version 2 Policy" in titles
    assert "Version 1 Policy" not in titles


@pytest.mark.asyncio
async def test_faiss_freshness_deactivation(async_client: AsyncClient, auth_a, db_session: AsyncSession, monkeypatch):
    """Confirm deactivated article is no longer retrieved."""
    monkeypatch.setattr(settings, "openai_api_key", "test_key")
    async def mock_get_embeddings(texts):
        return [[0.1] * 1536 for _ in texts]
    monkeypatch.setattr(FAISSRetriever, "_get_embeddings", mock_get_embeddings)
    
    resp = await async_client.post("/api/knowledge", json={
        "title": "Active Policy",
        "content": "This is active",
        "category": "GENERAL"
    }, headers=auth_a)
    article_id = resp.json()["id"]
    
    retriever = FAISSRetriever()
    search_res = await retriever.search("query", db_session, tenant_id="tenant_a")
    assert search_res["status"] == "RAG_SUCCESS"
    assert "Active Policy" in [r["title"] for r in search_res["results"]]
    
    await async_client.put(f"/api/knowledge/{article_id}", json={
        "is_active": False,
        "title": "Active Policy",
        "content": "This is active",
        "category": "GENERAL"
    }, headers=auth_a)
    
    search_res2 = await retriever.search("query", db_session, tenant_id="tenant_a")
    if search_res2["status"] == "RAG_SUCCESS":
        titles = [r["title"] for r in search_res2["results"]]
        assert "Active Policy" not in titles


@pytest.mark.asyncio
async def test_faiss_tenant_isolation(async_client: AsyncClient, auth_a, auth_b, db_session: AsyncSession, monkeypatch):
    """Tenant A and Tenant B have similar policies; neither retrieves the other's content."""
    monkeypatch.setattr(settings, "openai_api_key", "test_key")
    async def mock_get_embeddings(texts):
        return [[0.1] * 1536 for _ in texts]
    monkeypatch.setattr(FAISSRetriever, "_get_embeddings", mock_get_embeddings)
    
    await async_client.post("/api/knowledge", json={
        "title": "Policy for A",
        "content": "A content",
        "category": "GENERAL"
    }, headers=auth_a)
    
    await async_client.post("/api/knowledge", json={
        "title": "Policy for B",
        "content": "B content",
        "category": "GENERAL"
    }, headers=auth_b)
    
    retriever = FAISSRetriever()
    
    search_a = await retriever.search("query", db_session, tenant_id="tenant_a")
    assert search_a["status"] == "RAG_SUCCESS"
    titles_a = [r["title"] for r in search_a["results"]]
    assert "Policy for A" in titles_a
    assert "Policy for B" not in titles_a
    
    search_b = await retriever.search("query", db_session, tenant_id="tenant_b")
    assert search_b["status"] == "RAG_SUCCESS"
    titles_b = [r["title"] for r in search_b["results"]]
    assert "Policy for B" in titles_b
    assert "Policy for A" not in titles_b


# ============================================================================
# Section 3: TF-IDF Tenant Isolation & Inactivity Handling
# ============================================================================

@pytest.mark.asyncio
async def test_tenant_isolation_retrieval(db_session: AsyncSession):
    article_a = KnowledgeArticle(
        title="Tenant A refund policy",
        content="Refunds for Tenant A take 14 days.",
        category="REFUND",
        tenant_id="Tenant A",
        is_active=True
    )
    article_b = KnowledgeArticle(
        title="Tenant B refund policy",
        content="Refunds for Tenant B take 30 days.",
        category="REFUND",
        tenant_id="Tenant B",
        is_active=True
    )
    
    db_session.add_all([article_a, article_b])
    await db_session.commit()
    
    retriever = TFIDFRetriever()
    retriever.__class__._built_tenants = set()
    
    # Test A: Tenant A query gets Tenant A knowledge only
    res_a = await retriever.search("How long do refunds take?", db_session, tenant_id="Tenant A")
    assert res_a["status"] == "RAG_SUCCESS"
    assert len(res_a["results"]) == 1
    assert "Tenant A" in res_a["results"][0]["title"]
    
    # Test B: Tenant B query gets Tenant B knowledge only
    res_b = await retriever.search("How long do refunds take?", db_session, tenant_id="Tenant B")
    assert res_b["status"] == "RAG_SUCCESS"
    assert len(res_b["results"]) == 1
    assert "Tenant B" in res_b["results"][0]["title"]
    
    # Test C: Tenant A searching for a Tenant B specific concept
    res_c = await retriever.search("Refunds for Tenant B take 30 days", db_session, tenant_id="Tenant A")
    if res_c["status"] == "RAG_SUCCESS":
        for r in res_c["results"]:
            assert "Tenant B" not in r["title"]
    
    # Test D: Missing tenant ID
    res_d = await retriever.search("refunds", db_session, tenant_id=None)
    assert res_d["status"] == "RAG_EMPTY"
    
    # Test E: Inactive article
    article_inactive = KnowledgeArticle(
        title="Inactive Tenant A policy",
        content="This should not be retrieved.",
        category="REFUND",
        tenant_id="Tenant A",
        is_active=False
    )
    db_session.add(article_inactive)
    await db_session.commit()
    
    retriever.__class__._built_tenants.discard("Tenant A")
    res_e = await retriever.search("Inactive", db_session, tenant_id="Tenant A")
    assert res_e["status"] == "RAG_EMPTY"


# ============================================================================
# Section 4: Live KB Refresh In Conversation Pipeline
# ============================================================================

@pytest.mark.asyncio
async def test_kb_refresh_affects_rag(async_client: AsyncClient, auth_headers_admin: dict, auth_headers_a: dict):
    # 1. Ask a question we don't know
    res1 = await async_client.post(
        "/api/conversations", 
        json={"initial_message": "What is the capital of France?"}, 
        headers=auth_headers_a
    )
    assert res1.status_code == 200
    convo1_id = res1.json()["id"]

    res1_msgs = await async_client.get(f"/api/conversations/{convo1_id}/messages", headers=auth_headers_a)
    ai_msg1 = res1_msgs.json()[-1]
    assert "provide more details" in ai_msg1["content"].lower() or "trouble understanding" in ai_msg1["content"].lower()
    
    # 2. Add an article to KB
    article_res = await async_client.post(
        "/api/knowledge",
        json={
            "title": "Capital of France",
            "content": "The capital of France is Paris.",
            "category": "General",
            "is_active": True
        },
        headers=auth_headers_admin
    )
    assert article_res.status_code == 200
    
    # 3. Ask the same question again
    res2 = await async_client.post(
        "/api/conversations", 
        json={"initial_message": "What is the capital of France?"}, 
        headers=auth_headers_a
    )
    convo2_id = res2.json()["id"]

    res2_msgs = await async_client.get(f"/api/conversations/{convo2_id}/messages", headers=auth_headers_a)
    ai_msg2 = res2_msgs.json()[-1]
    
    # Now it should resolve from knowledge base directly
    assert "paris" in ai_msg2["content"].lower()


# ============================================================================
# Section 5: FAISS Vector Retriever Low-Level Behavior & Error Handling
# ============================================================================

@pytest.mark.asyncio
async def test_faiss_empty_db(db_session: AsyncSession, monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    
    await db_session.execute(delete(KnowledgeArticle))
    await db_session.flush()

    FAISSRetriever._built_tenants = set()
    retriever = FAISSRetriever()
    res = await retriever.search("hello", db=db_session)
    assert res["status"] == "RAG_EMPTY"


@pytest.mark.asyncio
async def test_faiss_provider_failure(db_session: AsyncSession, monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "")
    retriever = FAISSRetriever()
    res = await retriever.search("hello", db=db_session)
    assert res["status"] == "RAG_PROVIDER_FAILURE"


@pytest.mark.asyncio
async def test_faiss_success_and_metadata(db_session: AsyncSession, monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    
    @classmethod
    async def mock_get_embeddings(cls, texts):
        return [[0.1]*1536 for _ in texts]
        
    monkeypatch.setattr(FAISSRetriever, "_get_embeddings", mock_get_embeddings)

    await db_session.execute(delete(KnowledgeArticle))

    article = KnowledgeArticle(title="Test", content="This is a test article.", category="test")
    db_session.add(article)
    await db_session.flush()
    
    FAISSRetriever._built_tenants = set()
    retriever = FAISSRetriever()
    res = await retriever.search("test", db=db_session)
    assert res["status"] == "RAG_SUCCESS"
    assert len(res["results"]) > 0
    assert res["results"][0]["title"] == "Test"
    assert "chunk_id" in res["results"][0]


@pytest.mark.asyncio
async def test_faiss_retry(db_session: AsyncSession, monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    
    from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
    from openai import APIConnectionError

    call_count = 0
    @classmethod
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=2),
        retry=retry_if_exception_type((APIConnectionError,))
    )
    async def failing_embeddings(cls, texts):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            import httpx
            raise APIConnectionError(request=httpx.Request("GET", "http://test"))
        return [[0.1]*1536 for _ in texts]
        
    monkeypatch.setattr(FAISSRetriever, "_get_embeddings", failing_embeddings)

    await db_session.execute(delete(KnowledgeArticle))

    article = KnowledgeArticle(title="Test", content="Retry me.", category="test")
    db_session.add(article)
    await db_session.flush()

    FAISSRetriever._built_tenants = set()
    retriever = FAISSRetriever()
    res = await retriever.search("retry", db=db_session)
    assert res["status"] == "RAG_SUCCESS"
    assert call_count == 3
