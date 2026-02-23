from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, cast, func, String
from sqlalchemy.orm import Session

from app.models import Receipt


def _to_float(value: Decimal | float | int | None) -> float:
    if value is None:
        return 0.0
    return float(value)


def _base_filters(from_date: date | None = None, to_date: date | None = None) -> list[Any]:
    filters: list[Any] = [Receipt.total.isnot(None)]
    if from_date:
        filters.append(Receipt.issue_date >= from_date)
    if to_date:
        filters.append(Receipt.issue_date <= to_date)
    return filters


def build_summary(db: Session, from_date: date | None = None, to_date: date | None = None) -> dict[str, Any]:
    filters = _base_filters(from_date, to_date)

    total_receipts, total_spent, average_ticket = (
        db.query(
            func.count(Receipt.id),
            func.coalesce(func.sum(Receipt.total), 0),
            func.coalesce(func.avg(Receipt.total), 0),
        )
        .filter(and_(*filters))
        .first()
    )

    top_vendor_row = (
        db.query(Receipt.vendor_name, func.coalesce(func.sum(Receipt.total), 0).label("vendor_total"))
        .filter(and_(*(filters + [Receipt.vendor_name.isnot(None)])))
        .group_by(Receipt.vendor_name)
        .order_by(func.sum(Receipt.total).desc())
        .first()
    )

    top_vendor = top_vendor_row[0] if top_vendor_row else None
    top_vendor_total = _to_float(top_vendor_row[1]) if top_vendor_row else None

    return {
        "total_receipts": int(total_receipts or 0),
        "total_spent": _to_float(total_spent),
        "average_ticket": _to_float(average_ticket),
        "top_vendor": top_vendor,
        "top_vendor_total": top_vendor_total,
    }


def build_top_vendors(
    db: Session,
    *,
    limit: int = 5,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict[str, Any]:
    filters = _base_filters(from_date, to_date)
    rows = (
        db.query(
            Receipt.vendor_name,
            func.coalesce(func.sum(Receipt.total), 0).label("total_spent"),
            func.count(Receipt.id).label("receipts_count"),
        )
        .filter(and_(*(filters + [Receipt.vendor_name.isnot(None)])))
        .group_by(Receipt.vendor_name)
        .order_by(func.sum(Receipt.total).desc())
        .limit(limit)
        .all()
    )

    return {
        "items": [
            {
                "vendor_name": row[0],
                "total_spent": _to_float(row[1]),
                "receipts_count": int(row[2]),
            }
            for row in rows
        ]
    }


def build_trend(
    db: Session,
    *,
    group_by: str = "month",
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict[str, Any]:
    filters = _base_filters(from_date, to_date)

    if group_by == "day":
        period_expr = cast(Receipt.issue_date, String)
    else:
        period_expr = func.to_char(func.date_trunc("month", Receipt.issue_date), "YYYY-MM")

    rows = (
        db.query(
            period_expr.label("period"),
            func.coalesce(func.sum(Receipt.total), 0).label("total_spent"),
            func.count(Receipt.id).label("receipts_count"),
        )
        .filter(and_(*(filters + [Receipt.issue_date.isnot(None)])))
        .group_by(period_expr)
        .order_by(period_expr.asc())
        .all()
    )

    return {
        "group_by": group_by,
        "items": [
            {
                "period": str(row[0]),
                "total_spent": _to_float(row[1]),
                "receipts_count": int(row[2]),
            }
            for row in rows
        ],
    }


def build_anomalies(
    db: Session,
    *,
    factor: float = 1.8,
    limit: int = 10,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict[str, Any]:
    filters = _base_filters(from_date, to_date)

    avg_total = (
        db.query(func.coalesce(func.avg(Receipt.total), 0))
        .filter(and_(*filters))
        .scalar()
    )
    average_ticket = _to_float(avg_total)
    threshold = average_ticket * factor

    if threshold <= 0:
        return {
            "average_ticket": average_ticket,
            "threshold": threshold,
            "items": [],
        }

    rows = (
        db.query(Receipt)
        .filter(and_(*(filters + [Receipt.total >= threshold])))
        .order_by(Receipt.total.desc())
        .limit(limit)
        .all()
    )

    return {
        "average_ticket": average_ticket,
        "threshold": threshold,
        "items": [
            {
                "receipt_id": receipt.id,
                "vendor_name": receipt.vendor_name,
                "issue_date": receipt.issue_date,
                "total": _to_float(receipt.total),
                "threshold": threshold,
                "reason": "total_above_dynamic_threshold",
            }
            for receipt in rows
        ],
    }
