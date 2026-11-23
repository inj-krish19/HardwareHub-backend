import uuid

from sqlalchemy import ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CompatibilityRule(Base):
    __tablename__ = "compatibility_rule"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product.id"), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(80), nullable=False)
    condition: Mapped[dict] = mapped_column(JSONB, default=dict)
    result: Mapped[str] = mapped_column(Text, nullable=False)


class Symptom(Base):
    __tablename__ = "symptom"
    __table_args__ = (
        # Guide titles are unique ignoring case and surrounding spaces: the chat
        # opens a guide by the title the person tapped.
        Index("uq_symptom_title_ci", text("lower(btrim(title))"), unique=True),
        # Public URL of the guide page. NULLs are allowed (and not compared) so
        # the column can be added first and filled in afterwards.
        Index("uq_symptom_slug", "slug", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("product.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    # Stable, URL-safe name for /guides/<slug>. Generated once from the title
    # (see app/core/slugs.py) and never changed when the title is edited.
    slug: Mapped[str | None] = mapped_column(String(160), nullable=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    # Comma-separated synonyms/phrasings so a query doesn't have to closely
    # match the title wording to be matched (e.g. "ram isn't showing up"
    # should still hit "RAM not detected / no display").
    keywords: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Which bot owns this tree: diagnostic | compatibility | budget | upgrade | maintenance.
    # All bots share the same tree walker; only the content and this tag differ.
    bot_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="diagnostic", server_default="diagnostic"
    )

    diagnosis_rules: Mapped[list["DiagnosisRule"]] = relationship(back_populates="symptom")


class DiagnosisRule(Base):
    __tablename__ = "diagnosis_rule"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symptom_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("symptom.id"), nullable=False)
    question_tree: Mapped[dict] = mapped_column(JSONB, nullable=False)
    conclusion: Mapped[str | None] = mapped_column(Text, nullable=True)

    symptom: Mapped["Symptom"] = relationship(back_populates="diagnosis_rules")


class UseBudgetProfile(Base):
    __tablename__ = "use_budget_profile"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    budget_min: Mapped[int] = mapped_column(Integer, nullable=False)
    budget_max: Mapped[int] = mapped_column(Integer, nullable=False)
    task_type: Mapped[str] = mapped_column(String(120), nullable=False)

    recommendation_rules: Mapped[list["RecommendationRule"]] = relationship(back_populates="profile")


class RecommendationRule(Base):
    __tablename__ = "recommendation_rule"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("use_budget_profile.id"), nullable=False)
    component_set: Mapped[dict] = mapped_column(JSONB, nullable=False)

    profile: Mapped["UseBudgetProfile"] = relationship(back_populates="recommendation_rules")