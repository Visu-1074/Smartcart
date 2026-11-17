from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base

class Listing(Base):
    __tablename__ = "listings"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    platform: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String)
    price: Mapped[float] = mapped_column(Float)
    original_price: Mapped[float] = mapped_column(Float)
    rating: Mapped[float] = mapped_column(Float)
    availability: Mapped[str] = mapped_column(String)
    image_url: Mapped[str] = mapped_column(String)
    url: Mapped[str] = mapped_column(String)

class CartItem(Base):
    __tablename__ = "cart_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    listing_id: Mapped[str] = mapped_column(String, index=True)
    platform: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    price: Mapped[float] = mapped_column(Float)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    image_url: Mapped[str] = mapped_column(String)
    url: Mapped[str] = mapped_column(String)
    category: Mapped[str] = mapped_column(String, default="general")
    variant: Mapped[str] = mapped_column(String, default="")
    is_rx: Mapped[bool] = mapped_column(Boolean, default=False)

class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    confirmation_ref: Mapped[str] = mapped_column(String, default="Pending user confirmation")

class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(Integer, index=True)
    platform: Mapped[str] = mapped_column(String)
    item: Mapped[str] = mapped_column(String)
    price_paid: Mapped[float] = mapped_column(Float)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
