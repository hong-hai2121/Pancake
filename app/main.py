"""Khởi động server FastAPI và đăng ký route webhook."""

import uvicorn
from fastapi import FastAPI

from app.pancake.routes import router as pancake_router
from app.webhook.routes import router as webhook_router

app = FastAPI(title="FB Sales Bot")
app.include_router(webhook_router)
app.include_router(pancake_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
