"""End-to-end relay tests: mock device <-> relay <-> mock xAI."""
import asyncio
import os
from pathlib import Path

import aiohttp
import pytest
from aiohttp import web

from tamagroki_relay.config import Config
from tamagroki_relay.opus import Decoder, Encoder
from tamagroki_relay.server import BYE_RE, make_app
from mock_device import MockDevice, synth, FRAME
from mock_xai import MockXai



def free_port() -> int:
    import socket
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


@pytest.fixture
async def stack(tmp_path):
    mock = MockXai()
    xr = web.AppRunner(mock.app()); await xr.setup()
    xport = free_port(); await web.TCPSite(xr, "127.0.0.1", xport).start()
    cfg = Config(xai_api_key="test-key", xai_url=f"ws://127.0.0.1:{xport}/v1/realtime?model=grok-voice-latest",
                 bot_name="Tamagroki", port=free_port(), idle_close_s=30)
    rr = web.AppRunner(make_app(cfg)); await rr.setup()
    await web.TCPSite(rr, "127.0.0.1", cfg.port).start()
    http = aiohttp.ClientSession()
    yield {"mock": mock, "cfg": cfg, "http": http, "url": f"http://127.0.0.1:{cfg.port}", "tmp": tmp_path}
    await http.close(); await rr.cleanup(); await xr.cleanup()


async def keep_mic_open(dev, seconds):
    silence = bytes(FRAME * 2)
    loop = asyncio.get_running_loop(); end = loop.time() + seconds
    while loop.time() < end:
        await dev.ws.send_bytes(dev.enc.encode(silence)); await asyncio.sleep(0.06)


def test_opus_roundtrip():
    enc, dec = Encoder(16000), Decoder(16000)
    pcm = synth(0.06, 8000)
    pkt = enc.encode(pcm)
    assert 0 < len(pkt) < len(pcm)
    out = dec.decode(pkt)
    assert len(out) == len(pcm)


def test_defaults_and_instructions():
    cfg = Config()
    assert cfg.bot_name == "Tamagroki"
    ins = cfg.instructions()
    assert ins.startswith("You are Tamagroki, a small lavender-purple desk cube")
    assert "powered by Grok" in ins and "one to three spoken sentences" in ins


def test_bye_regex():
    assert BYE_RE.search("okay, bye Grok!")
    assert BYE_RE.search("Goodbye grog")
    assert not BYE_RE.search("tell me about Grok")


async def test_ota_points_device_at_relay(stack):
    async with stack["http"].post(stack["url"] + "/xiaozhi/ota/", json={"application": {"version": "2.0.0"}}) as r:
        body = await r.json()
    assert body["websocket"]["url"] == f"ws://127.0.0.1:{stack['cfg'].port}/xiaozhi/v1/"
    assert body["firmware"]["version"] == "2.0.0"  # never offers an OTA update
    assert "timestamp" in body["server_time"]


async def test_conversation_turn(stack):
    dev = MockDevice(stack["url"]); await dev.connect(stack["http"])
    assert dev.log.hello["audio_params"]["sample_rate"] == 24000
    await dev.listen_start()
    await dev.stream(synth(0.9, 6000) + bytes(FRAME * 2 * 8))
    assert await dev.wait_for(lambda: "stop" in dev.tts_states(), 8)
    await dev.ws.close()
    ev = stack["mock"].events
    su = ev[0]
    assert su["type"] == "session.update"
    assert su["session"]["turn_detection"]["type"] == "server_vad"
    assert su["session"]["audio"]["input"]["format"]["rate"] == 16000
    assert su["session"]["tools"] == [{"type": "web_search"}]  # no function tools
    assert su["session"]["instructions"].startswith("You are Tamagroki")
    assert stack["mock"].auth_headers[0] == "Bearer test-key"
    assert dev.tts_states()[:3] == ["start", "sentence_start", "stop"]
    assert dev.log.audio_frames >= 24  # 1.5 s of reply at 60 ms/frame
    assert any(m.get("type") == "stt" for m in dev.log.json_in)
    faces = [w for _, w in dev.log.timeline if w.startswith("face:")]
    assert "face:listening" in faces and "face:thinking" in faces


async def test_barge_in_interrupts_playback(stack):
    dev = MockDevice(stack["url"]); await dev.connect(stack["http"])
    await dev.listen_start()
    await dev.stream(synth(0.9, 6000) + bytes(FRAME * 2 * 7))
    assert await dev.wait_for(lambda: dev.log.audio_frames >= 5, 8)
    # user talks over the bot (full duplex: mic keeps streaming while speaking)
    await dev.stream(synth(0.6, 6000))
    assert await dev.wait_for(lambda: "stop" in dev.tts_states(), 3)
    frames_at_stop = dev.log.audio_frames
    assert frames_at_stop < 24, "playback should have been cut short"
    assert any(e["type"] == "response.cancel" for e in stack["mock"].events)
    # finish the barge-in utterance -> a new reply plays
    await dev.stream(bytes(FRAME * 2 * 8))
    assert await dev.wait_for(lambda: dev.tts_states().count("stop") >= 2, 8)
    await dev.ws.close()


async def test_health_reports_bot(stack):
    async with stack["http"].get(stack["url"] + "/health") as r:
        body = await r.json()
    assert body["bot"] == "Tamagroki" and set(body) == {"ok", "bot", "sessions", "xai_key_set"}


async def test_bye_grok_closes_conversation(stack):
    stack["mock"].transcript = "thanks, bye Grok"
    dev = MockDevice(stack["url"]); await dev.connect(stack["http"])
    await dev.listen_start()
    await dev.stream(synth(0.9, 6000) + bytes(FRAME * 2 * 8))
    mic = asyncio.create_task(keep_mic_open(dev, 10))
    closed = await dev.wait_for(lambda: dev.ws.closed, 12)
    mic.cancel()
    assert closed, "relay should close the device socket after the goodbye"
    assert dev.tts_states()[-1] == "stop"
    assert [m.get("emotion") for m in dev.log.json_in if m.get("type") == "llm"][-1] == "sleepy"
    ev = stack["mock"].events
    assert any(e.get("type") == "response.create" and "goodbye" in e.get("response", {}).get("instructions", "")
               for e in ev)
