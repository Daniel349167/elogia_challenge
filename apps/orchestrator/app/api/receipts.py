from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Receipt
from app.schemas import ReceiptListOut, ReceiptOut, ReceiptPatchIn
from app.services.receipt_mapper import load_receipt_items, serialize_receipt

router = APIRouter(prefix="/api/v1/receipts", tags=["receipts"])


@router.get("/{receipt_id}", response_model=ReceiptOut)
def get_receipt(receipt_id: str, db: Session = Depends(get_db)) -> ReceiptOut:
    receipt = db.query(Receipt).filter(Receipt.id == receipt_id).first()
    if not receipt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comprobante no encontrado")

    payload = serialize_receipt(receipt, load_receipt_items(db, receipt.id))
    return ReceiptOut.model_validate(payload)


@router.get("", response_model=ReceiptListOut)
def list_receipts(
    vendor: str | None = Query(default=None),
    min_total: float | None = Query(default=None, ge=0),
    max_total: float | None = Query(default=None, ge=0),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
) -> ReceiptListOut:
    query = db.query(Receipt)
    filters = []

    if vendor:
        filters.append(Receipt.vendor_name.ilike(f"%{vendor}%"))
    if min_total is not None:
        filters.append(Receipt.total >= min_total)
    if max_total is not None:
        filters.append(Receipt.total <= max_total)
    if from_date:
        filters.append(Receipt.issue_date >= from_date)
    if to_date:
        filters.append(Receipt.issue_date <= to_date)

    if filters:
        query = query.filter(and_(*filters))

    receipts = query.order_by(Receipt.created_at.desc()).limit(100).all()
    items = [ReceiptOut.model_validate(serialize_receipt(r, load_receipt_items(db, r.id))) for r in receipts]

    return ReceiptListOut(total=len(items), items=items)


@router.patch("/{receipt_id}", response_model=ReceiptOut)
def patch_receipt(receipt_id: str, payload: ReceiptPatchIn, db: Session = Depends(get_db)) -> ReceiptOut:
    receipt = db.query(Receipt).filter(Receipt.id == receipt_id).first()
    if not receipt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comprobante no encontrado")

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(receipt, field, value)

    db.add(receipt)
    db.commit()
    db.refresh(receipt)

    return ReceiptOut.model_validate(serialize_receipt(receipt, load_receipt_items(db, receipt.id)))
