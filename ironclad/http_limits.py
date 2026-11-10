"""Bound HTTP request bodies even when Transfer-Encoding is chunked."""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class BodyLimit:
    def __init__(self, app: ASGIApp, max_bytes: int = 1000000):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        total = 0
        packets: list[Message] = []
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            total += len(message.get("body", b""))
            if total > self.max_bytes:
                await JSONResponse(
                    {"detail": "Request body exceeds one megabyte"}, status_code=413
                )(scope, receive, send)
                return
            packets.append(message)
            if not message.get("more_body", False):
                break

        async def replay() -> Message:
            return packets.pop(0) if packets else await receive()

        await self.app(scope, replay, send)
