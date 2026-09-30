from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Book, BorrowRecord
from app.schemas import BookCreate, BookResponse, BookUpdate, MessageResponse

router = APIRouter(prefix="/books", tags=["Books"])


def get_book_or_404(db: Session, book_id: int) -> Book:
    book = db.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Book with ID {book_id} not found")
    return book


def ensure_isbn_available(db: Session, isbn: str, exclude_book_id: Optional[int] = None) -> None:
    query = select(Book).where(Book.isbn == isbn)
    if exclude_book_id is not None:
        query = query.where(Book.book_id != exclude_book_id)
    if db.scalars(query).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"A book with ISBN '{isbn}' already exists")


@router.post("", response_model=BookResponse, status_code=status.HTTP_201_CREATED)
def create_book(payload: BookCreate, db: Session = Depends(get_db)):
    ensure_isbn_available(db, payload.isbn)
    book = Book(**payload.model_dump())
    db.add(book)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"A book with ISBN '{payload.isbn}' already exists")
    db.refresh(book)
    return book


@router.get("", response_model=List[BookResponse])
def list_books(
    category: Optional[str] = Query(default=None, description="Filter by category, for example Programming"),
    author: Optional[str] = Query(default=None, description="Filter by author name, for example Robert"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = select(Book)
    if category is not None and category.strip():
        query = query.where(Book.category.ilike(f"%{category.strip()}%"))
    if author is not None and author.strip():
        query = query.where(Book.author.ilike(f"%{author.strip()}%"))
    query = query.order_by(Book.book_id).offset(skip).limit(limit)
    return list(db.scalars(query).all())


@router.get("/{book_id}", response_model=BookResponse)
def get_book(book_id: int = Path(ge=1), db: Session = Depends(get_db)):
    return get_book_or_404(db, book_id)


@router.put("/{book_id}", response_model=BookResponse)
def update_book(payload: BookUpdate, book_id: int = Path(ge=1), db: Session = Depends(get_db)):
    book = get_book_or_404(db, book_id)
    ensure_isbn_available(db, payload.isbn, exclude_book_id=book_id)
    for field, value in payload.model_dump().items():
        setattr(book, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"A book with ISBN '{payload.isbn}' already exists")
    db.refresh(book)
    return book


@router.delete("/{book_id}", response_model=MessageResponse)
def delete_book(book_id: int = Path(ge=1), db: Session = Depends(get_db)):
    book = get_book_or_404(db, book_id)
    active = db.scalars(
        select(BorrowRecord).where(BorrowRecord.book_id == book_id, BorrowRecord.returned_at.is_(None))
    ).first()
    if active is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Book cannot be deleted because it is currently borrowed by a member",
        )
    for record in db.scalars(select(BorrowRecord).where(BorrowRecord.book_id == book_id)).all():
        db.delete(record)
    db.delete(book)
    db.commit()
    return MessageResponse(message=f"Book with ID {book_id} deleted successfully")
