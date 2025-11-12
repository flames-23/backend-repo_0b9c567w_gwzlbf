"""
Database Schemas for Library Management System

Each Pydantic model represents a collection in MongoDB.
Collection name is the lowercase class name.

Collections:
- Book
- Member
- Loan
- Reservation (optional future)
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class Book(BaseModel):
    """
    Books collection schema
    Collection name: "book"
    """
    title: str = Field(..., description="Book title")
    author: str = Field(..., description="Primary author")
    isbn: str = Field(..., description="ISBN identifier")
    category: Optional[str] = Field(None, description="Category/Genre")
    description: Optional[str] = Field(None, description="Short description")
    total_copies: int = Field(1, ge=0, description="Total copies owned")
    copies_available: int = Field(1, ge=0, description="Copies currently available")
    tags: List[str] = Field(default_factory=list, description="Tags for search")


class Member(BaseModel):
    """
    Members collection schema
    Collection name: "member"
    """
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    phone: Optional[str] = Field(None, description="Phone number")
    address: Optional[str] = Field(None, description="Address")
    is_active: bool = Field(True, description="Whether membership is active")


class Loan(BaseModel):
    """
    Loans collection schema
    Collection name: "loan"
    """
    member_id: str = Field(..., description="Member ObjectId as string")
    book_id: str = Field(..., description="Book ObjectId as string")
    borrowed_at: datetime = Field(default_factory=datetime.utcnow)
    due_at: datetime = Field(..., description="Due date/time (UTC)")
    returned_at: Optional[datetime] = Field(None, description="Return date/time (UTC)")
    status: str = Field("borrowed", description="borrowed | returned | overdue")
