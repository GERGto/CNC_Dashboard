import os
import sys
from http.server import ThreadingHTTPServer


BACKEND_ROOT = os.path.dirname(os.path.abspath(__file__))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from cnc_backend import create_backend_app, create_request_handler


def main():
    app = create_backend_app()
    app.ensure_storage()
    app.start_background_tasks()

    bind_host = str(os.getenv("BIND_HOST", "")).strip()
    server = ThreadingHTTPServer((bind_host, app.config.port), create_request_handler(app))
    bind_label = bind_host or "0.0.0.0"
    print(f"Hardware API listening on http://{bind_label}:{app.config.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
