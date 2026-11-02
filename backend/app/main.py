"""
ResolveAIV2 — FastAPI Application Factory

Creates and configures the FastAPI application with all routers,
middleware, and lifecycle events.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from sqlalchemy import text
from app.config import settings
from app.database import create_tables, engine
from app.shared.middleware import setup_middleware
from app.core.logging import setup_logging

# Import all models so SQLAlchemy knows about them
from app.users.models import User  # noqa: F401
from app.conversations.models import Conversation, ConversationMessage  # noqa: F401
from app.tickets.models import Ticket  # noqa: F401
from app.handoff.models import Handoff, ExpertAssignment  # noqa: F401
from app.experts.models import Expert, ExpertSpecialization  # noqa: F401
from app.notifications.models import Notification  # noqa: F401
from app.feedback.models import Feedback  # noqa: F401
from app.rag.models import KnowledgeArticle  # noqa: F401
from app.auth.models import RefreshToken  # noqa: F401
from app.ai.tools.models import ToolExecution  # noqa: F401
from app.memory.models import ConversationMemory  # noqa: F401
from app.commerce.models import Order, Transaction  # noqa: F401
from app.ai.autonomy_models import AutonomyConfig  # noqa: F401
from app.ai.incident_models import IncidentRecord  # noqa: F401

logger = logging.getLogger(__name__)


async def check_migration_status():
    """Checks whether database schema matches the latest Alembic migration head."""
    if "sqlite" in settings.database_url:
        return
    try:
        import os
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        ini_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic.ini")
        if not os.path.exists(ini_path):
            return

        cfg = Config(ini_path)
        script = ScriptDirectory.from_config(cfg)
        heads = set(script.get_heads())

        from app import database as app_db
        async with app_db.engine.connect() as conn:
            res = await conn.execute(text("SELECT version_num FROM alembic_version"))
            db_revs = set(row[0] for row in res.fetchall())

        if not heads.issubset(db_revs):
            logger.warning(
                "⚠️ DATABASE MIGRATION WARNING: Database revision (%s) is behind Alembic head (%s). "
                "Run 'python -m alembic upgrade head' to apply pending migrations and avoid runtime column errors.",
                db_revs,
                heads,
            )
        else:
            logger.info("Database migration check passed: DB revision (%s) is up to date with head.", db_revs)
    except Exception as e:
        logger.debug(f"Migration status check skipped or unavailable: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: startup and shutdown."""
    # Startup
    logger.info(f"Starting {settings.app_name} ({settings.app_env})")
    logger.info(f"AI Provider: {settings.ai_provider}")
    logger.info(f"RAG Retriever: {settings.rag_retriever}")
    logger.info(f"STT Provider: {settings.stt_provider}")
    logger.info(f"TTS Provider: {settings.tts_provider}")
    logger.info(f"Email Enabled: {settings.email_enabled}")

    # Create tables in development for SQLite (use Alembic for Postgres)
    if settings.is_development and "sqlite" in settings.database_url:
        await create_tables()
        logger.info("Database tables created/verified")

    # Verify migration revision status
    await check_migration_status()

    yield

    # Shutdown
    logger.info(f"Shutting down {settings.app_name}")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    
    # Configure structured logging
    setup_logging()

    app = FastAPI(
        title=settings.app_name,
        description="AI-First Customer Support Platform",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.debug else None,
        redoc_url="/api/redoc" if settings.debug else None,
    )

    # Setup middleware (CORS, exception handlers)
    setup_middleware(app)

    # ── Health Check ──
    @app.get("/health/live", tags=["Health"])
    async def health_live():
        return {"status": "alive"}

    @app.get("/health/ready", tags=["Health"])
    async def health_ready():
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return {"status": "ready", "database": "ok"}
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return JSONResponse(
                status_code=503,
                content={"status": "unhealthy", "database": "unavailable"}
            )

    @app.get("/api/health", tags=["Health"])
    async def health_check():
        return JSONResponse(
            content={
                "status": "healthy",
                "app": settings.app_name,
                "env": settings.app_env,
                "providers": {
                    "ai": settings.ai_provider,
                    "rag": settings.rag_retriever,
                    "stt": settings.stt_provider,
                    "tts": settings.tts_provider,
                },
            }
        )

    # ── Routers ──
    from app.auth.router import router as auth_router
    from app.users.router import router as users_router
    from app.tickets.router import router as tickets_router
    from app.conversations.router import router as conversations_router
    from app.rag.router import router as knowledge_router
    from app.handoff.router import router as handoffs_router
    from app.websockets.router import router as websockets_router
    from app.voice.router import router as voice_router
    from app.analytics.router import router as analytics_router
    from app.feedback.router import router as feedback_router
    from app.admin.router import router as admin_router
    
    app.include_router(auth_router, prefix="/api/auth", tags=["Auth"])
    app.include_router(users_router, prefix="/api/users", tags=["Users"])
    app.include_router(tickets_router, prefix="/api/tickets", tags=["Tickets"])
    app.include_router(conversations_router, prefix="/api/conversations", tags=["Conversations"])
    app.include_router(feedback_router) # prefix is already /api/conversations in the router
    app.include_router(knowledge_router, prefix="/api/knowledge", tags=["Knowledge"])
    app.include_router(handoffs_router, prefix="/api/handoffs", tags=["Handoffs"])
    app.include_router(websockets_router, prefix="/api", tags=["WebSockets"])
    app.include_router(voice_router, prefix="/api/audio", tags=["Voice"])
    app.include_router(analytics_router)
    app.include_router(admin_router)

    return app


# Application instance (used by uvicorn)
app = create_app()
