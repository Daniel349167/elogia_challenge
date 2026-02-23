# Developer Challenge - IA para Analisis de Comprobantes

Solucion monorepo end-to-end para analisis de comprobantes con chat, persistencia y explotacion de datos.

## 1) Objetivo del reto y cobertura

### Requisitos minimos
- UI tipo chat: **implementado** (`apps/frontend`)
- Envio de texto y archivos: **implementado** (`POST /api/v1/chat/message`)
- Analisis via Agent (real o simulado): **implementado** (Agent mock JSON-RPC)
- JSON estructurado: **implementado** (contratos + validacion)
- Persistencia en BD: **implementado** (PostgreSQL)
- Consultas basicas desde chat: **implementado** (comprobante, buscar, resumen)

### Bonus
- Streaming de respuestas: **implementado** (SSE `POST /api/v1/chat/message/stream`)
- Validaciones adicionales: **implementado** (tamano/mime/ext + validaciones de negocio)
- Correccion manual desde UI: **implementado** (editor con `PATCH /api/v1/receipts/{id}`)
- Insights mas elaborados: **implementado** (`vendors`, `trend`, `anomalies`)
- Manejo de errores avanzado: **implementado** (errores estructurados + reintentos al Agent)

## 2) Arquitectura

```txt
Frontend (Next.js)
  -> Orchestrator API (FastAPI)
      -> Agent Analyzer (FastAPI, JSON-RPC 2.0)
      -> PostgreSQL
```

### Componentes
- `apps/frontend`: chat UI + streaming + editor manual de comprobantes.
- `apps/orchestrator`: orquesta conversacion, persistencia, consultas, insights, validaciones.
- `apps/agent-analyzer`: Agent de extraccion (mock/reglas) via JSON-RPC.
- `packages/contracts`: esquemas JSON de contratos.
- `infra/docker-compose.yml`: stack completo local.

## 3) Stack tecnico

- Frontend: `Next.js 16`, `TypeScript`, `Tailwind`
- Backend orchestrator: `FastAPI`, `SQLAlchemy`, `Pydantic`
- Agent: `FastAPI` (mock)
- Base de datos: `PostgreSQL 16`
- Pruebas E2E: `pytest + requests`
- Contenedores: `Docker Compose`

## 4) Estructura de carpetas

```txt
apps/
  frontend/
  orchestrator/
    app/
      api/
      models/
      schemas/
      services/
    tests/e2e/
  agent-analyzer/
packages/
  contracts/
infra/
  docker-compose.yml
samples/
  comprobante-demo.txt
```

## 5) Endpoints

### Orchestrator (`http://localhost:8000`)
- `GET /health`
- `POST /api/v1/chat/message` (multipart)
- `POST /api/v1/chat/message/stream` (SSE: `start`, `delta`, `final`, `error`)
- `GET /api/v1/chat/conversations/{conversation_id}/messages`
- `GET /api/v1/receipts/{receipt_id}`
- `GET /api/v1/receipts?vendor=&min_total=&max_total=&from=&to=`
- `PATCH /api/v1/receipts/{receipt_id}`
- `GET /api/v1/insights/summary`
- `GET /api/v1/insights/vendors?limit=5`
- `GET /api/v1/insights/trend?group_by=month|day`
- `GET /api/v1/insights/anomalies?factor=1.8&limit=10`

### Agent Analyzer (`http://localhost:8100`)
- `GET /health`
- `POST /rpc` metodo `analyze_receipt`

## 6) Modelo de datos (tablas)

- `conversations`
- `messages`
- `attachments`
- `receipts`
- `receipt_items`
- `extraction_runs`

Estados relevantes de `receipts.status`:
- `processed`
- `processed_with_warnings`
- `duplicate`
- `duplicate_candidate`
- `manually_corrected`
- `error`

## 7) Contratos JSON

- `packages/contracts/agent-jsonrpc.schema.json`
- `packages/contracts/receipt.schema.json`
- `packages/contracts/chat.schema.json`

Ejemplo request JSON-RPC:
```json
{
  "jsonrpc": "2.0",
  "id": "req-1",
  "method": "analyze_receipt",
  "params": {
    "filename": "comprobante.pdf",
    "mime_type": "application/pdf",
    "content_base64": "...",
    "text_hint": "total 120.50"
  }
}
```

## 8) Ejecucion

### Requisitos
- Docker Desktop activo
- Docker Compose
- Python 3.12+ (solo si ejecutaras pruebas E2E desde host)

### Levantar todo
```bash
# opcional: copiar .env si quieres sobreescribir valores locales
cp .env.example .env
# en PowerShell (Windows), equivalente:
# Copy-Item .env.example .env
docker compose -f infra/docker-compose.yml up --build -d
```

### URLs
- Frontend: `http://localhost:3000`
- Orchestrator docs: `http://localhost:8000/docs`
- Agent docs: `http://localhost:8100/docs`

### Detener
```bash
docker compose -f infra/docker-compose.yml down
```

## 9) Variables de entorno importantes

En `.env.example`:
- `MAX_UPLOAD_BYTES`
- `ALLOWED_MIME_TYPES`
- `ALLOWED_EXTENSIONS`
- `AGENT_TIMEOUT_SECONDS`
- `AGENT_RETRIES`
- `AGENT_BACKOFF_SECONDS`

## 10) Pruebas

### Pruebas E2E
```bash
pip install -r apps/orchestrator/requirements-test.txt
python -m pytest apps/orchestrator/tests/e2e -q
```

Cobertura E2E actual:
- upload + extraccion + persistencia
- consulta por ID y por criterio
- deteccion de duplicados por hash
- streaming SSE con evento `final`
- validacion de archivo bloqueando extension no permitida
- correccion manual via `PATCH`
- insights avanzados (`vendors`, `trend`, `anomalies`)

## 11) Flujo de demo recomendado

1. Abrir `http://localhost:3000`
2. Subir `samples/comprobante-demo.txt` con mensaje opcional
3. Ver respuesta en streaming y JSON persistido
4. Subir el mismo archivo otra vez (debe marcar `duplicate`)
5. Probar consultas en chat:
   - `resumen`
   - `top proveedores`
   - `tendencia mensual`
   - `anomalias`
6. Tomar un `receipt_id`, cargarlo en "Correccion manual", editar y guardar
7. Validar cambios con `GET /api/v1/receipts/{id}`
8. Reiniciar backend y confirmar persistencia:
   - `docker compose -f infra/docker-compose.yml restart orchestrator`

## 12) Decisiones tecnicas y tradeoffs

- Monorepo para acelerar integracion y entrega en 3 dias.
- Agent separado por HTTP para simular arquitectura real desacoplada.
- JSON-RPC 2.0 para contrato explicito y trazable con proveedores de IA.
- Mock de extraccion para garantizar flujo completo sin bloquearse por OCR/LLM.
- SSE para UX de respuesta progresiva en chat.
- Dedupe en 2 capas:
  - exacto por hash (`duplicate`)
  - candidato por regla de negocio (`duplicate_candidate`)
- Manejo de errores robusto:
  - reintentos y backoff al Agent
  - errores estructurados en API
  - registro de recepciones fallidas con estado `error`

## 13) Limitaciones actuales

- El Agent es mock (no OCR/LLM productivo).
- No hay autenticacion/roles multiusuario.
- No hay versionado de correcciones campo por campo.
- `create_all` en startup (en produccion se recomienda migraciones con Alembic).

## 14) Como evolucionarlo a LLM real

1. Reemplazar `mock_analyzer` por proveedor OCR+LLM (Vision API).
2. Mantener contrato JSON-RPC (sin romper Orchestrator).
3. Agregar fallback multi-proveedor y score por campo.
4. Registrar prompts/versiones de modelo por `extraction_run`.
5. Agregar validacion humana asistida por confidence por campo.

## 15) Estado final para evaluacion

- Flujo end-to-end: **OK**
- Arquitectura desacoplada: **OK**
- Bonus: **implementados**
- Pruebas E2E: **OK**
- Docker/build: **OK**
