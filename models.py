from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field, create_engine, Session
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/dbname")

engine = create_engine(DATABASE_URL)

class Budget(SQLModel, table=True):
    __tablename__ = "budgets"

    id: Optional[int] = Field(default=None, primary_key=True)
    period: str = Field(index=True, description="Format: YYYY-MM")
    planned_income: float = Field(default=0.0)
    planned_expense: float = Field(default=0.0)
    actual_income: float = Field(default=0.0)
    actual_expense: float = Field(default=0.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
