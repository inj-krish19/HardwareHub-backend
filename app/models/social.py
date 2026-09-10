import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Comparison(Base):
    __tablename__ = "comparison"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(160), nullable=False)

    items: Mapped[list["ComparisonItem"]] = relationship(back_populates="comparison")


class ComparisonItem(Base):
    __tablename__ = "comparison_item"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    comparison_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("comparison.id"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product.id"), nullable=False)

    comparison: Mapped["Comparison"] = relationship(back_populates="items")


class User(Base):
    __tablename__ = "app_user"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role: Mapped[str] = mapped_column(String(40), default="visitor")
    auth_info: Mapped[str | None] = mapped_column(String(255), nullable=True)