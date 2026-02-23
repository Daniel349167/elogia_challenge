import json
import os
import uuid
from pathlib import Path

import requests


API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
API_TIMEOUT = float(os.getenv("API_TIMEOUT", "30"))


def _post_chat_message(message: str | None, file_path: Path | None, conversation_id: str | None = None) -> dict:
    data: dict[str, str] = {}
    if conversation_id:
        data["conversation_id"] = conversation_id
    if message:
        data["message"] = message

    files = None
    if file_path is not None:
        files = {
            "file": (file_path.name, file_path.read_bytes(), "text/plain"),
        }

    response = requests.post(
        f"{API_BASE_URL}/api/v1/chat/message",
        data=data,
        files=files,
        timeout=API_TIMEOUT,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _collect_sse_events(response: requests.Response) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    current_event = "message"
    data_lines: list[str] = []

    for raw_line in response.iter_lines(decode_unicode=True):
        if raw_line is None:
            continue

        line = raw_line.strip("\r")
        if line == "":
            if data_lines:
                events.append({"event": current_event, "data": "\n".join(data_lines)})
                if current_event == "final":
                    return events
            current_event = "message"
            data_lines = []
            continue

        if line.startswith("event:"):
            current_event = line.split(":", 1)[1].strip()
            continue

        if line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].lstrip())

    return events


def test_end_to_end_upload_query_and_duplicate_detection(tmp_path: Path) -> None:
    unique_tag = uuid.uuid4().hex[:8]
    receipt_file = tmp_path / f"receipt-{unique_tag}.txt"
    receipt_file.write_text(
        "\n".join(
            [
                "TIENDA QA SAC",
                f"FACTURA: F001-{unique_tag}",
                "FECHA: 2026-02-23",
                "TOTAL: 480.75",
                "METODO: TARJETA",
            ]
        ),
        encoding="utf-8",
    )

    first = _post_chat_message(message="Procesa este comprobante", file_path=receipt_file)
    conversation_id = first.get("conversation_id")
    receipt_id = first.get("receipt_id")

    assert conversation_id
    assert receipt_id
    assert "Comprobante procesado" in first.get("assistant_message", "")

    get_receipt = requests.get(f"{API_BASE_URL}/api/v1/receipts/{receipt_id}", timeout=API_TIMEOUT)
    assert get_receipt.status_code == 200, get_receipt.text

    receipt_payload = get_receipt.json()
    assert receipt_payload["id"] == receipt_id
    assert receipt_payload["total"] is not None

    query_by_id = _post_chat_message(message=f"comprobante {receipt_id}", file_path=None, conversation_id=conversation_id)
    assert "Encontre" in query_by_id.get("assistant_message", "")

    query_search = _post_chat_message(
        message="buscar comprobantes mayor a 200",
        file_path=None,
        conversation_id=conversation_id,
    )
    assert "Encontre" in query_search.get("assistant_message", "")

    second = _post_chat_message(message="Mismo archivo otra vez", file_path=receipt_file, conversation_id=conversation_id)
    assert second.get("receipt_id")
    assert second["receipt_id"] != receipt_id
    assert "duplicado" in second.get("assistant_message", "").lower()
    assert second.get("data", {}).get("duplicate_of_receipt_id") == receipt_id

    insights = requests.get(f"{API_BASE_URL}/api/v1/insights/summary", timeout=API_TIMEOUT)
    assert insights.status_code == 200, insights.text
    insights_payload = insights.json()
    assert insights_payload["total_receipts"] >= 2
    assert insights_payload["total_spent"] > 0


def test_streaming_endpoint_emits_final_event() -> None:
    response = requests.post(
        f"{API_BASE_URL}/api/v1/chat/message/stream",
        data={"message": "resumen"},
        headers={"Accept": "text/event-stream"},
        timeout=API_TIMEOUT,
        stream=True,
    )
    try:
        assert response.status_code == 200, response.text
        assert "text/event-stream" in response.headers.get("content-type", "")

        events = _collect_sse_events(response)
        assert events

        final_event = next((event for event in events if event["event"] == "final"), None)
        assert final_event is not None

        final_payload = json.loads(final_event["data"])
        assert final_payload.get("conversation_id")
        assert final_payload.get("assistant_message")
    finally:
        response.close()


def test_upload_validation_rejects_disallowed_extension(tmp_path: Path) -> None:
    blocked_file = tmp_path / "payload.exe"
    blocked_file.write_text("dummy", encoding="utf-8")

    response = requests.post(
        f"{API_BASE_URL}/api/v1/chat/message",
        data={"message": "archivo no permitido"},
        files={"file": (blocked_file.name, blocked_file.read_bytes(), "application/octet-stream")},
        timeout=API_TIMEOUT,
    )

    assert response.status_code == 400, response.text
    body = response.json()
    assert "no permitida" in body["error"]["message"].lower()


def test_manual_correction_patch_updates_receipt(tmp_path: Path) -> None:
    receipt_file = tmp_path / "editable.txt"
    receipt_file.write_text(
        "\n".join(
            [
                "TIENDA EDITABLE SAC",
                "FACTURA: F002-9911",
                "FECHA: 2026-02-23",
                "TOTAL: 210.00",
            ]
        ),
        encoding="utf-8",
    )

    created = _post_chat_message(message="crear para editar", file_path=receipt_file)
    receipt_id = created["receipt_id"]

    patch_response = requests.patch(
        f"{API_BASE_URL}/api/v1/receipts/{receipt_id}",
        json={
            "vendor_name": "TIENDA EDITADA SAC",
            "total": 215.5,
            "status": "manually_corrected",
        },
        timeout=API_TIMEOUT,
    )

    assert patch_response.status_code == 200, patch_response.text
    payload = patch_response.json()
    assert payload["vendor_name"] == "TIENDA EDITADA SAC"
    assert payload["total"] == 215.5
    assert payload["status"] == "manually_corrected"


def test_advanced_insights_endpoints() -> None:
    vendors = requests.get(f"{API_BASE_URL}/api/v1/insights/vendors?limit=5", timeout=API_TIMEOUT)
    trend = requests.get(f"{API_BASE_URL}/api/v1/insights/trend?group_by=month", timeout=API_TIMEOUT)
    anomalies = requests.get(f"{API_BASE_URL}/api/v1/insights/anomalies?factor=1.2&limit=5", timeout=API_TIMEOUT)

    assert vendors.status_code == 200, vendors.text
    assert trend.status_code == 200, trend.text
    assert anomalies.status_code == 200, anomalies.text

    vendors_body = vendors.json()
    trend_body = trend.json()
    anomalies_body = anomalies.json()

    assert isinstance(vendors_body.get("items"), list)
    assert trend_body.get("group_by") == "month"
    assert isinstance(trend_body.get("items"), list)
    assert "threshold" in anomalies_body
    assert isinstance(anomalies_body.get("items"), list)
