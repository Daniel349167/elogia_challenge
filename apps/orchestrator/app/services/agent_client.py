import base64
import time
import uuid
from typing import Any

import httpx

from app.config import get_settings


class AgentClientError(RuntimeError):
    def __init__(self, code: str, message: str, *, retriable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retriable = retriable


class AgentClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    def analyze_receipt(
        self,
        *,
        file_bytes: bytes,
        filename: str,
        mime_type: str,
        text_hint: str | None,
    ) -> dict[str, Any]:
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "analyze_receipt",
            "params": {
                "filename": filename,
                "mime_type": mime_type,
                "content_base64": base64.b64encode(file_bytes).decode("utf-8"),
                "text_hint": text_hint,
            },
        }

        retries = max(self.settings.agent_retries, 0)
        backoff = max(self.settings.agent_backoff_seconds, 0)
        timeout = max(self.settings.agent_timeout_seconds, 1)

        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                with httpx.Client(timeout=timeout) as client:
                    response = client.post(self.settings.agent_url, json=payload)
                    response.raise_for_status()
                    body = response.json()

                if body.get("error"):
                    error = body["error"]
                    message = error.get("message", "Unknown analyzer error")
                    raise AgentClientError("agent_rpc_error", f"Agent error: {message}", retriable=False)

                result = body.get("result")
                if not result:
                    raise AgentClientError("agent_empty_result", "Agent returned empty result", retriable=False)

                return result
            except AgentClientError:
                raise
            except httpx.TimeoutException as exc:
                last_error = exc
                if attempt < retries:
                    time.sleep(backoff * (attempt + 1))
                    continue
                raise AgentClientError(
                    "agent_timeout",
                    "Analyzer timeout after retries",
                    retriable=True,
                ) from exc
            except httpx.HTTPStatusError as exc:
                last_error = exc
                status_code = exc.response.status_code
                retriable = status_code >= 500
                if retriable and attempt < retries:
                    time.sleep(backoff * (attempt + 1))
                    continue
                raise AgentClientError(
                    "agent_http_error",
                    f"Analyzer HTTP error: {status_code}",
                    retriable=retriable,
                ) from exc
            except httpx.TransportError as exc:
                last_error = exc
                if attempt < retries:
                    time.sleep(backoff * (attempt + 1))
                    continue
                raise AgentClientError(
                    "agent_transport_error",
                    "Analyzer unavailable after retries",
                    retriable=True,
                ) from exc
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                break

        raise AgentClientError("agent_unexpected_error", f"Unexpected analyzer error: {last_error}")
