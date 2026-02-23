"use client";

import { FormEvent, useMemo, useState } from "react";

type UiMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  data?: unknown;
};

type ChatResponse = {
  conversation_id: string;
  assistant_message: string;
  receipt_id?: string | null;
  data?: unknown;
};

type StreamDelta = {
  content?: string;
};

type StreamError = {
  message?: string;
};

type EditableReceipt = {
  id: string;
  vendor_name: string;
  receipt_number: string;
  payment_method: string;
  status: string;
  currency: string;
  issue_date: string;
  subtotal: string;
  tax: string;
  total: string;
};

const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function toJsonPreview(data: unknown): string {
  try {
    return JSON.stringify(data, null, 2);
  } catch {
    return String(data);
  }
}

function parseJson<T>(value: string): T | null {
  try {
    return JSON.parse(value) as T;
  } catch {
    return null;
  }
}

function parseSseBlock(block: string): { event: string; data: string } | null {
  const lines = block.split("\n");
  let event = "message";
  const dataLines: string[] = [];

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    if (!line) continue;

    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
      continue;
    }

    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }

  if (dataLines.length === 0) {
    return null;
  }

  return { event, data: dataLines.join("\n") };
}

function extractReceiptId(data: unknown): string | null {
  if (!data || typeof data !== "object") return null;
  const maybeId = (data as Record<string, unknown>).id;
  return typeof maybeId === "string" ? maybeId : null;
}

function parseApiError(raw: string): string {
  const parsed = parseJson<{ error?: { message?: string } }>(raw);
  if (parsed?.error?.message) return parsed.error.message;
  return raw;
}

function toEditableReceipt(data: Record<string, unknown>): EditableReceipt {
  return {
    id: String(data.id ?? ""),
    vendor_name: String(data.vendor_name ?? ""),
    receipt_number: String(data.receipt_number ?? ""),
    payment_method: String(data.payment_method ?? ""),
    status: String(data.status ?? "processed"),
    currency: String(data.currency ?? "PEN"),
    issue_date: String(data.issue_date ?? ""),
    subtotal: data.subtotal != null ? String(data.subtotal) : "",
    tax: data.tax != null ? String(data.tax) : "",
    total: data.total != null ? String(data.total) : "",
  };
}

export function ChatPanel() {
  const [conversationId, setConversationId] = useState<string>("");
  const [input, setInput] = useState<string>("");
  const [file, setFile] = useState<File | null>(null);
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [loading, setLoading] = useState<boolean>(false);

  const [editReceiptId, setEditReceiptId] = useState<string>("");
  const [editableReceipt, setEditableReceipt] = useState<EditableReceipt | null>(null);
  const [editorLoading, setEditorLoading] = useState<boolean>(false);
  const [editorMessage, setEditorMessage] = useState<string>("");

  const placeholder = useMemo(
    () => "Ejemplo: top proveedores, tendencia mensual o subir comprobante",
    [],
  );

  const appendMessage = (message: UiMessage) => setMessages((prev) => [...prev, message]);

  const patchMessage = (id: string, patch: Partial<UiMessage>) => {
    setMessages((prev) => prev.map((msg) => (msg.id === id ? { ...msg, ...patch } : msg)));
  };

  const appendMessageText = (id: string, textToAppend: string) => {
    setMessages((prev) =>
      prev.map((msg) =>
        msg.id === id
          ? {
              ...msg,
              text: `${msg.text}${textToAppend}`,
            }
          : msg,
      ),
    );
  };

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (loading) return;

    const text = input.trim();
    if (!text && !file) return;

    appendMessage({
      id: crypto.randomUUID(),
      role: "user",
      text: file ? `${text || "Archivo enviado"} (${file.name})` : text,
    });

    const assistantId = crypto.randomUUID();
    appendMessage({ id: assistantId, role: "assistant", text: "Procesando..." });

    const formData = new FormData();
    if (conversationId) formData.append("conversation_id", conversationId);
    if (text) formData.append("message", text);
    if (file) formData.append("file", file);

    setInput("");
    setFile(null);
    setLoading(true);

    try {
      await sendMessageStreaming(formData, assistantId);
    } catch (error) {
      patchMessage(assistantId, {
        text: `Error: ${error instanceof Error ? error.message : "No se pudo completar la solicitud"}`,
        data: undefined,
      });
    } finally {
      setLoading(false);
    }
  }

  async function sendMessageStreaming(formData: FormData, assistantId: string): Promise<void> {
    const response = await fetch(`${apiBase}/api/v1/chat/message/stream`, {
      method: "POST",
      body: formData,
      headers: {
        Accept: "text/event-stream",
      },
    });

    if (!response.ok) {
      const detail = await response.text();
      throw new Error(parseApiError(detail) || "Error enviando mensaje");
    }

    if (!response.body) {
      throw new Error("El servidor no devolvio stream");
    }

    const contentType = response.headers.get("content-type") ?? "";
    if (!contentType.includes("text/event-stream")) {
      throw new Error("Respuesta inesperada del servidor (sin SSE)");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    let hasDelta = false;
    let gotFinal = false;

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() ?? "";

      for (const block of blocks) {
        const parsed = parseSseBlock(block);
        if (!parsed) continue;

        if (parsed.event === "start") {
          patchMessage(assistantId, { text: "Procesando..." });
          continue;
        }

        if (parsed.event === "delta") {
          const delta = parseJson<StreamDelta>(parsed.data);
          const piece = delta?.content ?? "";
          if (!piece) continue;

          if (!hasDelta) {
            hasDelta = true;
            patchMessage(assistantId, { text: "" });
          }
          appendMessageText(assistantId, piece);
          continue;
        }

        if (parsed.event === "error") {
          const streamError = parseJson<StreamError>(parsed.data);
          const message = streamError?.message ?? "Error en streaming";
          throw new Error(message);
        }

        if (parsed.event === "final") {
          const payload = parseJson<ChatResponse>(parsed.data);
          if (!payload) {
            throw new Error("No se pudo leer respuesta final del stream");
          }

          gotFinal = true;
          setConversationId(payload.conversation_id);
          patchMessage(assistantId, {
            text: payload.assistant_message,
            data: payload.data,
          });
        }
      }
    }

    if (!gotFinal) {
      throw new Error("El stream finalizo sin evento final");
    }
  }

  async function loadReceiptForEdit(receiptId?: string) {
    const targetId = (receiptId ?? editReceiptId).trim();
    if (!targetId) {
      setEditorMessage("Ingresa un receipt_id para cargar.");
      return;
    }

    setEditorLoading(true);
    setEditorMessage("Cargando comprobante...");

    try {
      const response = await fetch(`${apiBase}/api/v1/receipts/${targetId}`);
      if (!response.ok) {
        throw new Error(parseApiError(await response.text()));
      }

      const data = (await response.json()) as Record<string, unknown>;
      const mapped = toEditableReceipt(data);
      setEditReceiptId(mapped.id);
      setEditableReceipt(mapped);
      setEditorMessage("Comprobante cargado. Puedes editar y guardar.");
    } catch (error) {
      setEditorMessage(`Error al cargar: ${error instanceof Error ? error.message : "desconocido"}`);
    } finally {
      setEditorLoading(false);
    }
  }

  async function saveManualCorrection() {
    if (!editableReceipt) {
      setEditorMessage("No hay comprobante cargado para editar.");
      return;
    }

    setEditorLoading(true);
    setEditorMessage("Guardando cambios...");

    const payload: Record<string, unknown> = {
      vendor_name: editableReceipt.vendor_name || null,
      receipt_number: editableReceipt.receipt_number || null,
      payment_method: editableReceipt.payment_method || null,
      status: editableReceipt.status || null,
      currency: editableReceipt.currency || null,
      issue_date: editableReceipt.issue_date || null,
    };

    if (editableReceipt.subtotal) payload.subtotal = Number(editableReceipt.subtotal);
    if (editableReceipt.tax) payload.tax = Number(editableReceipt.tax);
    if (editableReceipt.total) payload.total = Number(editableReceipt.total);

    try {
      const response = await fetch(`${apiBase}/api/v1/receipts/${editableReceipt.id}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error(parseApiError(await response.text()));
      }

      const updated = (await response.json()) as Record<string, unknown>;
      const mapped = toEditableReceipt(updated);
      setEditableReceipt(mapped);
      setEditorMessage("Correccion manual guardada correctamente.");

      appendMessage({
        id: crypto.randomUUID(),
        role: "assistant",
        text: `Correccion manual aplicada al comprobante ${mapped.id}.`,
        data: updated,
      });
    } catch (error) {
      setEditorMessage(`Error al guardar: ${error instanceof Error ? error.message : "desconocido"}`);
    } finally {
      setEditorLoading(false);
    }
  }

  function fillPrompt(prompt: string) {
    setInput(prompt);
  }

  return (
    <section className="grid flex-1 gap-4 md:grid-cols-[1fr_320px]">
      <div className="flex min-h-[560px] flex-col rounded-3xl border border-ink/10 bg-white/90 p-4 shadow-panel md:p-6">
        <div className="mb-3 flex items-center justify-between gap-3 border-b border-ink/10 pb-3">
          <div>
            <p className="text-sm font-semibold">Chat Orchestrator</p>
            <p className="font-mono text-xs text-ink/70">conversation_id: {conversationId || "(new)"}</p>
          </div>
          <span className="rounded-full bg-amber/15 px-3 py-1 font-mono text-xs text-ink">MVP + Bonus</span>
        </div>

        <div className="flex-1 space-y-3 overflow-y-auto pr-1">
          {messages.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-ink/20 bg-paper p-4 text-sm text-ink/75">
              Sube un comprobante o consulta insights. El backend persiste JSON y soporta correccion manual.
            </div>
          ) : null}

          {messages.map((msg) => {
            const messageReceiptId = extractReceiptId(msg.data);
            return (
              <article
                key={msg.id}
                className={`animate-rise rounded-2xl p-3 ${
                  msg.role === "user" ? "ml-auto max-w-[85%] bg-pine text-paper" : "mr-auto max-w-[90%] bg-paper"
                }`}
              >
                <p className="text-sm whitespace-pre-wrap">{msg.text}</p>
                {msg.data !== undefined ? (
                  <pre className="mt-3 max-h-64 overflow-auto rounded-xl bg-ink p-3 font-mono text-xs text-paper">
                    {toJsonPreview(msg.data)}
                  </pre>
                ) : null}
                {messageReceiptId ? (
                  <button
                    onClick={() => {
                      setEditReceiptId(messageReceiptId);
                      void loadReceiptForEdit(messageReceiptId);
                    }}
                    className="mt-3 rounded-lg border border-ink/20 bg-white px-2 py-1 text-xs text-ink hover:border-rust/50"
                  >
                    Editar este comprobante
                  </button>
                ) : null}
              </article>
            );
          })}
        </div>

        <form onSubmit={sendMessage} className="mt-4 space-y-3 border-t border-ink/10 pt-4">
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            rows={3}
            placeholder={placeholder}
            className="w-full resize-none rounded-2xl border border-ink/20 bg-white p-3 text-sm outline-none transition focus:border-rust"
          />

          <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
            <label className="inline-flex cursor-pointer items-center gap-2 rounded-xl border border-ink/15 bg-paper px-3 py-2 text-sm">
              <input
                type="file"
                className="hidden"
                onChange={(event) => {
                  const selected = event.target.files?.[0] ?? null;
                  setFile(selected);
                }}
              />
              <span className="font-mono text-xs">Adjuntar archivo</span>
              <span className="text-xs text-ink/70">{file ? file.name : "sin archivo"}</span>
            </label>

            <button
              type="submit"
              disabled={loading}
              className="rounded-xl bg-rust px-4 py-2 text-sm font-semibold text-paper transition hover:bg-rust/90 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loading ? "Procesando..." : "Enviar"}
            </button>
          </div>
        </form>
      </div>

      <aside className="space-y-4">
        <div className="rounded-3xl border border-ink/10 bg-white/80 p-4 shadow-panel md:p-5">
          <h2 className="text-sm font-semibold">Consultas rapidas</h2>
          <p className="mt-1 text-xs text-ink/75">Atajos para demo de insights y busquedas.</p>
          <div className="mt-3 space-y-2">
            <button
              onClick={() => fillPrompt("resumen")}
              className="w-full rounded-xl border border-ink/15 bg-paper px-3 py-2 text-left text-sm hover:border-rust/50"
            >
              resumen
            </button>
            <button
              onClick={() => fillPrompt("top proveedores")}
              className="w-full rounded-xl border border-ink/15 bg-paper px-3 py-2 text-left text-sm hover:border-rust/50"
            >
              top proveedores
            </button>
            <button
              onClick={() => fillPrompt("tendencia mensual")}
              className="w-full rounded-xl border border-ink/15 bg-paper px-3 py-2 text-left text-sm hover:border-rust/50"
            >
              tendencia mensual
            </button>
            <button
              onClick={() => fillPrompt("anomalias")}
              className="w-full rounded-xl border border-ink/15 bg-paper px-3 py-2 text-left text-sm hover:border-rust/50"
            >
              anomalias
            </button>
            <button
              onClick={() => fillPrompt("buscar comprobantes mayor a 500")}
              className="w-full rounded-xl border border-ink/15 bg-paper px-3 py-2 text-left text-sm hover:border-rust/50"
            >
              buscar comprobantes mayor a 500
            </button>
          </div>
        </div>

        <div className="rounded-3xl border border-ink/10 bg-white/80 p-4 shadow-panel md:p-5">
          <h2 className="text-sm font-semibold">Correccion manual</h2>
          <p className="mt-1 text-xs text-ink/75">Carga un comprobante por ID y edita campos clave.</p>

          <div className="mt-3 space-y-2">
            <input
              value={editReceiptId}
              onChange={(event) => setEditReceiptId(event.target.value)}
              placeholder="receipt_id"
              className="w-full rounded-lg border border-ink/20 bg-white px-3 py-2 text-xs font-mono outline-none focus:border-rust"
            />
            <button
              onClick={() => void loadReceiptForEdit()}
              disabled={editorLoading}
              className="w-full rounded-lg border border-ink/20 bg-paper px-3 py-2 text-xs hover:border-rust/50 disabled:opacity-60"
            >
              {editorLoading ? "Cargando..." : "Cargar"}
            </button>
          </div>

          {editableReceipt ? (
            <div className="mt-3 space-y-2">
              <input
                value={editableReceipt.vendor_name}
                onChange={(event) => setEditableReceipt((prev) => (prev ? { ...prev, vendor_name: event.target.value } : prev))}
                placeholder="vendor_name"
                className="w-full rounded-lg border border-ink/20 bg-white px-2 py-2 text-xs outline-none focus:border-rust"
              />
              <input
                value={editableReceipt.receipt_number}
                onChange={(event) =>
                  setEditableReceipt((prev) => (prev ? { ...prev, receipt_number: event.target.value } : prev))
                }
                placeholder="receipt_number"
                className="w-full rounded-lg border border-ink/20 bg-white px-2 py-2 text-xs outline-none focus:border-rust"
              />
              <div className="grid grid-cols-2 gap-2">
                <input
                  value={editableReceipt.subtotal}
                  onChange={(event) => setEditableReceipt((prev) => (prev ? { ...prev, subtotal: event.target.value } : prev))}
                  placeholder="subtotal"
                  className="w-full rounded-lg border border-ink/20 bg-white px-2 py-2 text-xs outline-none focus:border-rust"
                />
                <input
                  value={editableReceipt.tax}
                  onChange={(event) => setEditableReceipt((prev) => (prev ? { ...prev, tax: event.target.value } : prev))}
                  placeholder="tax"
                  className="w-full rounded-lg border border-ink/20 bg-white px-2 py-2 text-xs outline-none focus:border-rust"
                />
              </div>
              <input
                value={editableReceipt.total}
                onChange={(event) => setEditableReceipt((prev) => (prev ? { ...prev, total: event.target.value } : prev))}
                placeholder="total"
                className="w-full rounded-lg border border-ink/20 bg-white px-2 py-2 text-xs outline-none focus:border-rust"
              />
              <div className="grid grid-cols-2 gap-2">
                <input
                  value={editableReceipt.currency}
                  onChange={(event) => setEditableReceipt((prev) => (prev ? { ...prev, currency: event.target.value } : prev))}
                  placeholder="currency"
                  className="w-full rounded-lg border border-ink/20 bg-white px-2 py-2 text-xs outline-none focus:border-rust"
                />
                <input
                  value={editableReceipt.payment_method}
                  onChange={(event) =>
                    setEditableReceipt((prev) => (prev ? { ...prev, payment_method: event.target.value } : prev))
                  }
                  placeholder="payment_method"
                  className="w-full rounded-lg border border-ink/20 bg-white px-2 py-2 text-xs outline-none focus:border-rust"
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <input
                  value={editableReceipt.issue_date}
                  onChange={(event) => setEditableReceipt((prev) => (prev ? { ...prev, issue_date: event.target.value } : prev))}
                  placeholder="issue_date YYYY-MM-DD"
                  className="w-full rounded-lg border border-ink/20 bg-white px-2 py-2 text-xs outline-none focus:border-rust"
                />
                <input
                  value={editableReceipt.status}
                  onChange={(event) => setEditableReceipt((prev) => (prev ? { ...prev, status: event.target.value } : prev))}
                  placeholder="status"
                  className="w-full rounded-lg border border-ink/20 bg-white px-2 py-2 text-xs outline-none focus:border-rust"
                />
              </div>

              <button
                onClick={() => void saveManualCorrection()}
                disabled={editorLoading}
                className="w-full rounded-lg bg-rust px-3 py-2 text-xs font-semibold text-paper disabled:opacity-60"
              >
                {editorLoading ? "Guardando..." : "Guardar correccion"}
              </button>
            </div>
          ) : null}

          <p className="mt-3 text-xs text-ink/70">{editorMessage || "Sin acciones en editor."}</p>
        </div>
      </aside>
    </section>
  );
}
