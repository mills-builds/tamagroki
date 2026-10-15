#!/usr/bin/env bash
# One-command build + flash for the Tamagroki cube (Waveshare ESP32-S3-Touch-AMOLED-2.16).
#
#   ./flash.sh /dev/cu.usbmodem*            # build for this Mac's relay, flash, open monitor
#   ./flash.sh /dev/cu.usbmodem* --no-build # flash the existing build/merged-binary.bin with esptool
#   TAMAGROKI_RELAY_URL=http://<relay-ip>:8765/xiaozhi/ota/ ./flash.sh /dev/cu.usbmodem1101
#   NO_MONITOR=1 ./flash.sh /dev/cu.usbmodem1101
set -euo pipefail
cd "$(dirname "$0")"
PORT="${1:-}"
[ -z "$PORT" ] && { ls /dev/cu.usbmodem* /dev/ttyACM* 2>/dev/null | head -1 >/dev/null; PORT=$(ls /dev/cu.usbmodem* /dev/ttyACM* 2>/dev/null | head -1 || true); }
[ -z "$PORT" ] && { echo "usage: $0 /dev/cu.usbmodemXXXX [--no-build]   (plug the cube in over USB-C)"; exit 1; }
shift || true
BUILD=1; [ "${1:-}" = "--no-build" ] && BUILD=0

if [ -z "${TAMAGROKI_RELAY_URL:-}" ]; then
  if command -v scutil >/dev/null; then HOST="$(scutil --get LocalHostName).local"; else HOST="$(hostname).local"; fi
  export TAMAGROKI_RELAY_URL="http://${HOST}:8765/xiaozhi/ota/"
fi

if [ "$BUILD" = 1 ]; then
  echo ">> building with relay OTA URL $TAMAGROKI_RELAY_URL"
  ./build.sh
  echo ">> flashing $PORT"
  idf.py -p "$PORT" -b 921600 flash   # keeps NVS (Wi-Fi credentials)
  [ -z "${NO_MONITOR:-}" ] && exec idf.py -p "$PORT" monitor
else
  BIN=build/merged-binary.bin
  [ -f "$BIN" ] || { echo "no $BIN; run without --no-build"; exit 1; }
  ESPTOOL="esptool.py"; command -v esptool.py >/dev/null || ESPTOOL="python3 -m esptool"
  echo ">> flashing $BIN to $PORT (whole flash image, this also resets saved Wi-Fi)"
  $ESPTOOL --chip esp32s3 -p "$PORT" -b 921600 --before default-reset --after hard-reset write-flash 0x0 "$BIN"
  echo "done. The relay URL baked into this binary is in build/tamagroki.local.sdkconfig (CONFIG_OTA_URL);"
  echo "you can also change it in the Wi-Fi setup page (Advanced -> OTA URL)."
fi
