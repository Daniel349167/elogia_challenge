from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import InsightAnomaliesOut, InsightSummaryOut, InsightTrendOut, InsightVendorsOut
from app.services.insights_service import build_anomalies, build_summary, build_top_vendors, build_trend

router = APIRouter(prefix="/api/v1/insights", tags=["insights"])


@router.get("/summary", response_model=InsightSummaryOut)
def summary(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
) -> InsightSummaryOut:
    return InsightSummaryOut.model_validate(build_summary(db, from_date=from_date, to_date=to_date))


@router.get("/vendors", response_model=InsightVendorsOut)
def vendors(
    limit: int = Query(default=5, ge=1, le=20),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
) -> InsightVendorsOut:
    return InsightVendorsOut.model_validate(
        build_top_vendors(db, limit=limit, from_date=from_date, to_date=to_date)
    )


@router.get("/trend", response_model=InsightTrendOut)
def trend(
    group_by: str = Query(default="month", pattern="^(day|month)$"),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
) -> InsightTrendOut:
    return InsightTrendOut.model_validate(
        build_trend(db, group_by=group_by, from_date=from_date, to_date=to_date)
    )


@router.get("/anomalies", response_model=InsightAnomaliesOut)
def anomalies(
    factor: float = Query(default=1.8, ge=1.0, le=4.0),
    limit: int = Query(default=10, ge=1, le=50),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
) -> InsightAnomaliesOut:
    return InsightAnomaliesOut.model_validate(
        build_anomalies(db, factor=factor, limit=limit, from_date=from_date, to_date=to_date)
    )
