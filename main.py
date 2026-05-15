import os
import logging
from datetime import datetime
from typing import Optional, List

import httpx
import pandas as pd
from fastapi import FastAPI, Depends, HTTPException, Query
from sqlmodel import Session, select, create_engine, SQLModel
from dotenv import load_dotenv

from models import Budget, engine

# Configuration
load_dotenv()
BITRIX24_WEBHOOK_URL = os.getenv("BITRIX24_WEBHOOK_URL")

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vibe_finance")

app = FastAPI(title="VibeCode Finance Module (Bitrix24 Integration)")

# Create tables on startup
@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session

@app.post("/sync/trigger")
async def sync_bitrix_deals(
    entity_type: str = "deal",
    date_from: Optional[str] = None,
    session: Session = Depends(get_session)
):
    """
    Fetches deals from Bitrix24, calculates weighted income,
    and updates the budget for the current month.
    """
    if not BITRIX24_WEBHOOK_URL:
        raise HTTPException(status_code=500, detail="BITRIX24_WEBHOOK_URL not configured")

    logger.info(f"Starting sync for {entity_type}")

    params = {
        "order[CLOSED_DATE][>]": date_from if date_from else "2000-01-01T00:00:00",
        "select": ["OPPORTUNITY", "PROBABILITY", "CLOSED_DATE"]
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BITRIX24_WEBHOOK_URL}/crm.deal.list", params=params)
            response.raise_for_status()
            data = response.json().get("result", [])
        except Exception as e:
            logger.error(f"Bitrix24 API error: {str(e)}")
            raise HTTPException(status_code=502, detail="Failed to fetch data from Bitrix24")

    if not data:
        return {"status": "success", "processed_deals": 0, "total_weighted_income": 0.0}

    # Data Processing via Pandas
    df = pd.DataFrame(data)

    # Ensure numeric types
    df['OPPORTUNITY'] = pd.to_numeric(df['OPPORTUNITY'], errors='coerce').fillna(0)
    df['PROBABILITY'] = pd.to_numeric(df['PROBABILITY'], errors='coerce').fillna(0)

    # Logic: Sum (Amount * Probability / 100)
    df['weighted_income'] = df['OPPORTUNITY'] * (df['PROBABILITY'] / 100)
    total_weighted_income = float(df['weighted_income'].sum())
    deals_count = len(df)

    # Determine period (YYYY-MM)
    now = datetime.now()
    period = now.strftime("%Y-%m")

    # Update or Create Budget Record
    statement = select(Budget).where(Budget.period == period)
    existing_budget = session.exec(statement).first()

    if existing_budget:
        existing_budget.actual_income = total_weighted_income
        existing_budget.updated_at = datetime.utcnow()
        session.add(existing_budget)
    else:
        new_budget = Budget(
            period=period,
            planned_income=0.0,
            planned_expense=0.0,
            actual_income=total_weighted_income,
            actual_expense=0.0
        )
        session.add(new_budget)

    try:
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Database error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to save budget data")

    logger.info(f"Sync completed. Processed {deals_count} deals. Total: {total_weighted_income}")
    return {
        "status": "success",
        "processed_deals": deals_count,
        "total_weighted_income": total_weighted_income,
        "period": period
    }

@app.get("/planning/budgets")
def get_budgets(
    period: Optional[str] = Query(None, description="Filter by period in YYYY-MM format"),
    session: Session = Depends(get_session)
):
    """
    Returns all budget records, optionally filtered by period.
    """
    statement = select(Budget)
    if period:
        statement = statement.where(Budget.period == period)

    budgets = session.exec(statement).all()
    return budgets

@app.get("/health")
def health_check():
    return {"status": "healthy"}
