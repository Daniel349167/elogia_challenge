from datetime import date
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status

from app.config import Settings

VALID_CURRENCIES = {"PEN", "USD", "EUR", "COP", "MXN", "CLP", "ARS", "BRL"}


def validate_upload(*, filename: str, mime_type: str, size_bytes: int, settings: Settings) -> None:
    extension = Path(filename).suffix.lower()
    mime_normalized = (mime_type or "").lower()

    if size_bytes <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo esta vacio")

    if size_bytes > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Archivo excede limite de {settings.max_upload_bytes} bytes",
        )

    if extension not in settings.allowed_extensions_set:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Extension no permitida: {extension or 'sin extension'}",
        )

    if mime_normalized and mime_normalized not in settings.allowed_mime_types_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"MIME no permitido: {mime_normalized}",
        )


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def validate_receipt_payload(receipt_payload: dict[str, Any]) -> tuple[dict[str, Any], list[str], str]:
    payload = dict(receipt_payload)
    warnings: list[str] = []

    vendor_name = str(payload.get("vendor_name") or "").strip()
    if len(vendor_name) < 3:
        warnings.append("vendor_name_too_short")

    currency = str(payload.get("currency") or "PEN").upper().strip()
    payload["currency"] = currency
    if currency not in VALID_CURRENCIES:
        warnings.append("currency_outside_allowlist")

    subtotal = _to_float(payload.get("subtotal"))
    tax = _to_float(payload.get("tax"))
    total = _to_float(payload.get("total"))

    if total is None or total <= 0:
        warnings.append("total_missing_or_non_positive")

    if subtotal is not None and tax is not None and total is not None:
        if abs((subtotal + tax) - total) > 1.0:
            warnings.append("amount_inconsistency_subtotal_tax_total")

    issue_date_raw = payload.get("issue_date")
    if issue_date_raw:
        try:
            parsed_date = date.fromisoformat(str(issue_date_raw))
            if parsed_date > date.today():
                warnings.append("issue_date_in_future")
        except ValueError:
            warnings.append("issue_date_invalid")

    status_value = "processed" if not warnings else "processed_with_warnings"
    return payload, warnings, status_value
