import re
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models import Receipt
from app.services.insights_service import build_anomalies, build_summary, build_top_vendors, build_trend
from app.services.receipt_mapper import load_receipt_items, serialize_receipt


HELP_TEXT = (
    "Puedo ayudarte con:\n"
    "1) 'comprobante <id>' para ver un comprobante\n"
    "2) 'buscar comprobantes mayor a 500' para filtrar por monto\n"
    "3) 'resumen' para ver insights simples\n"
    "4) 'top proveedores', 'tendencia mensual' o 'anomalias'"
)


class QueryResult:
    def __init__(self, message: str, data: Any = None) -> None:
        self.message = message
        self.data = data


def _to_float(value: Decimal | float | int | None) -> float:
    if value is None:
        return 0.0
    return float(value)


def _parse_amount(text: str) -> float | None:
    match = re.search(r"(\d+[\.,]?\d*)", text)
    if not match:
        return None
    normalized = match.group(1).replace(",", ".")
    try:
        return float(normalized)
    except ValueError:
        return None


def _parse_receipt_id(text: str) -> str | None:
    match = re.search(r"([0-9a-fA-F]{8}-[0-9a-fA-F-]{27})", text)
    if match:
        return match.group(1)

    simple = re.search(r"comprobante\s+([A-Za-z0-9-]+)", text)
    if simple:
        return simple.group(1)

    return None


def handle_text_query(db: Session, text: str) -> QueryResult:
    normalized = text.strip().lower()

    if not normalized:
        return QueryResult("Envia un mensaje o un archivo para continuar.")

    if "resumen" in normalized or "insight" in normalized:
        return _build_summary(db)

    if "top" in normalized and ("proveedor" in normalized or "vendor" in normalized):
        top = build_top_vendors(db, limit=5)
        if not top["items"]:
            return QueryResult("No hay suficientes datos para top proveedores.", top)

        first = top["items"][0]
        message = (
            f"Top proveedores listo. #1 {first['vendor_name']} con {first['total_spent']:.2f}."
        )
        return QueryResult(message, top)

    if "tendencia" in normalized or "trend" in normalized:
        group_by = "day" if "dia" in normalized else "month"
        trend = build_trend(db, group_by=group_by)
        if not trend["items"]:
            return QueryResult("No hay suficientes datos para tendencia.", trend)

        message = f"Tendencia {group_by} generada con {len(trend['items'])} puntos."
        return QueryResult(message, trend)

    if "anomalia" in normalized or "anomal" in normalized:
        anomalies = build_anomalies(db, factor=1.8, limit=10)
        if not anomalies["items"]:
            return QueryResult("No detecte anomalias con el umbral actual.", anomalies)

        message = (
            f"Detecte {len(anomalies['items'])} anomalias sobre umbral {anomalies['threshold']:.2f}."
        )
        return QueryResult(message, anomalies)

    if "comprobante" in normalized and "buscar" not in normalized:
        receipt_id = _parse_receipt_id(text)
        if not receipt_id:
            return QueryResult("No pude detectar un ID. Usa: comprobante <id>")

        receipt = db.query(Receipt).filter(Receipt.id == receipt_id).first()
        if not receipt:
            return QueryResult(f"No encontre el comprobante {receipt_id}.")

        payload = serialize_receipt(receipt, load_receipt_items(db, receipt.id))
        return QueryResult(
            f"Encontre el comprobante {receipt.id} por {payload['total']} {payload['currency']}.",
            payload,
        )

    if "buscar" in normalized or "mayor" in normalized or ">" in normalized:
        amount = _parse_amount(normalized)
        if amount is None:
            amount = 0.0

        vendor_match = re.search(r"proveedor\s+([a-zA-Z0-9\s]+)", text, re.IGNORECASE)
        query = db.query(Receipt)
        filters = [Receipt.total.isnot(None), Receipt.total >= amount]
        if vendor_match:
            vendor = vendor_match.group(1).strip()
            filters.append(Receipt.vendor_name.ilike(f"%{vendor}%"))

        receipts = query.filter(and_(*filters)).order_by(Receipt.created_at.desc()).limit(20).all()
        if not receipts:
            return QueryResult(f"No encontre comprobantes con total >= {amount:.2f}.")

        data = [serialize_receipt(r, load_receipt_items(db, r.id)) for r in receipts]
        return QueryResult(f"Encontre {len(data)} comprobantes con total >= {amount:.2f}.", data)

    return QueryResult(HELP_TEXT)


def _build_summary(db: Session) -> QueryResult:
    data = build_summary(db)
    data["generated_at"] = date.today().isoformat()

    message = (
        f"Resumen: {data['total_receipts']} comprobantes, gasto total {data['total_spent']:.2f}, "
        f"ticket promedio {data['average_ticket']:.2f}."
    )
    if data.get("top_vendor"):
        message += f" Proveedor con mayor gasto: {data['top_vendor']} ({_to_float(data['top_vendor_total']):.2f})."

    return QueryResult(message, data)
