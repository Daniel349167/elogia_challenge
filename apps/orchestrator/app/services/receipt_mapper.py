from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models import Receipt, ReceiptItem


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_receipt_items(db: Session, receipt_id: str) -> list[ReceiptItem]:
    return db.query(ReceiptItem).filter(ReceiptItem.receipt_id == receipt_id).all()


def serialize_receipt(receipt: Receipt, items: list[ReceiptItem]) -> dict[str, Any]:
    return {
        "id": receipt.id,
        "attachment_id": receipt.attachment_id,
        "conversation_id": receipt.conversation_id,
        "vendor_name": receipt.vendor_name,
        "vendor_tax_id": receipt.vendor_tax_id,
        "receipt_number": receipt.receipt_number,
        "issue_date": receipt.issue_date.isoformat() if receipt.issue_date else None,
        "currency": receipt.currency,
        "subtotal": _to_float(receipt.subtotal),
        "tax": _to_float(receipt.tax),
        "total": _to_float(receipt.total),
        "payment_method": receipt.payment_method,
        "confidence": receipt.confidence,
        "status": receipt.status,
        "raw_text": receipt.raw_text,
        "raw_json": receipt.raw_json,
        "created_at": receipt.created_at.isoformat() if receipt.created_at else None,
        "updated_at": receipt.updated_at.isoformat() if receipt.updated_at else None,
        "items": [
            {
                "id": item.id,
                "description": item.description,
                "quantity": _to_float(item.quantity) or 0.0,
                "unit_price": _to_float(item.unit_price),
                "line_total": _to_float(item.line_total),
            }
            for item in items
        ],
    }
