#!/usr/bin/env bash
# Build the Tamagroki cube firmware (ESP-IDF >= 6.0.1, 6.1 recommended).
#   ./build.sh                       # uses tamagroki/sdkconfig.tamagroki
#   TAMAGROKI_RELAY_URL=http://<relay-ip>:8765/xiaozhi/ota/ ./build.sh
#   TAMAGROKI_COLOR=0xFF8800 TAMAGROKI_NAME=Jarvis TAMAGROKI_WAKE="hey jarvis" ./build.sh
set -euo pipefail
cd "$(dirname "$0")"
if ! command -v idf.py >/dev/null; then
  for p in "${IDF_PATH:-}" "$HOME/esp/esp-idf" "$HOME/.espressif/esp-idf"; do
    [ -n "$p" ] && [ -f "$p/export.sh" ] && { . "$p/export.sh" >/dev/null; break; }
  done
fi
command -v idf.py >/dev/null || { echo "ESP-IDF not found: install it (see README) or source export.sh"; exit 1; }

frag=build/tamagroki.local.sdkconfig
mkdir -p build
cp tamagroki/sdkconfig.tamagroki "$frag"
[ -n "${TAMAGROKI_RELAY_URL:-}" ] && echo "CONFIG_OTA_URL=\"$TAMAGROKI_RELAY_URL\"" >> "$frag"
[ -n "${TAMAGROKI_COLOR:-}" ]     && echo "CONFIG_TAMAGROKI_BG_COLOR=$TAMAGROKI_COLOR" >> "$frag"
[ -n "${TAMAGROKI_NAME:-}" ]      && echo "CONFIG_TAMAGROKI_NAME=\"$TAMAGROKI_NAME\"" >> "$frag"
if [ -n "${TAMAGROKI_WAKE:-}" ]; then
  echo "CONFIG_CUSTOM_WAKE_WORD=\"$(echo "$TAMAGROKI_WAKE" | tr 'A-Z' 'a-z')\"" >> "$frag"
  echo "CONFIG_CUSTOM_WAKE_WORD_DISPLAY=\"$TAMAGROKI_WAKE\"" >> "$frag"
fi
[ -f tamagroki/sdkconfig.local ] && cat tamagroki/sdkconfig.local >> "$frag"   # your private overrides (gitignored)

# regenerate sdkconfig from defaults whenever the preset changed (full rebuild), else incremental
if ! cmp -s "$frag" build/tamagroki.last.sdkconfig; then rm -f sdkconfig; fi
cp "$frag" build/tamagroki.last.sdkconfig
idf.py -DIDF_TARGET=esp32s3 "-DSDKCONFIG_DEFAULTS=sdkconfig.defaults;$frag" \
       -DBOARD_NAME=esp32-s3-touch-amoled-2.16 build
idf.py merge-bin
echo "OK: build/merged-binary.bin ($(du -h build/merged-binary.bin | cut -f1))"
