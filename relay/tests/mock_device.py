"""Mock Tamagroki cube: speaks the xiaozhi websocket protocol like the firmware does.

Library use (tests) or CLI against a running relay:
  python -m tests.mock_device --relay http://127.0.0.1:8765 --wav question.wav --out reply.wav
(--wav must be 16 kHz mono 16-bit; without it a synthetic 'utterance' is sent.)
"""
from __future__ import annotations

import argparse
import array
import asyncio
import json
import math
import sys
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tamagroki_relay.opus import Decoder, Encoder  # noqa: E402

IN_RATE = 16000
FRAME = IN_RATE * 60 // 1000  # 960 samples


def synth(seconds: float, amp: int, freq: float = 220.0) -> bytes:
    n = int(IN_RATE * seconds)
    return array.array("h", (int(amp * math.sin(2 * math.pi * freq * i / IN_RATE)) for i in range(n))).tobytes()


@dataclass
class DeviceLog:
    json_in: list[dict] = field(default_factory=list)
    audio_frames: int = 0
    pcm_out: bytearray = field(default_factory=bytearray)
    timeline: list[tuple[float, str]] = field(default_factory=list)
    hello: dict = field(default_factory=dict)


class MockDevice:
    def __init__(self, relay_http: str) -> None:
        self.relay = relay_http.rstrip("/")
        self.log = DeviceLog()
        self.enc = Encoder(IN_RATE)
        self.dec = Decoder(24000)
        self.t0 = time.monotonic()
        self.ws: aiohttp.ClientWebSocketResponse | None = None
        self.state = "idle"  # mirrors firmware DeviceState (idle/listening/speaking)

    def mark(self, what: str) -> None:
        self.log.timeline.append((round(time.monotonic() - self.t0, 3), what))

    async def connect(self, session: aiohttp.ClientSession) -> None:
        async with session.post(self.relay + "/xiaozhi/ota/", json={"application": {"version": "2.0.0"}}) as r:
            ota = await r.json()
        url = ota["websocket"]["url"]
        self.ws = await session.ws_connect(url, headers={"Authorization": "Bearer " + ota["websocket"]["token"],
                                                         "Protocol-Version": "1", "Device-Id": "mock"})
        await self.ws.send_str(json.dumps({"type": "hello", "version": 1, "transport": "websocket",
                                           "features": {"mcp": True},
                                           "audio_params": {"format": "opus", "sample_rate": 16000, "channels": 1, "frame_duration": 60}}))
        self.reader = asyncio.create_task(self._read())
        for _ in range(100):
            if self.log.hello:
                break
            await asyncio.sleep(0.02)
        assert self.log.hello, "no server hello"

    async def _read(self) -> None:
        assert self.ws
        async for msg in self.ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                m = json.loads(msg.data)
                if m.get("type") == "hello":
                    self.log.hello = m
                    continue
                self.log.json_in.append(m)
                if m.get("type") == "tts":
                    self.mark("tts:" + m["state"])
                    if m["state"] == "start":
                        self.state = "speaking"
                    elif m["state"] == "stop":
                        self.state = "listening"
                elif m.get("type") == "llm":
                    self.mark("face:" + m.get("emotion", ""))
            elif msg.type == aiohttp.WSMsgType.BINARY:
                if self.state == "speaking":  # firmware only plays audio while Speaking
                    self.log.audio_frames += 1
                    self.log.pcm_out.extend(self.dec.decode(msg.data))
            else:
                break
        self.mark("closed")

    async def listen_start(self, mode: str = "realtime") -> None:
        await self.ws.send_str(json.dumps({"type": "listen", "state": "detect", "text": "Yo Grok"}))
        await self.ws.send_str(json.dumps({"type": "listen", "state": "start", "mode": mode}))
        self.state = "listening"

    async def stream(self, pcm: bytes, realtime: bool = True) -> None:
        for i in range(0, len(pcm) - FRAME * 2 + 1, FRAME * 2):
            await self.ws.send_bytes(self.enc.encode(pcm[i:i + FRAME * 2]))
            await asyncio.sleep(0.06 if realtime else 0)

    async def wait_for(self, pred, timeout: float = 10.0) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if pred():
                return True
            await asyncio.sleep(0.02)
        return False

    def tts_states(self) -> list[str]:
        return [m["state"] for m in self.log.json_in if m.get("type") == "tts"]


async def _cli() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--relay", default="http://127.0.0.1:8765")
    ap.add_argument("--wav", help="16 kHz mono s16 wav to speak")
    ap.add_argument("--out", default="reply.wav")
    ap.add_argument("--wait", type=float, default=15)
    a = ap.parse_args()
    if a.wav:
        with wave.open(a.wav) as w:
            assert w.getframerate() == 16000 and w.getnchannels() == 1, "need 16 kHz mono"
            pcm = w.readframes(w.getnframes())
    else:
        pcm = synth(1.5, 6000)
    pcm += bytes(IN_RATE * 2)  # 1 s of silence so server VAD ends the turn
    async with aiohttp.ClientSession() as s:
        d = MockDevice(a.relay)
        await d.connect(s)
        await d.listen_start()
        await d.stream(pcm)
        silence = bytes(FRAME * 2)
        end = time.monotonic() + a.wait
        while time.monotonic() < end:  # keep the mic open like the real device
            await d.ws.send_bytes(d.enc.encode(silence))
            await asyncio.sleep(0.06)
        await d.ws.close()
    with wave.open(a.out, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(bytes(d.log.pcm_out))
    for t, what in d.log.timeline:
        print(f"{t:7.3f}s {what}")
    print(f"received {d.log.audio_frames} opus frames -> {a.out}")


if __name__ == "__main__":
    asyncio.run(_cli())
