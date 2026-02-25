from datetime import datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    Enum,
    Float,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_deactivated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    chat_type: Mapped[str] = mapped_column(
        Enum("private", "group", "supergroup", name="chat_type_enum"),
        nullable=False,
    )
    chat_name: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class WishlistEntry(Base):
    __tablename__ = "wishlist_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    google_place_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    address: Mapped[str] = mapped_column(String, nullable=False)
    area: Mapped[str | None] = mapped_column(String, nullable=True)
    cuisine_type: Mapped[str | None] = mapped_column(String, nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    added_by: Mapped[str] = mapped_column(String, nullable=False)  # FK: users.telegram_id
    status: Mapped[str] = mapped_column(
        Enum("wishlist", "visited", "deleted", name="wishlist_status_enum"),
        default="wishlist",
        nullable=False,
    )
    any_branch: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_added: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Visit(Base):
    __tablename__ = "visits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    google_place_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    logged_by: Mapped[str] = mapped_column(String, nullable=False)  # FK: users.telegram_id
    place_name: Mapped[str | None] = mapped_column(String, nullable=True)   # denormalised for resilient display
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1–5
    review: Mapped[str | None] = mapped_column(Text, nullable=True)
    occasion: Mapped[str | None] = mapped_column(String, nullable=True)  # Casual/Special/Work/Spontaneous
    photos: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)  # Telegram file_ids
    visited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SponsoredRestaurant(Base):
    __tablename__ = "sponsored_restaurants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    google_place_id: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    cuisine_tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    area: Mapped[str | None] = mapped_column(String, nullable=True)
    deal_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Error(Base):
    __tablename__ = "errors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    telegram_id: Mapped[str | None] = mapped_column(String, nullable=True)
    chat_id: Mapped[str | None] = mapped_column(String, nullable=True)
    command: Mapped[str | None] = mapped_column(String, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
