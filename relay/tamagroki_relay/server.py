"""aiohttp server: xiaozhi OTA endpoint + xiaozhi websocket protocol <-> xAI realtime voice."""
from __future__ import annotations

import asyncio
import array
import base64
import os
import re
import json
import logging
import socket
import time
import uuid
from typing import Any, Optional

import aiohttp
from aiohttp import web

from .config import Config
from .opus import Decoder, Encoder

# "Bye Grok" (plus common mis-transcriptions) ends the conversation
BYE_RE = re.compile(r"\b(bye|by|buy|goodbye)[\s,.!-]*(grok|grog|grock|rock|groc)\b", re.I)

log = logging.getLogger("tamagroki.relay")

DEVICE_IN_RATE = 16000     # device -> relay opus (xiaozhi always sends 16 kHz)
DEVICE_OUT_RATE = 24000    # relay -> device opus (board codec runs at 24 kHz)
FRAME_MS = 60
OUT_FRAME_BYTES = DEVICE_OUT_RATE * FRAME_MS // 1000 * 2
PLAYBACK_LEAD_S = 0.36     # how far ahead of real time we let audio run into the device queue

def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class DeviceSession:
    """One connected cube. Owns the xAI realtime websocket for the conversation."""

    def __init__(self, cfg: Config, ws: web.WebSocketResponse, http: aiohttp.ClientSession) -> None:
        self.cfg, self.dev, self.http = cfg, ws, http
        self.id = uuid.uuid4().hex[:12]
        self.xai: Optional[aiohttp.ClientWebSocketResponse] = None
        self.dec = Decoder(DEVICE_IN_RATE)
        self.enc = Encoder(DEVICE_OUT_RATE)
        self.listening = False
        self.listen_mode = "realtime"
        self.speaking = False           # we told the device tts start
        self.out_pcm = bytearray()      # pending model audio not yet encoded
        self.out_q: asyncio.Queue[Optional[bytes]] = asyncio.Queue()
        self.response_done = True
        self.last_activity = time.monotonic()
        self.closed = False
        self.stats = {"mic_frames": 0, "spk_frames": 0, "barge_ins": 0}
        self._tasks: list[asyncio.Task] = []
        self.user_speaking_since: Optional[float] = None
        self.bye_pending = False
        self.in_gain = float(os.getenv("RELAY_IN_GAIN", "3.0"))

    # ---------------- device side -----------------
    async def send_dev_json(self, obj: dict[str, Any]) -> None:
        if self.dev.closed:
            return
        obj.setdefault("session_id", self.id)
        await self.dev.send_str(json.dumps(obj))

    async def face(self, emotion: str) -> None:
        """Face-state event understood by the firmware (llm emotion)."""
        await self.send_dev_json({"type": "llm", "emotion": emotion, "text": ""})

    async def run(self) -> None:
        try:
            async for msg in self.dev:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self.on_dev_text(json.loads(msg.data))
                elif msg.type == aiohttp.WSMsgType.BINARY:
                    await self.on_dev_audio(msg.data)
                elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSE):
                    break
        finally:
            await self.close()

    async def on_dev_text(self, m: dict[str, Any]) -> None:
        t = m.get("type")
        log.debug("[%s] dev -> %s", self.id, m)
        if t == "hello":
            await self.send_dev_json({
                "type": "hello", "transport": "websocket", "session_id": self.id,
                "audio_params": {"format": "opus", "sample_rate": DEVICE_OUT_RATE,
                                 "channels": 1, "frame_duration": FRAME_MS}})
            vol = os.getenv("RELAY_DEVICE_VOLUME", "80")
            if vol:
                await self.send_dev_json({"type": "mcp", "payload": {"jsonrpc": "2.0", "id": 9001,
                    "method": "tools/call", "params": {"name": "self.audio_speaker.set_volume",
                    "arguments": {"volume": int(vol)}}}})
                log.info("[%s] asked device to set volume %s", self.id, vol)
            await self.ensure_xai()
        elif t == "listen":
            state = m.get("state")
            if state == "start":
                self.listening = True
                self.listen_mode = m.get("mode", "realtime")
                self.last_activity = time.monotonic()
                await self.ensure_xai()
                if m.get("mode") == "manual":
                    await self.xai_send({"type": "input_audio_buffer.clear"})
            elif state == "stop":
                self.listening = False
                if self.listen_mode == "manual":
                    # push-to-talk release: commit what we have and ask for a reply
                    await self.xai_send({"type": "input_audio_buffer.commit"})
                    await self.xai_send({"type": "response.create"})
            elif state == "detect":
                log.info("[%s] wake word: %s", self.id, m.get("text"))
                self.last_activity = time.monotonic()
                if self.cfg.greet_on_wake:
                    await self.ensure_xai()
                    await self.xai_send({"type": "response.create", "response": {
                        "instructions": "The user just woke you with your name. Greet them in two or three words."}})
        elif t == "abort":
            log.info("[%s] device abort (%s)", self.id, m.get("reason"))
            await self.interrupt(reason="device-abort")
        elif t == "mcp":
            pass  # device MCP replies (e.g. to set_volume) are ignored

    async def on_dev_audio(self, data: bytes) -> None:
        if not self.listening or self.xai is None:
            return
        try:
            pcm = self.dec.decode(data)
        except Exception as e:  # noqa: BLE001
            log.warning("bad opus frame from device: %s", e)
            return
        self.stats["mic_frames"] += 1
        a = array.array("h", pcm)
        # boost the quiet cube mic, but not while we are playing a reply: amplified speaker
        # echo would trip xAI's VAD and barge in on ourselves
        if self.in_gain != 1.0 and a and not self.speaking:
            g = self.in_gain
            for i, v in enumerate(a):
                v = int(v * g)
                a[i] = 32767 if v > 32767 else (-32768 if v < -32768 else v)
            pcm = a.tobytes()
        await self.xai_send({"type": "input_audio_buffer.append", "audio": base64.b64encode(pcm).decode()})

    # ---------------- xAI side -----------------
    async def ensure_xai(self) -> None:
        if self.xai is not None and not self.xai.closed:
            return
        headers = {}
        if self.cfg.xai_api_key:
            headers["Authorization"] = f"Bearer {self.cfg.xai_api_key}"
        else:
            log.error("XAI_API_KEY is not set (export XAI_API_KEY=... or set it in relay/.env); connecting anyway")
        self.xai = await self.http.ws_connect(self.cfg.xai_url, headers=headers, heartbeat=20, max_msg_size=0)
        tools: list[dict[str, Any]] = [{"type": "web_search"}] if self.cfg.enable_web_search else []
        await self.xai_send({"type": "session.update", "session": {
            "voice": self.cfg.xai_voice,
            "instructions": self.cfg.instructions(),
            "turn_detection": {"type": "server_vad", "silence_duration_ms": int(os.getenv("RELAY_VAD_SILENCE_MS", "900"))},
            "audio": {
                "input": {"format": {"type": "audio/pcm", "rate": DEVICE_IN_RATE}},
                "output": {"format": {"type": "audio/pcm", "rate": DEVICE_OUT_RATE}},
            },
            "tools": tools,
        }})
        self._tasks.append(asyncio.create_task(self.xai_reader()))
        self._tasks.append(asyncio.create_task(self.playback_pump()))
        self._tasks.append(asyncio.create_task(self.idle_watchdog()))
        log.info("[%s] xAI realtime session opened", self.id)

    async def xai_send(self, obj: dict[str, Any]) -> None:
        if self.xai is not None and not self.xai.closed:
            await self.xai.send_str(json.dumps(obj))

    async def xai_reader(self) -> None:
        assert self.xai is not None
        async for msg in self.xai:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    await self.on_xai_event(json.loads(msg.data))
                except Exception:  # noqa: BLE001
                    log.exception("error handling xAI event")
            elif msg.type == aiohttp.WSMsgType.BINARY:
                await self.on_model_audio(msg.data)
            else:
                log.warning("[%s] xAI ws message %s: %s", self.id, msg.type, msg.data)
                break
        log.info("[%s] xAI websocket closed (code=%s, exc=%s)", self.id, self.xai.close_code, self.xai.exception())
        if not self.closed:
            await self.send_dev_json({"type": "tts", "state": "stop"})
            await self.dev.close()

    async def on_xai_event(self, ev: dict[str, Any]) -> None:
        t = ev.get("type", "")
        if not t.endswith(".delta"):
            log.debug("[%s] xAI <- %s", self.id, t)
        if t in ("response.output_audio.delta", "response.audio.delta"):
            await self.on_model_audio(base64.b64decode(ev.get("delta", "")))
        elif t == "input_audio_buffer.speech_started":
            self.last_activity = time.monotonic()
            self.user_speaking_since = time.monotonic()
            if self.speaking or not self.out_q.empty() or self.out_pcm:
                self.stats["barge_ins"] += 1
                log.info("[%s] barge-in", self.id)
                await self.interrupt(reason="barge-in", cancel_model=True)
            await self.face("listening")
        elif t == "input_audio_buffer.speech_stopped":
            self.last_activity = time.monotonic()
            self.user_speaking_since = None
            await self.face("thinking")
        elif t == "conversation.item.input_audio_transcription.completed":
            tr = ev.get("transcript", "")
            await self.send_dev_json({"type": "stt", "text": tr})
            if not self.bye_pending and BYE_RE.search(tr or ""):
                log.info("[%s] goodbye phrase heard (%r), ending conversation", self.id, tr)
                self.bye_pending = True
                await self.xai_send({"type": "response.cancel"})
                await self.xai_send({"type": "response.create", "response": {
                    "instructions": "Say only a very short goodbye, two or three words, like 'Bye for now!'"}})
                self._tasks.append(asyncio.create_task(self._bye_close()))
        elif t in ("response.output_audio_transcript.done", "response.audio_transcript.done"):
            text = ev.get("transcript", "")
            if text:
                log.info("[%s] %s: %s", self.id, self.cfg.bot_name, text)
                await self.send_dev_json({"type": "tts", "state": "sentence_start", "text": text})
        elif t == "response.created":
            self.response_done = False
            log.info("[%s] xAI response started", self.id)
        elif t == "response.done":
            self.response_done = True
            await self.out_q.put(None)  # marker: flush + tts stop when drained
        elif t == "error":
            log.error("[%s] xAI error: %s", self.id, ev.get("error", ev))
        elif t == "session.updated":
            log.debug("[%s] session updated", self.id)
        elif t == "input_audio_buffer.committed":
            log.info("[%s] xAI committed user audio", self.id)

    async def on_model_audio(self, pcm: bytes) -> None:
        g = float(os.getenv("RELAY_OUT_GAIN", "1.5"))
        if g != 1.0 and pcm:
            a = array.array("h"); a.frombytes(pcm[:len(pcm)//2*2])
            for i, v in enumerate(a):
                v = int(v * g); a[i] = 32767 if v > 32767 else (-32768 if v < -32768 else v)
            pcm = a.tobytes()
        self.out_pcm.extend(pcm)
        while len(self.out_pcm) >= OUT_FRAME_BYTES:
            frame = bytes(self.out_pcm[:OUT_FRAME_BYTES])
            del self.out_pcm[:OUT_FRAME_BYTES]
            await self.out_q.put(self.enc.encode(frame))

    async def playback_pump(self) -> None:
        """Sends opus frames to the device paced to real time, with tts start/stop around them."""
        loop = asyncio.get_running_loop()
        play_clock = 0.0
        while not self.closed:
            item = await self.out_q.get()
            if item is None:
                # end of a response: flush the remainder (padded) then stop
                if self.out_pcm:
                    rest = bytes(self.out_pcm) + b"\0" * (OUT_FRAME_BYTES - len(self.out_pcm))
                    self.out_pcm.clear()
                    item = self.enc.encode(rest)
                    await self._send_frame(item, loop, play_clock)
                if self.speaking:
                    # wait until the device has played what we sent
                    await asyncio.sleep(max(0.0, play_clock - loop.time()))
                    self.speaking = False
                    await self.send_dev_json({"type": "tts", "state": "stop"})
                    self.last_activity = time.monotonic()
                continue
            if not self.speaking:
                self.speaking = True
                play_clock = loop.time()
                await self.send_dev_json({"type": "tts", "state": "start"})
                # the firmware switches to Speaking asynchronously and drops audio until then
                await asyncio.sleep(0.12)
                play_clock = loop.time()
            play_clock = await self._send_frame(item, loop, play_clock)

    async def _send_frame(self, frame: bytes, loop: asyncio.AbstractEventLoop, play_clock: float) -> float:
        ahead = play_clock - loop.time()
        if ahead > PLAYBACK_LEAD_S:
            await asyncio.sleep(ahead - PLAYBACK_LEAD_S)
        if not self.dev.closed:
            await self.dev.send_bytes(frame)
            self.stats["spk_frames"] += 1
        self.last_activity = time.monotonic()
        return max(play_clock, loop.time()) + FRAME_MS / 1000

    async def interrupt(self, reason: str, cancel_model: bool = True) -> None:
        """Barge-in / abort: drop queued audio, cancel the model response, return the face to listening."""
        while not self.out_q.empty():
            self.out_q.get_nowait()
        self.out_pcm.clear()
        if cancel_model:
            await self.xai_send({"type": "response.cancel"})
        if self.speaking:
            self.speaking = False
            await self.send_dev_json({"type": "tts", "state": "stop"})

    async def end_session(self) -> None:
        """Relay-initiated end: stop TTS and show the sleep face, then close the socket.
        (The firmware also sleeps on its own when the channel closes.)"""
        try:
            await self.interrupt(reason="end", cancel_model=False)
            await self.send_dev_json({"type": "tts", "state": "stop"})
            await self.face("sleepy")
        except Exception:  # noqa: BLE001
            log.debug("[%s] could not send end-of-session hints", self.id)
        await self.dev.close()

    async def _bye_close(self) -> None:
        await asyncio.sleep(1.0)
        deadline = time.monotonic() + 6.0
        while time.monotonic() < deadline and (not self.response_done or self.speaking or not self.out_q.empty()):
            await asyncio.sleep(0.2)
        await asyncio.sleep(0.4)
        log.info("[%s] closing after goodbye", self.id)
        await self.end_session()

    async def idle_watchdog(self) -> None:
        while not self.closed:
            await asyncio.sleep(1.0)
            now = time.monotonic()
            since = self.user_speaking_since
            # the user is mid-utterance (capped so stuck VAD can't hold it open forever),
            # or the model is still working on a reply
            user_talking = since is not None and now - since < 60
            busy = (self.speaking or not self.out_q.empty() or user_talking
                    or not self.response_done)
            if not busy and time.monotonic() - self.last_activity > self.cfg.idle_close_s:
                log.info("[%s] idle for %.0fs, ending conversation", self.id, self.cfg.idle_close_s)
                await self.end_session()
                return

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        await self.out_q.put(None)
        for t in self._tasks:
            if t is not asyncio.current_task():
                t.cancel()
        if self.xai is not None and not self.xai.closed:
            await self.xai.close()
        log.info("[%s] session closed %s", self.id, self.stats)


def make_app(cfg: Config) -> web.Application:
    app = web.Application()
    app["cfg"] = cfg
    app["sessions"] = set()

    async def on_startup(app: web.Application) -> None:
        app["http"] = aiohttp.ClientSession()

    async def on_cleanup(app: web.Application) -> None:
        for s in list(app["sessions"]):
            await s.close()
        await app["http"].close()

    async def ota(request: web.Request) -> web.Response:
        try:
            info = await request.json() if request.can_read_body else {}
        except Exception:  # noqa: BLE001
            info = {}
        cur = (info.get("application") or {}).get("version", "0.0.0") if isinstance(info, dict) else "0.0.0"
        ws_url = cfg.public_ws_url or f"ws://{request.host.split(':')[0] if request.host else lan_ip()}:{cfg.port}/xiaozhi/v1/"
        log.info("OTA check from %s (fw %s) -> %s", request.headers.get("Device-Id", request.remote), cur, ws_url)
        body: dict[str, Any] = {
            "server_time": {"timestamp": int(time.time() * 1000), "timezone_offset": -time.timezone // 60 if not time.daylight else -time.altzone // 60},
            "firmware": {"version": cur, "url": ""},
            "websocket": {"url": ws_url, "token": cfg.device_token or "tamagroki", "version": 1},
        }
        return web.json_response(body)

    async def device_ws(request: web.Request) -> web.StreamResponse:
        if cfg.device_token:
            auth = request.headers.get("Authorization", "")
            if auth.split(" ")[-1] != cfg.device_token:
                return web.Response(status=401, text="bad device token")
        ws = web.WebSocketResponse(heartbeat=30, max_msg_size=0)
        await ws.prepare(request)
        log.info("device connected: %s (%s)", request.headers.get("Device-Id", "?"), request.remote)
        s = DeviceSession(cfg, ws, app["http"])
        app["sessions"].add(s)
        try:
            await s.run()
        finally:
            app["sessions"].discard(s)
        return ws

    async def health(request: web.Request) -> web.Response:
        return web.json_response({"ok": True, "bot": cfg.bot_name,
                                  "sessions": len(app["sessions"]), "xai_key_set": bool(cfg.xai_api_key)})

    app.router.add_route("*", "/xiaozhi/ota/", ota)
    app.router.add_get("/xiaozhi/v1/", device_ws)
    app.router.add_get("/health", health)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app
