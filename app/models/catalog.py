import uuid

from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Category(Base):
    __tablename__ = "category"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    products: Mapped[list["Product"]] = relationship(back_populates="category")


class Product(Base):
    __tablename__ = "product"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("category.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    model_number: Mapped[str] = mapped_column(String(80), nullable=False)
    specs: Mapped[dict] = mapped_column(JSONB, default=dict)
    use_case_tags: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Media is linked, not stored: paste an image URL and a YouTube URL.
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    video_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    category: Mapped["Category"] = relationship(back_populates="products")
    blog_posts: Mapped[list["BlogPost"]] = relationship(back_populates="product")
    links: Mapped[list["ProductLink"]] = relationship(
        back_populates="product", order_by="ProductLink.position", cascade="all, delete-orphan"
    )


class BlogPost(Base):
    __tablename__ = "blog_post"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    do_you_know: Mapped[str | None] = mapped_column(Text, nullable=True)
    # LEGACY: comma-separated URLs. Superseded by ProductLink; the catalog API
    # only falls back to this when a product has no ProductLink rows.
    buy_links: Mapped[str | None] = mapped_column(Text, nullable=True)

    product: Mapped["Product"] = relationship(back_populates="blog_posts")


class ProductLink(Base):
    """A store link for a product. Position 0 is the primary link (the
    "Check price" button); positions 0-2 are all listed under "Where to buy".
    The unique + check constraints cap a product at three links."""

    __tablename__ = "product_link"
    __table_args__ = (
        UniqueConstraint("product_id", "position", name="uq_product_link_position"),
        CheckConstraint("position BETWEEN 0 AND 2", name="ck_product_link_position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("product.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    store: Mapped[str] = mapped_column(String(60), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)

    product: Mapped["Product"] = relationship(back_populates="links")