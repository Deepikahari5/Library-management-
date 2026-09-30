import os
import tempfile

_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_db_file.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_db_file.name}"

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app


@pytest.fixture(autouse=True)
def fresh_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def book_payload(**overrides):
    data = {
        "book_name": "Clean Code",
        "author": "Robert C. Martin",
        "category": "Programming",
        "isbn": "9780132350884",
        "price": 499.0,
        "available_quantity": 2,
    }
    data.update(overrides)
    return data


def member_payload(**overrides):
    data = {
        "member_name": "Deepika",
        "email": "deepika@example.com",
        "phone_number": "9876543210",
        "membership_type": "Premium",
    }
    data.update(overrides)
    return data


def test_create_and_get_book(client):
    response = client.post("/books", json=book_payload())
    assert response.status_code == 201
    body = response.json()
    assert body["book_id"] == 1
    assert client.get("/books/1").json()["isbn"] == "9780132350884"
    assert len(client.get("/books").json()) == 1


def test_update_and_delete_book(client):
    client.post("/books", json=book_payload())
    response = client.put("/books/1", json=book_payload(price=550.0, available_quantity=7))
    assert response.status_code == 200
    assert response.json()["price"] == 550.0
    assert response.json()["available_quantity"] == 7
    assert client.delete("/books/1").status_code == 200
    assert client.get("/books/1").status_code == 404


def test_book_not_found(client):
    assert client.get("/books/99").status_code == 404
    assert client.put("/books/99", json=book_payload()).status_code == 404
    assert client.delete("/books/99").status_code == 404


def test_duplicate_isbn(client):
    client.post("/books", json=book_payload())
    response = client.post("/books", json=book_payload(book_name="Another"))
    assert response.status_code == 409
    client.post("/books", json=book_payload(isbn="1111111111"))
    response = client.put("/books/2", json=book_payload(isbn="9780132350884"))
    assert response.status_code == 409


def test_invalid_book_input(client):
    assert client.post("/books", json=book_payload(price=0)).status_code == 422
    assert client.post("/books", json=book_payload(price=-10)).status_code == 422
    assert client.post("/books", json=book_payload(available_quantity=-1)).status_code == 422
    assert client.post("/books", json=book_payload(book_name="   ")).status_code == 422
    assert client.post("/books", json=book_payload(price="abc")).status_code == 422
    payload = book_payload()
    del payload["isbn"]
    assert client.post("/books", json=payload).status_code == 422
    assert client.get("/books/0").status_code == 422
    assert client.get("/books/abc").status_code == 422


def test_zero_quantity_is_allowed(client):
    assert client.post("/books", json=book_payload(available_quantity=0)).status_code == 201


def test_search_books(client):
    client.post("/books", json=book_payload())
    client.post(
        "/books",
        json=book_payload(
            book_name="Atomic Habits", author="James Clear", category="Self Help", isbn="9780735211292"
        ),
    )
    by_category = client.get("/books", params={"category": "Programming"}).json()
    assert [b["book_name"] for b in by_category] == ["Clean Code"]
    by_author = client.get("/books", params={"author": "Robert"}).json()
    assert [b["book_name"] for b in by_author] == ["Clean Code"]
    both = client.get("/books", params={"category": "Self Help", "author": "Clear"}).json()
    assert len(both) == 1
    assert client.get("/books", params={"category": "Cooking"}).json() == []


def test_member_crud(client):
    response = client.post("/members", json=member_payload(email="Deepika@Example.com"))
    assert response.status_code == 201
    assert response.json()["email"] == "deepika@example.com"
    assert client.get("/members/1").status_code == 200
    assert len(client.get("/members").json()) == 1
    response = client.put("/members/1", json=member_payload(member_name="Deepika S"))
    assert response.status_code == 200
    assert response.json()["member_name"] == "Deepika S"
    assert client.delete("/members/1").status_code == 200
    assert client.get("/members/1").status_code == 404


def test_member_validation_and_duplicates(client):
    client.post("/members", json=member_payload())
    assert client.post("/members", json=member_payload()).status_code == 409
    client.post("/members", json=member_payload(email="second@example.com"))
    assert client.put("/members/2", json=member_payload()).status_code == 409
    assert client.post("/members", json=member_payload(email="not-an-email")).status_code == 422
    assert client.post("/members", json=member_payload(member_name="")).status_code == 422
    assert client.post("/members", json=member_payload(phone_number="abc")).status_code == 422
    assert client.post("/members", json=member_payload(membership_type="Gold")).status_code == 422
    assert client.get("/members/99").status_code == 404


def test_borrow_and_return_updates_quantity(client):
    client.post("/books", json=book_payload(available_quantity=2))
    client.post("/members", json=member_payload())
    response = client.post("/members/1/books/1/borrow")
    assert response.status_code == 200
    assert response.json()["available_quantity"] == 1
    assert client.get("/books/1").json()["available_quantity"] == 1
    response = client.post("/members/1/books/1/return")
    assert response.status_code == 200
    assert response.json()["available_quantity"] == 2
    assert client.get("/books/1").json()["available_quantity"] == 2


def test_borrow_errors(client):
    client.post("/books", json=book_payload(available_quantity=0))
    client.post("/books", json=book_payload(isbn="2222222222", available_quantity=1))
    client.post("/members", json=member_payload())
    assert client.post("/members/1/books/99/borrow").status_code == 404
    assert client.post("/members/99/books/1/borrow").status_code == 404
    assert client.post("/members/1/books/1/borrow").status_code == 409
    assert client.post("/members/1/books/2/borrow").status_code == 200
    assert client.post("/members/1/books/2/borrow").status_code == 409


def test_return_errors(client):
    client.post("/books", json=book_payload())
    client.post("/members", json=member_payload())
    assert client.post("/members/1/books/1/return").status_code == 400
    assert client.post("/members/99/books/1/return").status_code == 404
    assert client.post("/members/1/books/99/return").status_code == 404
    client.post("/members/1/books/1/borrow")
    assert client.post("/members/1/books/1/return").status_code == 200
    assert client.post("/members/1/books/1/return").status_code == 400


def test_cannot_delete_borrowed_book_or_member(client):
    client.post("/books", json=book_payload())
    client.post("/members", json=member_payload())
    client.post("/members/1/books/1/borrow")
    assert client.delete("/books/1").status_code == 409
    assert client.delete("/members/1").status_code == 409
    client.post("/members/1/books/1/return")
    assert client.delete("/members/1").status_code == 200
    assert client.delete("/books/1").status_code == 200
