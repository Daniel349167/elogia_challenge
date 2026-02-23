from fastapi import APIRouter

from app.providers.mock_analyzer import analyze_mock
from app.schemas.jsonrpc import AnalyzeParams, JsonRpcError, JsonRpcErrorDetail, JsonRpcRequest, JsonRpcSuccess

router = APIRouter()


@router.post("/rpc", response_model=JsonRpcSuccess | JsonRpcError)
def rpc_handler(payload: JsonRpcRequest) -> JsonRpcSuccess | JsonRpcError:
    if payload.jsonrpc != "2.0":
        return JsonRpcError(
            id=payload.id,
            error=JsonRpcErrorDetail(code=-32600, message="Invalid JSON-RPC version"),
        )

    if payload.method != "analyze_receipt":
        return JsonRpcError(
            id=payload.id,
            error=JsonRpcErrorDetail(code=-32601, message=f"Method {payload.method} not found"),
        )

    try:
        params = AnalyzeParams.model_validate(payload.params)
    except Exception as exc:  # noqa: BLE001
        return JsonRpcError(
            id=payload.id,
            error=JsonRpcErrorDetail(code=-32602, message="Invalid params", data={"detail": str(exc)}),
        )

    result = analyze_mock(
        filename=params.filename,
        mime_type=params.mime_type,
        content_base64=params.content_base64,
        text_hint=params.text_hint,
    )
    return JsonRpcSuccess(id=payload.id, result=result)
