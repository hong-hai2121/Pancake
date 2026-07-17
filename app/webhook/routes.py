"""Nhận GET (verify) + POST (tin nhắn) từ Facebook."""

from fastapi import APIRouter, HTTPException, Request, Response

from app.config import settings
from app.webhook.handler import handle_event

router = APIRouter()


@router.get("/webhook")
async def verify(request: Request):
    """Facebook gọi GET một lần để xác minh webhook."""
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == settings.fb_verify_token:
        return Response(content=challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhook")
async def receive(request: Request):
    """Facebook gọi POST mỗi khi có sự kiện tin nhắn mới."""
    body = await request.json()
    if body.get("object") != "page":
        return {"status": "ignored"}

    for entry in body.get("entry", []):
        for event in entry.get("messaging", []):
            await handle_event(event)

    # Luôn trả 200 nhanh để Facebook không gửi lại.
    return {"status": "ok"}
