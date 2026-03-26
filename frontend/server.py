#!/usr/bin/env python3
from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class NoCacheRequestHandler(SimpleHTTPRequestHandler):
    """Serve static frontend files without browser caching."""

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the CNC Dashboard frontend.")
    parser.add_argument("--bind", default="127.0.0.1", help="Address to bind to.")
    parser.add_argument("--port", type=int, default=8081, help="Port to listen on.")
    parser.add_argument(
        "--directory",
        default=".",
        help="Directory to serve static files from.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    handler = partial(NoCacheRequestHandler, directory=args.directory)
    server = ThreadingHTTPServer((args.bind, args.port), handler)
    print(f"Serving frontend from {args.directory} on http://{args.bind}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
