# Tamagroki firmware (modified xiaozhi-esp32)

See the [top-level README](../README.md) for the project overview, parts, printing, flashing and relay setup. This file covers the firmware internals.

A lavender cube with two tilted black pill eyes. Say **"Yo Grok"** and talk to Grok in real time (full duplex, so you can interrupt it). Tamagroki is a plain, general-purpose Grok voice assistant; say **"Bye Grok"** to end the conversation.

```
 ┌──────── cube (ESP32-S3) ────────┐   Wi-Fi    ┌────────── Mac: relay/ ──────────┐   wss   ┌──────────────────┐
 │ MultiNet "yo grok" wake word     │──opus 16k─▶│ xiaozhi WS server + OTA endpoint │──pcm──▶│ xAI realtime voice│
 │ ES7210 AEC, realtime listening   │◀─opus 24k──│ server-VAD barge-in, pacing      │◀─pcm───│ grok-voice-latest │
 │ LVGL pill-eye face (5 states)    │◀─face evts─│ optional web_search, idle close  │        └──────────────────┘
 │ QMI8658 pick-up-to-wake (opt.)   │            │ "bye grok" ends the conversation │
 └──────────────────────────────────┘            └──────────────────────────────────┘
```

This is a vendored, modified copy of [78/xiaozhi-esp32](https://github.com/78/xiaozhi-esp32) at commit `d7a1c05` (MIT, see `LICENSE`). The upstream README is kept as `README.upstream.md`; `../patches/` has the full diff against upstream. Everything specific to the cube is in:

| Path | What |
|---|---|
| `main/tamagroki/grok_face.{h,cc}` | The face, written in pure LVGL v9 (shared with the simulator) |
| `main/tamagroki/grok_face_display.{h,cc}` | Replaces xiaozhi's chat UI and maps device state to the face |
| `main/tamagroki/qmi8658_pickup.{h,cc}` | IMU pick-up detector |
| `main/tamagroki/tamagroki_audio.cc` | Speaker loudness, used for the speaking bounce |
| `main/boards/waveshare/esp32-s3-touch-amoled-2.16/*.cc` | Wires the face and IMU into the stock board |
| `main/Kconfig.projbuild` → menu **Tamagroki** (Tamagroki settings) | Name, colour, tilt, subtitles, IMU |
| `tamagroki/sdkconfig.tamagroki` | Build preset: board, custom wake word, MN7-EN, AEC, relay URL |
| `build.sh`, `flash.sh`, `test.sh` | Build, flash, and desktop tests |
| `../relay/` | Python relay for the Mac, plus tests (mock device, mock xAI) |
| `sim/face/` | Headless LVGL simulator that renders PNG/GIF previews of every face state |

## 1. Relay

See `../relay/` and the top-level README.

## 2. Build and flash the cube

You need ESP-IDF **v6.1** (xiaozhi now requires 6.0.1 or newer):

```bash
mkdir -p ~/esp && cd ~/esp && git clone -b v6.1 --recursive https://github.com/espressif/esp-idf.git
cd esp-idf && ./install.sh esp32s3 && . ./export.sh
```

Connect the cube over USB-C, then:

```bash
./flash.sh /dev/cu.usbmodem*          # builds with OTA URL http://<this-mac>.local:8765/xiaozhi/ota/, flashes, opens the monitor
```

- To use a fixed IP: `TAMAGROKI_RELAY_URL=http://<relay-ip>:8765/xiaozhi/ota/ ./flash.sh /dev/cu.usbmodem1101`
- If the port doesn't show up: hold **BOOT**, tap **PWR/RESET**, release BOOT, then retry.
- `./flash.sh PORT --no-build` writes the existing `build/merged-binary.bin` with esptool. This is a full-image write, so it also clears saved Wi-Fi.

**First boot:** the cube opens a Wi-Fi access point and shows its name under the eyes. Join it from your phone, pick your Wi-Fi, and if needed set **Advanced → OTA URL** to the relay URL that `run.sh` printed. You can change the relay that way without rebuilding. The cube then fetches `/xiaozhi/ota/` from the relay, gets the websocket URL, and the relay never offers firmware updates.

**Buttons:** BOOT click starts or stops a conversation (or enters Wi-Fi setup during boot). BOOT double-click toggles device AEC. PWR hold for 4 s powers off.

## 3. Configuring the name, wake word, colour and face

Everything lives in Kconfig (`idf.py menuconfig` → *Xiaozhi Assistant* → *Tamagroki* and *Wake Word*). It is easiest through `build.sh` environment variables or a gitignored `tamagroki/sdkconfig.local`:

```bash
TAMAGROKI_NAME=Jarvis TAMAGROKI_WAKE="hey jarvis" TAMAGROKI_COLOR=0x9B7FE0 ./flash.sh /dev/cu.usbmodem*
```

| Kconfig | Default | |
|---|---|---|
| `CONFIG_TAMAGROKI_NAME` | `Tamagroki` | Bot name (also set `TAMAGROKI_NAME` on the relay) |
| `CONFIG_CUSTOM_WAKE_WORD` | `yo grok;yo grog;yoh grok;yo grawk` | MultiNet-7 English command phrases, lowercase, `;`-separated, all wake |
| `CONFIG_CUSTOM_WAKE_WORD_THRESHOLD` | `13` (%) | Lower values are more sensitive and give more false wakes |
| `CONFIG_CUSTOM_WAKE_WORD_SW_GAIN` | `3` | Software gain into MultiNet only (the mic is quiet; ES7210 PGA is also raised to 37.5 dB on this board) |
| `CONFIG_TAMAGROKI_BG_COLOR` | `0x9B7FE0` | Solid background colour |
| `CONFIG_TAMAGROKI_EYE_TILT_DEG` | `12` | Pill lean; positive tilts the tops to the right |
| `CONFIG_TAMAGROKI_SHOW_SUBTITLES` | `n` | Shows STT/TTS text under the eyes |
| `CONFIG_TAMAGROKI_IMU_WAKE` / `_THRESHOLD_MG` | `n` / `350` | Picking the cube up starts a conversation (off: it false-triggered) |

**Face states** (preview them with `./test.sh` or `../relay/.venv/bin/python sim/face/render.py`; needs cmake + a C++ compiler + Pillow, which writes to `sim/face/out/`):

- **idle (no conversation open):** shows the **sleep** face, so awake eyes always mean "listening"
- **listening:** taller, raised eyes with a pulse
- **thinking:** eyes look up-right and squish alternately. The relay sends this after you stop talking.
- **speaking:** eyes bounce with the real speaker loudness
- **sleep:** closed eyes with drifting "z z z", shown whenever no conversation is open (wake word armed)
- **busy:** connecting

### Wake-word tuning

"Yo Grok" uses ESP-SR **MultiNet7 (English)** as a custom command, so no training is needed. Tune it on the device:

1. Watch `idf.py monitor` for `CustomWakeWord` detections while you say the phrase at different distances, and while music or TV plays.
2. If it misses you, lower `CONFIG_CUSTOM_WAKE_WORD_THRESHOLD` (try 10 to 15). If it false-triggers, raise it (try 30 to 40).
3. Alternative spellings sometimes match better; add them `;`-separated (e.g. `yo grog` was what matched in testing). Each extra phrase adds false-trigger risk.
4. For real robustness, a trained microWakeWord model would do better.

Audio-path changes for the wake word: AEC is off while idle (the AEC NLP was eating speech), MultiNet's window restarts at VAD speech onset with the VAD pre-roll, ES7210 PGA at 37.5 dB, and x3 software gain into MultiNet only.

## 4. Tests on a desktop (no hardware)

```bash
./test.sh        # ../relay pytest + face simulator frames
```

- `../relay/tests/test_relay.py` runs a mock cube that speaks the exact xiaozhi WS and opus protocol, and a mock xAI realtime server (energy VAD, audio deltas, cancellation). It covers the OTA response, health, persona defaults, a full conversation turn, barge-in (cancels the response and cuts playback short), "bye grok" closing the conversation, and opus round trips.
- `sim/face` builds `grok_face.cc` against desktop LVGL 9.5 and renders a scripted timeline (idle → listening → thinking → speaking → idle → sleep) to `sim/face/out/*.png|gif`.

## Known limitations / TODO

- The QMI8658 pick-up wake is disabled by default because it false-triggered.
- MultiNet custom-phrase accuracy is lower than a trained WakeNet or microWakeWord model.
- Upstream fix included: the 2.16 board was missing from `USE_DEVICE_AEC`'s Kconfig dependency list, so `CONFIG_USE_DEVICE_AEC=y` from its `config.json` was silently dropped.
