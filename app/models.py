from datetime import datetime
from sqlalchemy import String, Integer, Float, DateTime, Text, BigInteger
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class ShopOrder(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_ref: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    game_slug: Mapped[str] = mapped_column(String(120))
    game_name: Mapped[str] = mapped_column(String(180))
    package_id: Mapped[int] = mapped_column(Integer)
    package_name: Mapped[str] = mapped_column(String(180))
    player_id: Mapped[str] = mapped_column(String(120))
    server_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    supplier_price: Mapped[float] = mapped_column(Float)
    sell_price: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(40), default="awaiting_payment", index=True)
    supplier_order_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    receipt_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
