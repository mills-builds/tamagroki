# Third-party notices

## xiaozhi-esp32 (firmware/)

`firmware/` is a vendored, modified copy of
[78/xiaozhi-esp32](https://github.com/78/xiaozhi-esp32) at commit `d7a1c05`
(main, 2026-10-15).

- License: MIT. Copyright (c) 2025 Shenzhen Xinzhi Future Technology Co., Ltd.
  and Project Contributors. The original license is kept unchanged at
  [`firmware/LICENSE`](firmware/LICENSE), and it covers the whole `firmware/` tree,
  modifications included.
- The upstream README is kept at `firmware/README.upstream.md` (plus `README_zh.md` and `README_ja.md`).
- Every change made to upstream is listed as one unified diff in
  [`patches/xiaozhi-d7a1c05-to-tamagroki.diff`](patches/xiaozhi-d7a1c05-to-tamagroki.diff).
  To get the same tree from a clean upstream checkout:
  `git clone https://github.com/78/xiaozhi-esp32 && cd xiaozhi-esp32 && git checkout d7a1c05 && patch -p1 < ../patches/xiaozhi-d7a1c05-to-tamagroki.diff`

ESP-IDF components (ESP-SR, LVGL, esp-opus and others) are downloaded at build time by the
ESP-IDF component manager under their own licenses. They are not included in this repository.

## Everything else

The relay (`relay/`), tools (`tools/`), CAD files (`cad/`) and docs are
Copyright (c) 2026 Josh Mills, MIT licensed (see [`LICENSE`](LICENSE)).

"Grok" and "xAI" are trademarks of xAI. Tamagroki is an independent hobby project and is not affiliated with or endorsed by xAI.
