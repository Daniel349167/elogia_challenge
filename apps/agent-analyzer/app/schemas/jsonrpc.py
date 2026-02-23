from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JsonRpcRequest(BaseModel):
    jsonrpc: str = Field(default="2.0")
    id: str | int
    method: str
    params: dict[str, Any]


class JsonRpcSuccess(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int
    result: dict[str, Any]


class JsonRpcErrorDetail(BaseModel):
    code: int
    message: str
    data: dict[str, Any] | None = None


class JsonRpcError(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int | None
    error: JsonRpcErrorDetail


class AnalyzeParams(BaseModel):
    filename: str
    mime_type: str
    content_base64: str
    text_hint: str | None = None

    model_config = ConfigDict(extra="ignore")
