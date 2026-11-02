"""
ResolveAIV2 — Expert Models
"""

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.shared.models import TimestampMixin


class Expert(TimestampMixin, Base):
    __tablename__ = "experts"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, unique=True
    )

    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_concurrent: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    current_load: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    user = relationship("User")
    specializations = relationship("ExpertSpecialization", back_populates="expert", lazy="selectin")
    handoffs = relationship("Handoff", back_populates="assigned_expert")
    assignments = relationship("ExpertAssignment", back_populates="expert")

    def __repr__(self) -> str:
        return f"<Expert(id={self.id}, user_id={self.user_id}, available={self.is_available})>"


class ExpertSpecialization(TimestampMixin, Base):
    __tablename__ = "expert_specializations"

    expert_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("experts.id"), nullable=False
    )
    category: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # payment / security / delivery / technical / general
    proficiency: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3
    )  # 1-5

    # Relationships
    expert = relationship("Expert", back_populates="specializations")

    def __repr__(self) -> str:
        return f"<ExpertSpecialization(expert={self.expert_id}, category='{self.category}', level={self.proficiency})>"
