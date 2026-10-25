"""Local web UI: serves the static page and a JSON API on 127.0.0.1."""

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import memory

STATIC = Path(__file__).parent / "static"
API = {"/api/memory": memory.snapshot}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in API:
            try:
                body, status = json.dumps(API[path]()).encode(), 200
            except Exception as e:  # report collection failures to the UI
                body, status = json.dumps({"error": str(e)}).encode(), 500
            self._send(status, "application/json", body)
            return
        file = (STATIC / (path.lstrip("/") or "index.html")).resolve()
        if not file.is_relative_to(STATIC) or not file.is_file():
            self._send(404, "text/plain", b"not found")
            return
        ctype = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
        self._send(200, ctype, file.read_bytes())

    def _send(self, status, ctype, body):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


def serve(port):
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
