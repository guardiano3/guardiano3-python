"""WebSocket live-session helper for real-time audio analysis."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional


@dataclass
class LiveFrame:
    """A parsed frame from the decision stream."""

    type: str
    raw: dict
    session_id: Optional[str] = None
    risk_level: Optional[str] = None
    risk_score: Optional[float] = None
    fraud_category: Optional[str] = None
    verification_status: Optional[str] = None
    transcript: Optional[str] = None
    explanation: Optional[list] = None
    dropped_chunks: Optional[int] = None
    #: `degraded` frames: a stretch of the call was not transcribed, so no
    #: decision covers it. Do not treat a quiet stream as a safe call.
    degraded_reason: Optional[str] = None
    unheard_seconds: Optional[float] = None
    total_unheard_seconds: Optional[float] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


def _parse_frame(data: dict) -> LiveFrame:
    frame_type = data.get("type", "unknown")
    frame = LiveFrame(type=frame_type, raw=data)
    frame.session_id = data.get("sessionId")

    if frame_type in ("decision", "decisionUpdate"):
        frame.risk_level = data.get("riskLevel")
        frame.risk_score = data.get("riskScore")
        frame.fraud_category = data.get("fraudCategory")
        frame.verification_status = data.get("verificationStatus")
        frame.transcript = data.get("transcript")
        frame.explanation = data.get("explanation")
    elif frame_type == "lagging":
        frame.dropped_chunks = data.get("droppedChunks")
    elif frame_type == "degraded":
        frame.degraded_reason = data.get("reason")
        frame.unheard_seconds = data.get("unheardSeconds")
        frame.total_unheard_seconds = data.get("totalUnheardSeconds")
    elif frame_type == "error":
        err = data.get("error", {})
        frame.error_code = err.get("code")
        frame.error_message = err.get("message")

    return frame


def _require_websockets() -> Any:
    try:
        import websockets
        return websockets
    except ImportError as exc:
        raise ImportError(
            "The 'websockets' package is required for LiveSession. "
            "Install it with: pip install 'guardiano3[live]'"
        ) from exc


class LiveSession:
    """Async context manager for a live audio analysis session.

    Opens two WebSocket connections: one for sending audio (binary uplink)
    and one for receiving decision frames (JSON downlink). Use as an async
    iterator to receive typed frames.

        async with LiveSession(base_url=url, credential=token, session_id=sid) as session:
            await session.send_audio(pcm_bytes)

            async for frame in session:
                print(frame.type, frame.risk_level, frame.risk_score)
    """

    def __init__(
        self,
        *,
        base_url: str,
        credential: str,
        session_id: str,
    ) -> None:
        self._ws_mod = _require_websockets()
        ws_base = base_url.rstrip("/").replace("http://", "ws://").replace("https://", "wss://")
        self._audio_url = f"{ws_base}/v1/sessions/{session_id}/audio"
        self._stream_url = f"{ws_base}/v1/sessions/{session_id}/stream"
        self._credential = credential
        self._audio_ws: Any = None
        self._stream_ws: Any = None
        self._closed = False

    async def __aenter__(self) -> "LiveSession":
        auth_msg = json.dumps({"token": self._credential})

        self._audio_ws = await self._ws_mod.connect(self._audio_url)
        await self._audio_ws.send(auth_msg)

        self._stream_ws = await self._ws_mod.connect(self._stream_url)
        await self._stream_ws.send(auth_msg)

        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def send_audio(self, pcm: bytes) -> None:
        if self._audio_ws is None:
            raise RuntimeError("LiveSession is not connected.")
        await self._audio_ws.send(pcm)

    async def close(self) -> None:
        self._closed = True
        if self._audio_ws:
            await self._audio_ws.close()
            self._audio_ws = None
        if self._stream_ws:
            await self._stream_ws.close()
            self._stream_ws = None

    def __aiter__(self) -> AsyncIterator[LiveFrame]:
        return self._iter_frames()

    async def _iter_frames(self) -> AsyncIterator[LiveFrame]:
        if self._stream_ws is None:
            raise RuntimeError("LiveSession is not connected.")
        try:
            async for message in self._stream_ws:
                if isinstance(message, bytes):
                    continue
                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    continue
                yield _parse_frame(data)
        except self._ws_mod.ConnectionClosed:
            return
