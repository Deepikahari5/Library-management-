from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Book(Base):
    __tablename__ = "books"

    book_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_name: Mapped[str] = mapped_column(String(200), nullable=False)
    author: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    isbn: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    available_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Member(Base):
    __tablename__ = "members"

    member_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    member_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    phone_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    membership_type: Mapped[str] = mapped_column(String(20), nullable=False, default="Standard")


class BorrowRecord(Base):
    __tablename__ = "borrow_records"

    record_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.member_id"), nullable=False, index=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.book_id"), nullable=False, index=True)
    borrowed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    returned_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
