"""Run the server outside OBS: .venv\\Scripts\\python -m peercam [options]"""

import argparse
import time

from .log import setup_logging
from .server import SignalingServer


def main():
    parser = argparse.ArgumentParser(prog="peercam")
    parser.add_argument("--port", type=int, default=8080, help="localhost HTTP port for OBS")
    parser.add_argument("--https-port", type=int, default=8443, help="LAN HTTPS port for phones, 0 = off")
    parser.add_argument("--max-cameras", type=int, default=5, choices=range(1, 9))
    parser.add_argument("--buffer-ms", type=int, default=100, help="viewer jitter buffer target, 0 = adaptive")
    args = parser.parse_args()

    setup_logging()
    server = SignalingServer(args.port, args.max_cameras, https_port=args.https_port or None,
                             buffer_ms=args.buffer_ms)
    server.start()
    try:
        while server.running:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()


if __name__ == "__main__":
    main()
