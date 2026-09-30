from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Book, BorrowRecord, Member, utc_now
from app.schemas import (
    BorrowResponse,
    MemberCreate,
    MemberResponse,
    MemberUpdate,
    MessageResponse,
    ReturnResponse,
)

router = APIRouter(prefix="/members", tags=["Members"])


def get_member_or_404(db: Session, member_id: int) -> Member:
    member = db.get(Member, member_id)
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Member with ID {member_id} not found")
    return member


def get_book_or_404(db: Session, book_id: int) -> Book:
    book = db.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Book with ID {book_id} not found")
    return book


def ensure_email_available(db: Session, email: str, exclude_member_id: Optional[int] = None) -> None:
    query = select(Member).where(Member.email == email)
    if exclude_member_id is not None:
        query = query.where(Member.member_id != exclude_member_id)
    if db.scalars(query).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"A member with email '{email}' already exists")


@router.post("", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
def create_member(payload: MemberCreate, db: Session = Depends(get_db)):
    ensure_email_available(db, payload.email)
    member = Member(**payload.model_dump())
    db.add(member)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"A member with email '{payload.email}' already exists")
    db.refresh(member)
    return member


@router.get("", response_model=List[MemberResponse])
def list_members(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = select(Member).order_by(Member.member_id).offset(skip).limit(limit)
    return list(db.scalars(query).all())


@router.get("/{member_id}", response_model=MemberResponse)
def get_member(member_id: int = Path(ge=1), db: Session = Depends(get_db)):
    return get_member_or_404(db, member_id)


@router.put("/{member_id}", response_model=MemberResponse)
def update_member(payload: MemberUpdate, member_id: int = Path(ge=1), db: Session = Depends(get_db)):
    member = get_member_or_404(db, member_id)
    ensure_email_available(db, payload.email, exclude_member_id=member_id)
    for field, value in payload.model_dump().items():
        setattr(member, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"A member with email '{payload.email}' already exists")
    db.refresh(member)
    return member


@router.delete("/{member_id}", response_model=MessageResponse)
def delete_member(member_id: int = Path(ge=1), db: Session = Depends(get_db)):
    member = get_member_or_404(db, member_id)
    active = db.scalars(
        select(BorrowRecord).where(BorrowRecord.member_id == member_id, BorrowRecord.returned_at.is_(None))
    ).first()
    if active is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Member cannot be deleted because they have books that are not returned",
        )
    for record in db.scalars(select(BorrowRecord).where(BorrowRecord.member_id == member_id)).all():
        db.delete(record)
    db.delete(member)
    db.commit()
    return MessageResponse(message=f"Member with ID {member_id} deleted successfully")


@router.post("/{member_id}/books/{book_id}/borrow", response_model=BorrowResponse, tags=["Borrowing"])
def borrow_book(member_id: int = Path(ge=1), book_id: int = Path(ge=1), db: Session = Depends(get_db)):
    member = get_member_or_404(db, member_id)
    book = get_book_or_404(db, book_id)

    if book.available_quantity <= 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Book '{book.book_name}' is currently out of stock",
        )

    already_borrowed = db.scalars(
        select(BorrowRecord).where(
            BorrowRecord.member_id == member.member_id,
            BorrowRecord.book_id == book.book_id,
            BorrowRecord.returned_at.is_(None),
        )
    ).first()
    if already_borrowed is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Member has already borrowed this book and has not returned it yet",
        )

    record = BorrowRecord(member_id=member.member_id, book_id=book.book_id)
    book.available_quantity -= 1
    db.add(record)
    db.commit()
    db.refresh(record)
    db.refresh(book)

    return BorrowResponse(
        message=f"Book '{book.book_name}' borrowed successfully by {member.member_name}",
        member_id=member.member_id,
        book_id=book.book_id,
        borrowed_at=record.borrowed_at,
        available_quantity=book.available_quantity,
    )


@router.post("/{member_id}/books/{book_id}/return", response_model=ReturnResponse, tags=["Borrowing"])
def return_book(member_id: int = Path(ge=1), book_id: int = Path(ge=1), db: Session = Depends(get_db)):
    member = get_member_or_404(db, member_id)
    book = get_book_or_404(db, book_id)

    record = db.scalars(
        select(BorrowRecord)
        .where(
            BorrowRecord.member_id == member.member_id,
            BorrowRecord.book_id == book.book_id,
            BorrowRecord.returned_at.is_(None),
        )
        .order_by(BorrowRecord.borrowed_at)
    ).first()
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This member has not borrowed this book or it was already returned",
        )

    record.returned_at = utc_now()
    book.available_quantity += 1
    db.commit()
    db.refresh(record)
    db.refresh(book)

    return ReturnResponse(
        message=f"Book '{book.book_name}' returned successfully by {member.member_name}",
        member_id=member.member_id,
        book_id=book.book_id,
        borrowed_at=record.borrowed_at,
        returned_at=record.returned_at,
        available_quantity=book.available_quantity,
    )
