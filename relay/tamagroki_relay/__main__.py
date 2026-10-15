import argparse
import logging

from aiohttp import web

from .config import Config
from .server import lan_ip, make_app


def main() -> None:
    ap = argparse.ArgumentParser(description="Tamagroki voice relay")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = Config.from_env()
    if not cfg.xai_api_key:
        logging.warning("XAI_API_KEY is not set: `export XAI_API_KEY=xai-...` or add it to relay/.env")
    ip = lan_ip()
    print(f"\n  Tamagroki relay for '{cfg.bot_name}'\n"
          f"  OTA URL for the firmware: http://{ip}:{cfg.port}/xiaozhi/ota/\n"
          f"  Device websocket:         ws://{ip}:{cfg.port}/xiaozhi/v1/\n")
    web.run_app(make_app(cfg), host=cfg.host, port=cfg.port, print=None)


if __name__ == "__main__":
    main()
