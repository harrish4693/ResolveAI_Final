import os
os.environ["AI_PROVIDER"] = "mock"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from typing import AsyncGenerator

from app.main import app
from app.database import Base, get_db
from app.config import settings

# TEST ISOLATION: Force AI provider to "mock" for all tests to ensure deterministic output
settings.ai_provider = "mock"
settings.database_url = "sqlite+aiosqlite:///:memory:"

from sqlalchemy.pool import StaticPool

# Use an in-memory SQLite database for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=StaticPool)
TestingSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

# Patch the application's async_session_factory so background tasks use the test DB
from app import database as app_database
from app.conversations import router as app_router
from app import main as app_main
app_database.async_session_factory = TestingSessionLocal
app_database.engine = engine
app_main.engine = engine
app_router.async_session_factory = TestingSessionLocal

from app.ai.m4.provider import M4AIProvider
app_router.conversation_service.ai_provider = M4AIProvider()

@pytest.fixture(autouse=True)
def reset_rate_limit_cache():
    from app.shared import middleware
    middleware._RATE_LIMIT_CACHE.clear()
    middleware._RATE_LIMIT_LOCK = None

@pytest_asyncio.fixture(scope="function", autouse=True)
async def setup_db() -> AsyncGenerator[None, None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    # Seed knowledge articles for tests
    from app.rag.models import KnowledgeArticle
    from tests.fixtures import INITIAL_ARTICLES
    from app.rag.retriever import TFIDFRetriever
    async with TestingSessionLocal() as session:
        for article_data in INITIAL_ARTICLES:
            article = KnowledgeArticle(**article_data)
            session.add(article)
        await session.commit()
        TFIDFRetriever.invalidate("default")
        await TFIDFRetriever.refresh(session, "default")
        
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        yield session

@pytest_asyncio.fixture(scope="function")
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    # Override the dependency to use our test database session factory
    async def override_get_db():
        async with TestingSessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
        
    app.dependency_overrides.clear()

from app.users.models import User
from app.auth.password import get_password_hash
from app.auth.jwt import create_access_token

@pytest_asyncio.fixture
async def test_user_a(db_session: AsyncSession):
    user = User(
        email="customer_a@example.com",
        full_name="Customer A",
        password_hash=get_password_hash("TestPassword123!"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

@pytest_asyncio.fixture
async def test_user_b(db_session: AsyncSession):
    user = User(
        email="customer_b@example.com",
        full_name="Customer B",
        password_hash=get_password_hash("TestPassword123!"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

@pytest_asyncio.fixture
async def test_expert(db_session: AsyncSession):
    user = User(
        email="expert@example.com",
        full_name="Test Expert",
        password_hash=get_password_hash("TestPassword123!"),
        role="expert"
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user
@pytest_asyncio.fixture
async def test_admin(db_session: AsyncSession):
    user = User(
        email="admin@example.com",
        full_name="Test Admin",
        password_hash=get_password_hash("TestPassword123!"),
        role="admin"
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user
@pytest.fixture
def auth_headers_a(test_user_a):
    token = create_access_token(test_user_a.id, "customer")
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def auth_headers_b(test_user_b):
    token = create_access_token(test_user_b.id, "customer")
    return {"Authorization": f"Bearer {token}"}
    
@pytest.fixture
def auth_headers_expert(test_expert):
    token = create_access_token(test_expert.id, "expert")
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def auth_headers_admin(test_admin):
    token = create_access_token(test_admin.id, "admin")
    return {"Authorization": f"Bearer {token}"}
