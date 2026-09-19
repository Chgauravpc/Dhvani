"""aiohttp signaling endpoint: exchanges SDP offer/answer with the browser."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription

WEB_DIR = Path(__file__).resolve().parents[3] / "web"

OnPeerConnected = Callable[[RTCPeerConnection], Awaitable[None]]


def create_app(on_peer_connected: OnPeerConnected, web_dir: Path = WEB_DIR) -> web.Application:
    """Build the aiohttp app.

    `on_peer_connected` is awaited with each new `RTCPeerConnection` right
    after creation, so the caller can attach track handlers and add its
    outbound track before the SDP answer is sent.
    """
    peer_connections: set[RTCPeerConnection] = set()

    async def offer(request: web.Request) -> web.Response:
        params = await request.json()
        pc = RTCPeerConnection()
        peer_connections.add(pc)

        @pc.on("connectionstatechange")
        async def on_state_change() -> None:
            if pc.connectionState in ("failed", "closed"):
                peer_connections.discard(pc)
                await pc.close()

        await on_peer_connected(pc)

        offer_desc = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
        await pc.setRemoteDescription(offer_desc)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        local = pc.localDescription
        assert local is not None
        return web.json_response({"sdp": local.sdp, "type": local.type})

    async def index(request: web.Request) -> web.FileResponse:
        return web.FileResponse(web_dir / "index.html")

    async def on_shutdown(app: web.Application) -> None:
        await asyncio.gather(*(pc.close() for pc in peer_connections))
        peer_connections.clear()

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_post("/offer", offer)
    app.router.add_static("/static/", web_dir)
    app.on_shutdown.append(on_shutdown)
    return app
