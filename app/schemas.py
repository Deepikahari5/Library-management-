import re
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

MembershipType = Literal["Standard", "Premium", "Student"]

PHONE_PATTERN = re.compile(r"^\+?[0-9][0-9\- ]{6,18}$")


class BookBase(BaseModel):
    book_name: str = Field(min_length=1, max_length=200, examples=["Clean Code"])
    author: str = Field(min_length=1, max_length=150, examples=["Robert C. Martin"])
    category: str = Field(min_length=1, max_length=100, examples=["Programming"])
    isbn: str = Field(min_length=1, max_length=20, examples=["9780132350884"])
    price: float = Field(gt=0, examples=[499.0])
    available_quantity: int = Field(ge=0, examples=[5])

    @field_validator("book_name", "author", "category", "isbn")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class BookCreate(BookBase):
    pass


class BookUpdate(BookBase):
    pass


class BookResponse(BookBase):
    model_config = ConfigDict(from_attributes=True)

    book_id: int


class MemberBase(BaseModel):
    member_name: str = Field(min_length=1, max_length=150, examples=["Deepika"])
    email: EmailStr = Field(examples=["deepika@example.com"])
    phone_number: Optional[str] = Field(default=None, examples=["9876543210"])
    membership_type: MembershipType = Field(default="Standard")

    @field_validator("member_name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("phone_number")
    @classmethod
    def check_phone(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if not PHONE_PATTERN.match(value):
            raise ValueError("must be a valid phone number with 7 to 15 digits")
        return value


class MemberCreate(MemberBase):
    pass


class MemberUpdate(MemberBase):
    pass


class MemberResponse(MemberBase):
    model_config = ConfigDict(from_attributes=True)

    member_id: int


class MessageResponse(BaseModel):
    message: str


class BorrowResponse(BaseModel):
    message: str
    member_id: int
    book_id: int
    borrowed_at: datetime
    available_quantity: int


class ReturnResponse(BaseModel):
    message: str
    member_id: int
    book_id: int
    borrowed_at: datetime
    returned_at: datetime
    available_quantity: int
