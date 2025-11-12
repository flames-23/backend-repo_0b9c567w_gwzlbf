import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import Book as BookSchema, Member as MemberSchema, Loan as LoanSchema


# Helpers
class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if isinstance(v, ObjectId):
            return v
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)


def to_str_id(doc: Dict[str, Any]):
    if not doc:
        return doc
    doc["id"] = str(doc.get("_id"))
    doc.pop("_id", None)
    return doc


# Request Models
class CreateBook(BaseModel):
    title: str
    author: str
    isbn: str
    category: Optional[str] = None
    description: Optional[str] = None
    total_copies: int = Field(1, ge=0)
    copies_available: Optional[int] = None
    tags: List[str] = []


class UpdateBook(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    isbn: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    total_copies: Optional[int] = Field(None, ge=0)
    copies_available: Optional[int] = Field(None, ge=0)
    tags: Optional[List[str]] = None


class CreateMember(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    address: Optional[str] = None
    is_active: bool = True


class UpdateMember(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    is_active: Optional[bool] = None


class BorrowRequest(BaseModel):
    member_id: str
    book_id: str
    days: int = Field(14, ge=1, le=60)


app = FastAPI(title="Library Management API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": "Library Management API is running"}


# Books Endpoints
@app.get("/api/books")
def list_books(q: Optional[str] = None, category: Optional[str] = None):
    query: Dict[str, Any] = {}
    if q:
        # simple OR search on title/author/isbn/tags
        query["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"author": {"$regex": q, "$options": "i"}},
            {"isbn": {"$regex": q, "$options": "i"}},
            {"tags": {"$regex": q, "$options": "i"}},
        ]
    if category:
        query["category"] = category
    docs = db["book"].find(query).sort("title", 1)
    return [to_str_id(d) for d in docs]


@app.post("/api/books", status_code=201)
def create_book(payload: CreateBook):
    data = payload.model_dump()
    if data.get("copies_available") is None:
        data["copies_available"] = data["total_copies"]
    book = BookSchema(**data)
    new_id = create_document("book", book)
    doc = db["book"].find_one({"_id": ObjectId(new_id)})
    return to_str_id(doc)


@app.put("/api/books/{book_id}")
def update_book(book_id: str, payload: UpdateBook):
    if not ObjectId.is_valid(book_id):
        raise HTTPException(400, "Invalid book id")
    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if not update:
        raise HTTPException(400, "No fields to update")
    update["updated_at"] = datetime.now(timezone.utc)
    result = db["book"].update_one({"_id": ObjectId(book_id)}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(404, "Book not found")
    doc = db["book"].find_one({"_id": ObjectId(book_id)})
    return to_str_id(doc)


@app.delete("/api/books/{book_id}", status_code=204)
def delete_book(book_id: str):
    if not ObjectId.is_valid(book_id):
        raise HTTPException(400, "Invalid book id")
    result = db["book"].delete_one({"_id": ObjectId(book_id)})
    if result.deleted_count == 0:
        raise HTTPException(404, "Book not found")
    return {"ok": True}


# Members Endpoints
@app.get("/api/members")
def list_members(q: Optional[str] = None):
    query: Dict[str, Any] = {}
    if q:
        query["$or"] = [
            {"name": {"$regex": q, "$options": "i"}},
            {"email": {"$regex": q, "$options": "i"}},
            {"phone": {"$regex": q, "$options": "i"}},
        ]
    docs = db["member"].find(query).sort("name", 1)
    return [to_str_id(d) for d in docs]


@app.post("/api/members", status_code=201)
def create_member(payload: CreateMember):
    member = MemberSchema(**payload.model_dump())
    new_id = create_document("member", member)
    doc = db["member"].find_one({"_id": ObjectId(new_id)})
    return to_str_id(doc)


@app.put("/api/members/{member_id}")
def update_member(member_id: str, payload: UpdateMember):
    if not ObjectId.is_valid(member_id):
        raise HTTPException(400, "Invalid member id")
    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if not update:
        raise HTTPException(400, "No fields to update")
    update["updated_at"] = datetime.now(timezone.utc)
    result = db["member"].update_one({"_id": ObjectId(member_id)}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(404, "Member not found")
    doc = db["member"].find_one({"_id": ObjectId(member_id)})
    return to_str_id(doc)


@app.delete("/api/members/{member_id}", status_code=204)
def delete_member(member_id: str):
    if not ObjectId.is_valid(member_id):
        raise HTTPException(400, "Invalid member id")
    # ensure no active loans
    active_loans = db["loan"].count_documents({"member_id": member_id, "status": {"$in": ["borrowed", "overdue"]}})
    if active_loans > 0:
        raise HTTPException(400, "Member has active loans")
    result = db["member"].delete_one({"_id": ObjectId(member_id)})
    if result.deleted_count == 0:
        raise HTTPException(404, "Member not found")
    return {"ok": True}


# Loans Endpoints
@app.get("/api/loans")
def list_loans(status: Optional[str] = None):
    query: Dict[str, Any] = {}
    if status:
        query["status"] = status
    # update overdue statuses
    now = datetime.utcnow()
    db["loan"].update_many({"status": "borrowed", "due_at": {"$lt": now}}, {"$set": {"status": "overdue"}})
    docs = db["loan"].find(query).sort("borrowed_at", -1)
    # join-like enrichment for client
    members_map = {str(m["_id"]): m for m in db["member"].find({})}
    books_map = {str(b["_id"]): b for b in db["book"].find({})}
    out: List[Dict[str, Any]] = []
    for d in docs:
        d = to_str_id(d)
        m = members_map.get(d["member_id"]) or {}
        b = books_map.get(d["book_id"]) or {}
        d["member_name"] = m.get("name")
        d["book_title"] = b.get("title")
        out.append(d)
    return out


@app.post("/api/loans/borrow", status_code=201)
def borrow_book(payload: BorrowRequest):
    # validations
    if not ObjectId.is_valid(payload.member_id) or not ObjectId.is_valid(payload.book_id):
        raise HTTPException(400, "Invalid member or book id")
    member = db["member"].find_one({"_id": ObjectId(payload.member_id)})
    if not member or not member.get("is_active", True):
        raise HTTPException(400, "Member not found or inactive")
    book = db["book"].find_one({"_id": ObjectId(payload.book_id)})
    if not book:
        raise HTTPException(404, "Book not found")
    if book.get("copies_available", 0) <= 0:
        raise HTTPException(400, "No copies available")

    # Create loan and decrement available copies atomically-ish
    due_at = datetime.utcnow() + timedelta(days=payload.days)
    loan = LoanSchema(
        member_id=payload.member_id,
        book_id=payload.book_id,
        borrowed_at=datetime.utcnow(),
        due_at=due_at,
        status="borrowed",
    )
    loan_id = create_document("loan", loan)
    db["book"].update_one({"_id": ObjectId(payload.book_id)}, {"$inc": {"copies_available": -1}, "$set": {"updated_at": datetime.now(timezone.utc)}})
    doc = db["loan"].find_one({"_id": ObjectId(loan_id)})
    return to_str_id(doc)


@app.post("/api/loans/{loan_id}/return")
def return_book(loan_id: str):
    if not ObjectId.is_valid(loan_id):
        raise HTTPException(400, "Invalid loan id")
    loan = db["loan"].find_one({"_id": ObjectId(loan_id)})
    if not loan:
        raise HTTPException(404, "Loan not found")
    if loan.get("status") == "returned":
        return to_str_id(loan)
    # mark as returned
    now = datetime.utcnow()
    db["loan"].update_one(
        {"_id": ObjectId(loan_id)},
        {"$set": {"status": "returned", "returned_at": now, "updated_at": datetime.now(timezone.utc)}},
    )
    # increment book availability
    db["book"].update_one({"_id": ObjectId(loan["book_id"])}, {"$inc": {"copies_available": 1}, "$set": {"updated_at": datetime.now(timezone.utc)}})
    doc = db["loan"].find_one({"_id": ObjectId(loan_id)})
    return to_str_id(doc)


# Stats endpoint
@app.get("/api/stats")
def stats():
    total_books = db["book"].count_documents({})
    total_copies = list(db["book"].aggregate([
        {"$group": {"_id": None, "total": {"$sum": "$total_copies"}, "available": {"$sum": "$copies_available"}}}
    ]))
    total_members = db["member"].count_documents({})
    active_loans = db["loan"].count_documents({"status": {"$in": ["borrowed", "overdue"]}})
    overdue = db["loan"].count_documents({"status": "overdue"})

    total = total_copies[0]["total"] if total_copies else 0
    available = total_copies[0]["available"] if total_copies else 0

    return {
        "books": total_books,
        "copies": total,
        "available": available,
        "members": total_members,
        "active_loans": active_loans,
        "overdue": overdue,
    }


# Schema info (useful for tooling)
@app.get("/schema")
def get_schema_info():
    return {
        "collections": [
            {
                "name": "book",
                "fields": list(CreateBook.model_fields.keys())
            },
            {
                "name": "member",
                "fields": list(CreateMember.model_fields.keys())
            },
            {
                "name": "loan",
                "fields": ["member_id", "book_id", "borrowed_at", "due_at", "returned_at", "status"]
            },
        ]
    }


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    import os as _os
    response["database_url"] = "✅ Set" if _os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if _os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
