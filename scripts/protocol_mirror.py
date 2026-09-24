#!/usr/bin/env python3
"""A local document mirror with ETag support, standing in for a county's update feed in the demo.

  python scripts/protocol_mirror.py <dir> --port 8300
Serves <dir>/<county>/<doc_id>.pdf. Responds 304 to If-None-Match when unchanged, so Herald's sync (which checks
only on a good link) fetches a document only when it really changed. The county's own site returns 403 to
scripts, so a real deployment needs an agency-provided feed; this mirror shows the mechanism honestly.
"""
import argparse
import hashlib
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path = Path(self.translate_path(self.path))
        if not path.is_file():
            return super().do_GET()
        data = path.read_bytes()
        etag = '"' + hashlib.sha256(data).hexdigest()[:16] + '"'
        if self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("ETag", etag)
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--port", type=int, default=8300)
    a = ap.parse_args()
    ThreadingHTTPServer(("0.0.0.0", a.port), partial(Handler, directory=a.dir)).serve_forever()
