import asyncio
import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Attachment, Conversation, ExtractionRun, Message, Receipt, ReceiptItem
from app.schemas import ChatResponse, MessageOut
from app.services.agent_client import AgentClient, AgentClientError
from app.services.query_interpreter import handle_text_query
from app.services.receipt_mapper import load_receipt_items, serialize_receipt
from app.services.receipt_validation import validate_receipt_payload, validate_upload

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])
agent_client = AgentClient()
settings = get_settings()


@dataclass(slots=True)
class FilePayload:
    filename: str
    mime_type: str
    content: bytes


def _get_or_create_conversation(db: Session, conversation_id: str | None) -> Conversation:
    if conversation_id:
        existing = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if existing:
            return existing
        conversation = Conversation(id=conversation_id)
    else:
        conversation = Conversation()

    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def _create_message(db: Session, conversation_id: str, role: str, text: str, intent: str | None = None) -> Message:
    message = Message(conversation_id=conversation_id, role=role, text=text, intent=intent)
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def _read_file_payload(file: UploadFile | None) -> FilePayload | None:
    if file is None:
        return None

    content = await file.read()
    payload = FilePayload(
        filename=file.filename or "attachment.bin",
        mime_type=file.content_type or "application/octet-stream",
        content=content,
    )

    validate_upload(
        filename=payload.filename,
        mime_type=payload.mime_type,
        size_bytes=len(payload.content),
        settings=settings,
    )

    return payload


def _store_attachment(db: Session, message_id: str, conversation_id: str, payload: FilePayload) -> Attachment:
    conversation_dir = os.path.join(settings.upload_dir, conversation_id)
    os.makedirs(conversation_dir, exist_ok=True)

    stored_filename = f"{uuid.uuid4()}_{payload.filename}"
    storage_path = os.path.join(conversation_dir, stored_filename)

    with open(storage_path, "wb") as out_file:
        out_file.write(payload.content)

    attachment = Attachment(
        message_id=message_id,
        filename=payload.filename,
        mime_type=payload.mime_type,
        storage_path=storage_path,
        sha256=hashlib.sha256(payload.content).hexdigest(),
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return attachment


def _persist_items(db: Session, receipt_id: str, items: list[dict[str, Any]]) -> None:
    for item in items:
        db.add(
            ReceiptItem(
                receipt_id=receipt_id,
                description=item.get("description") or "Item",
                quantity=_safe_float(item.get("quantity")) or 1,
                unit_price=_safe_float(item.get("unit_price")),
                line_total=_safe_float(item.get("line_total")),
            )
        )


def _create_receipt_from_agent(
    db: Session,
    conversation_id: str,
    attachment: Attachment,
    file_bytes: bytes,
    text_hint: str | None,
) -> tuple[Receipt, list[str]]:
    import time

    start = time.perf_counter()
    result = agent_client.analyze_receipt(
        file_bytes=file_bytes,
        filename=attachment.filename,
        mime_type=attachment.mime_type,
        text_hint=text_hint,
    )
    latency_ms = int((time.perf_counter() - start) * 1000)

    receipt_payload = result.get("receipt", {})
    receipt_payload, validation_warnings, receipt_status = validate_receipt_payload(receipt_payload)

    issue_date_str = receipt_payload.get("issue_date")
    issue_date = None
    if issue_date_str:
        try:
            issue_date = date.fromisoformat(str(issue_date_str))
        except ValueError:
            issue_date = None

    raw_json = dict(result)
    raw_json["validation"] = {
        "warnings": validation_warnings,
        "validated_at": date.today().isoformat(),
    }

    receipt = Receipt(
        attachment_id=attachment.id,
        conversation_id=conversation_id,
        vendor_name=receipt_payload.get("vendor_name") or "Proveedor desconocido",
        vendor_tax_id=receipt_payload.get("vendor_tax_id"),
        receipt_number=receipt_payload.get("receipt_number"),
        issue_date=issue_date,
        currency=receipt_payload.get("currency") or "PEN",
        subtotal=_safe_float(receipt_payload.get("subtotal")),
        tax=_safe_float(receipt_payload.get("tax")),
        total=_safe_float(receipt_payload.get("total")),
        payment_method=receipt_payload.get("payment_method"),
        confidence=_safe_float(receipt_payload.get("confidence")),
        status=receipt_status,
        raw_text=receipt_payload.get("raw_text"),
        raw_json=raw_json,
    )
    db.add(receipt)
    db.commit()
    db.refresh(receipt)

    _persist_items(db, receipt.id, receipt_payload.get("items", []))

    db.add(
        ExtractionRun(
            receipt_id=receipt.id,
            provider=result.get("provider", "mock-agent"),
            model=result.get("model", "mock-rules-v1"),
            success=True,
            latency_ms=latency_ms,
            error=None,
        )
    )
    db.commit()

    return receipt, validation_warnings


def _create_duplicate_receipt(
    db: Session,
    conversation_id: str,
    attachment: Attachment,
    source_receipt: Receipt,
) -> Receipt:
    duplicated = Receipt(
        attachment_id=attachment.id,
        conversation_id=conversation_id,
        vendor_name=source_receipt.vendor_name,
        vendor_tax_id=source_receipt.vendor_tax_id,
        receipt_number=source_receipt.receipt_number,
        issue_date=source_receipt.issue_date,
        currency=source_receipt.currency,
        subtotal=_safe_float(source_receipt.subtotal),
        tax=_safe_float(source_receipt.tax),
        total=_safe_float(source_receipt.total),
        payment_method=source_receipt.payment_method,
        confidence=source_receipt.confidence,
        status="duplicate",
        raw_text=source_receipt.raw_text,
        raw_json={
            "source": "sha256",
            "duplicate_of_receipt_id": source_receipt.id,
        },
    )
    db.add(duplicated)
    db.commit()
    db.refresh(duplicated)

    source_items = load_receipt_items(db, source_receipt.id)
    for item in source_items:
        db.add(
            ReceiptItem(
                receipt_id=duplicated.id,
                description=item.description,
                quantity=_safe_float(item.quantity) or 1,
                unit_price=_safe_float(item.unit_price),
                line_total=_safe_float(item.line_total),
            )
        )

    db.add(
        ExtractionRun(
            receipt_id=duplicated.id,
            provider="dedupe",
            model="sha256-v1",
            success=True,
            latency_ms=0,
            error=None,
        )
    )
    db.commit()

    return duplicated


def _create_failed_receipt(
    db: Session,
    conversation_id: str,
    attachment: Attachment,
    *,
    error_code: str,
    error_message: str,
) -> Receipt:
    receipt = Receipt(
        attachment_id=attachment.id,
        conversation_id=conversation_id,
        vendor_name="Procesamiento fallido",
        currency="PEN",
        status="error",
        raw_json={
            "error": {
                "code": error_code,
                "message": error_message,
            }
        },
    )
    db.add(receipt)
    db.commit()
    db.refresh(receipt)

    db.add(
        ExtractionRun(
            receipt_id=receipt.id,
            provider="mock-agent",
            model="unknown",
            success=False,
            latency_ms=None,
            error=f"{error_code}: {error_message}",
        )
    )
    db.commit()

    return receipt


def _find_business_duplicate_candidate(db: Session, receipt: Receipt) -> Receipt | None:
    if not receipt.receipt_number or not receipt.issue_date or receipt.total is None:
        return None

    return (
        db.query(Receipt)
        .filter(
            and_(
                Receipt.id != receipt.id,
                Receipt.receipt_number == receipt.receipt_number,
                Receipt.issue_date == receipt.issue_date,
                Receipt.total == receipt.total,
            )
        )
        .order_by(Receipt.created_at.asc())
        .first()
    )


def _process_message(
    db: Session,
    conversation_id: str | None,
    text: str,
    file_payload: FilePayload | None,
) -> ChatResponse:
    if not text and not file_payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Debes enviar texto y/o archivo")

    conversation = _get_or_create_conversation(db, conversation_id)
    user_text = text if text else f"[file] {file_payload.filename if file_payload else 'sin-nombre'}"
    user_message = _create_message(db, conversation.id, "user", user_text)

    if file_payload is None:
        result = handle_text_query(db, text)
        _create_message(db, conversation.id, "assistant", result.message, intent="query")
        return ChatResponse(conversation_id=conversation.id, assistant_message=result.message, data=result.data)

    attachment = _store_attachment(db, user_message.id, conversation.id, file_payload)

    duplicate_source = (
        db.query(Receipt)
        .join(Attachment, Receipt.attachment_id == Attachment.id)
        .filter(
            and_(
                Attachment.sha256 == attachment.sha256,
                Attachment.id != attachment.id,
            )
        )
        .order_by(Receipt.created_at.asc())
        .first()
    )

    if duplicate_source:
        receipt = _create_duplicate_receipt(db, conversation.id, attachment, duplicate_source)
        data = serialize_receipt(receipt, load_receipt_items(db, receipt.id))
        data["duplicate_of_receipt_id"] = duplicate_source.id

        assistant_text = (
            f"Archivo duplicado detectado por hash. Se registro el comprobante {receipt.id} "
            f"enlazado al original {duplicate_source.id}."
        )
        _create_message(db, conversation.id, "assistant", assistant_text, intent="analyze_receipt_duplicate")

        return ChatResponse(
            conversation_id=conversation.id,
            assistant_message=assistant_text,
            receipt_id=receipt.id,
            data=data,
        )

    try:
        receipt, warnings = _create_receipt_from_agent(
            db=db,
            conversation_id=conversation.id,
            attachment=attachment,
            file_bytes=file_payload.content,
            text_hint=text or None,
        )
    except AgentClientError as exc:
        failed = _create_failed_receipt(
            db,
            conversation.id,
            attachment,
            error_code=exc.code,
            error_message=str(exc),
        )

        assistant_text = (
            "No pude procesar el comprobante en este momento. "
            f"Codigo: {exc.code}. Detalle: {exc}"
        )
        _create_message(db, conversation.id, "assistant", assistant_text, intent="analyze_receipt_error")

        return ChatResponse(
            conversation_id=conversation.id,
            assistant_message=assistant_text,
            receipt_id=failed.id,
            data={"error_code": exc.code, "retriable": exc.retriable},
        )

    business_duplicate = _find_business_duplicate_candidate(db, receipt)
    data = serialize_receipt(receipt, load_receipt_items(db, receipt.id))

    if business_duplicate:
        receipt.status = "duplicate_candidate"
        enriched_raw = dict(receipt.raw_json or {})
        enriched_raw["validation"] = dict(enriched_raw.get("validation") or {})
        enriched_raw["validation"]["duplicate_candidate_of_receipt_id"] = business_duplicate.id
        receipt.raw_json = enriched_raw
        db.add(receipt)
        db.commit()
        db.refresh(receipt)

        data = serialize_receipt(receipt, load_receipt_items(db, receipt.id))
        data["duplicate_candidate_of_receipt_id"] = business_duplicate.id

    assistant_text = (
        f"Comprobante procesado. ID: {receipt.id}. "
        f"Proveedor: {receipt.vendor_name}. Total: {data['total']} {receipt.currency}."
    )
    if warnings:
        assistant_text += f" Validaciones: {len(warnings)} alerta(s)."
    if business_duplicate:
        assistant_text += f" Posible duplicado de negocio: {business_duplicate.id}."

    _create_message(db, conversation.id, "assistant", assistant_text, intent="analyze_receipt")

    return ChatResponse(
        conversation_id=conversation.id,
        assistant_message=assistant_text,
        receipt_id=receipt.id,
        data=data,
    )


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/message", response_model=ChatResponse)
async def send_message(
    conversation_id: str | None = Form(default=None),
    message: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
) -> ChatResponse:
    text = (message or "").strip()
    payload = await _read_file_payload(file)
    return _process_message(db=db, conversation_id=conversation_id, text=text, file_payload=payload)


@router.post("/message/stream")
async def send_message_stream(
    conversation_id: str | None = Form(default=None),
    message: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    text = (message or "").strip()
    payload = await _read_file_payload(file)

    async def event_stream() -> Any:
        yield _sse("start", {"status": "processing"})

        try:
            response = _process_message(db=db, conversation_id=conversation_id, text=text, file_payload=payload)
        except HTTPException as exc:
            yield _sse("error", {"message": str(exc.detail), "status_code": exc.status_code})
            return
        except Exception as exc:  # noqa: BLE001
            yield _sse("error", {"message": f"Unexpected error: {exc}"})
            return

        assistant_text = response.assistant_message or ""
        if assistant_text:
            for index in range(0, len(assistant_text), 24):
                chunk = assistant_text[index : index + 24]
                yield _sse("delta", {"content": chunk})
                await asyncio.sleep(0.015)

        yield _sse("final", response.model_dump())

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def get_conversation_messages(conversation_id: str, db: Session = Depends(get_db)) -> list[MessageOut]:
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation no encontrada")

    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
        .all()
    )
    return [MessageOut.model_validate(msg) for msg in messages]
