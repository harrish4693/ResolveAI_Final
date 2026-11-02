"""
ResolveAIV2 — Knowledge Article Model (for RAG)
"""

from sqlalchemy import Boolean, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.shared.models import TimestampMixin


class KnowledgeArticle(TimestampMixin, Base):
    __tablename__ = "knowledge_articles"

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(50), default="default", nullable=False, server_default="default", index=True)

    def __repr__(self) -> str:
        return f"<KnowledgeArticle(id={self.id}, title='{self.title[:50]}', category='{self.category}')>"
