from fastapi import FastAPI

from app.api.rpc import router as rpc_router

app = FastAPI(title="Receipt Analyzer Agent", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(rpc_router)
