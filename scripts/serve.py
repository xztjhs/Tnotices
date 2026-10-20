#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地预览 Tnotices 看板：uv run python scripts/serve.py [port]"""
import http.server
import socketserver
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8088


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


with socketserver.TCPServer(("0.0.0.0", PORT), Handler) as httpd:
    print(f"Tnotices dashboard: http://127.0.0.1:{PORT}/index.html")
    print(f"LAN: http://<本机IP>:{PORT}/index.html")
    httpd.serve_forever()
