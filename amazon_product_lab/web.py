from __future__ import annotations

import argparse
import json
import tempfile
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .opportunity_import import analyze_opportunity_export, write_opportunity_outputs


ASSET_DIR = Path(__file__).with_name("web_assets")
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
}


def analyze_upload(filename: str, payload: bytes) -> dict[str, object]:
    if not payload:
        raise ValueError("文件为空")
    safe_name = Path(filename or "opportunity-export.csv").name
    if not safe_name.lower().endswith(".csv"):
        raise ValueError("仅支持 CSV 文件")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / safe_name
        output = root / "output"
        source.write_bytes(payload)
        analysis = analyze_opportunity_export(source)
        write_opportunity_outputs(analysis, output)
        enrichment_csv = (output / "candidate_enrichment.csv").read_text(
            encoding="utf-8-sig"
        )
    return {"analysis": analysis, "enrichment_csv": enrichment_csv}


class ProductLabHandler(BaseHTTPRequestHandler):
    server_version = "AmazonProductLab/1.0"

    def do_GET(self) -> None:
        route = urlparse(self.path).path
        asset = "index.html" if route == "/" else route.removeprefix("/")
        if asset not in {"index.html", "styles.css", "app.js"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        path = ASSET_DIR / asset
        try:
            body = path.read_bytes()
        except FileNotFoundError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self._send_bytes(HTTPStatus.OK, body, CONTENT_TYPES[path.suffix])

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/analyze":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "无效的文件大小"})
            return
        if length <= 0:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "文件为空"})
            return
        if length > MAX_UPLOAD_BYTES:
            self._send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "文件不能超过 25 MB"})
            return
        filename = parse_qs(parsed.query).get("filename", ["opportunity-export.csv"])[0]
        try:
            response = analyze_upload(filename, self.rfile.read(length))
        except (OSError, UnicodeError, ValueError) as error:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        self._send_json(HTTPStatus.OK, response)

    def log_message(self, format: str, *args: object) -> None:
        print(f"[web] {self.address_string()} {format % args}")

    def _send_json(self, status: HTTPStatus, data: object) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._send_bytes(status, body, "application/json; charset=utf-8")

    def _send_bytes(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Amazon Product Lab web interface")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), ProductLabHandler)
    url = f"http://{args.host}:{server.server_port}"
    print(f"Amazon Product Lab running at {url}")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
