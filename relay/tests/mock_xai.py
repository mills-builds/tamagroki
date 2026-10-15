"""Mock xAI realtime voice server (subset of the protocol the relay uses).

Behaviour: energy-based "server VAD" on appended PCM; after each user utterance it
replies with ~1.5 s of tone audio + transcript. A client response.create (e.g. with
one-off instructions) also produces a short spoken reply. Barge-in: user speech during a response emits speech_started and stops
the response once response.cancel arrives.
Run standalone: python -m tests.mock_xai --port 9100
"""
from __future__ import annotations

import argparse
import array
import asyncio
import base64
import json
import math

from aiohttp import web

RATE_OUT = 24000


def tone(seconds: float, freq: float = 440.0, amp: int = 9000) -> bytes:
    n = int(RATE_OUT * seconds)
    return array.array("h", (int(amp * math.sin(2 * math.pi * freq * i / RATE_OUT)) for i in range(n))).tobytes()


class MockXai:
    def __init__(self) -> None:
        self.events: list[dict] = []          # everything clients sent
        self.sessions = 0
        self.auth_headers: list[str] = []
        self.transcript = "mock user speech"   # what the "user" is heard saying

    def app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/v1/realtime", self.handle)
        return app

    async def handle(self, request: web.Request) -> web.WebSocketResponse:
        self.auth_headers.append(request.headers.get("Authorization", ""))
        ws = web.WebSocketResponse(max_msg_size=0)
        await ws.prepare(request)
        self.sessions += 1
        st = {"in_speech": False, "quiet_ms": 0, "peak": 0, "resp": None, "cancelled": False, "rate": 24000}

        async def send(obj):
            if not ws.closed:
                await ws.send_str(json.dumps(obj))

        async def respond(text: str = "Hello from mock Grok.", seconds: float = 1.5):
            await send({"type": "response.created", "response": {"id": "r"}})
            pcm = tone(seconds)
            chunk = RATE_OUT * 2 // 10  # 100 ms
            for i in range(0, len(pcm), chunk):
                if st["cancelled"]:
                    await send({"type": "response.done", "response": {"status": "cancelled"}})
                    return
                await send({"type": "response.output_audio.delta", "delta": base64.b64encode(pcm[i:i + chunk]).decode()})
                await asyncio.sleep(0.05)  # faster than real time, like the real API
            await send({"type": "response.output_audio_transcript.done", "transcript": text})
            await send({"type": "response.done", "response": {"status": "completed"}})

        def start(**kw):
            st["cancelled"] = False
            st["resp"] = asyncio.create_task(respond(**kw))

        async for msg in ws:
            ev = json.loads(msg.data)
            self.events.append(ev)
            t = ev.get("type")
            if t == "session.update":
                s = ev["session"]
                st["rate"] = s.get("audio", {}).get("input", {}).get("format", {}).get("rate", 24000)
                await send({"type": "session.updated", "session": s})
            elif t == "input_audio_buffer.append":
                pcm = array.array("h", base64.b64decode(ev["audio"]))
                ms = len(pcm) * 1000 // st["rate"]
                peak = max((abs(x) for x in pcm), default=0)
                if peak > 2000:
                    st["peak"] = max(st["peak"], peak)
                    st["quiet_ms"] = 0
                    if not st["in_speech"]:
                        st["in_speech"] = True
                        await send({"type": "input_audio_buffer.speech_started"})
                elif st["in_speech"]:
                    st["quiet_ms"] += ms
                    if st["quiet_ms"] >= 300:
                        st["in_speech"] = False
                        await send({"type": "input_audio_buffer.speech_stopped"})
                        await send({"type": "conversation.item.input_audio_transcription.completed",
                                    "transcript": self.transcript})
                        st["peak"] = 0
                        start()
            elif t == "response.cancel":
                st["cancelled"] = True
            elif t == "response.create":
                if st["resp"] is not None and not st["resp"].done():
                    st["cancelled"] = True
                    await st["resp"]
                start(text="Bye for now!", seconds=0.6)
        return ws


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9100)
    a = ap.parse_args()
    web.run_app(MockXai().app(), port=a.port)
