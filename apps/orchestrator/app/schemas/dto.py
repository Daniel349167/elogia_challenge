from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ReceiptItemOut(BaseModel):
    id: str
    description: str
    quantity: float
    unit_price: float | None = None
    line_total: float | None = None

    model_config = ConfigDict(from_attributes=True)


class ReceiptOut(BaseModel):
    id: str
    attachment_id: str | None = None
    conversation_id: str
    vendor_name: str
    vendor_tax_id: str | None = None
    receipt_number: str | None = None
    issue_date: date | None = None
    currency: str
    subtotal: float | None = None
    tax: float | None = None
    total: float | None = None
    payment_method: str | None = None
    confidence: float | None = None
    status: str
    raw_text: str | None = None
    raw_json: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
    items: list[ReceiptItemOut] = []

    model_config = ConfigDict(from_attributes=True)


class MessageOut(BaseModel):
    id: str
    conversation_id: str
    role: str
    text: str
    intent: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatResponse(BaseModel):
    conversation_id: str
    assistant_message: str
    receipt_id: str | None = None
    data: Any | None = None


class ReceiptPatchIn(BaseModel):
    vendor_name: str | None = None
    vendor_tax_id: str | None = None
    receipt_number: str | None = None
    issue_date: date | None = None
    currency: str | None = None
    subtotal: float | None = Field(default=None, ge=0)
    tax: float | None = Field(default=None, ge=0)
    total: float | None = Field(default=None, ge=0)
    payment_method: str | None = None
    status: str | None = None


class ReceiptListOut(BaseModel):
    total: int
    items: list[ReceiptOut]


class InsightSummaryOut(BaseModel):
    total_receipts: int
    total_spent: float
    average_ticket: float
    top_vendor: str | None = None
    top_vendor_total: float | None = None


class InsightVendorItemOut(BaseModel):
    vendor_name: str
    total_spent: float
    receipts_count: int


class InsightVendorsOut(BaseModel):
    items: list[InsightVendorItemOut]


class InsightTrendPointOut(BaseModel):
    period: str
    total_spent: float
    receipts_count: int


class InsightTrendOut(BaseModel):
    group_by: str
    items: list[InsightTrendPointOut]


class InsightAnomalyItemOut(BaseModel):
    receipt_id: str
    vendor_name: str
    issue_date: date | None = None
    total: float
    threshold: float
    reason: str


class InsightAnomaliesOut(BaseModel):
    average_ticket: float
    threshold: float
    items: list[InsightAnomalyItemOut]
