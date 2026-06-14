from __future__ import annotations

import argparse
import json
import tempfile
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .asin_import import analyze_asin_export, is_asin_export, write_asin_outputs
from .opportunity_import import analyze_opportunity_export, write_opportunity_outputs
from .storage import ProductLabStore
from .workflow import (
    build_launch_package,
    calculate_actual_result,
    calculate_profit_snapshot,
    validate_status_transition,
)


ASSET_DIR = Path(__file__).with_name("web_assets")
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
}


def analyze_upload(
    filename: str, payload: bytes, store: ProductLabStore | None = None
) -> dict[str, object]:
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
        if is_asin_export(source):
            analysis = analyze_asin_export(source)
            write_asin_outputs(analysis, output)
            download_name = "product_enrichment.csv"
            dataset_type = "asin"
        else:
            analysis = analyze_opportunity_export(source)
            write_opportunity_outputs(analysis, output)
            download_name = "candidate_enrichment.csv"
            dataset_type = "market"
        enrichment_csv = (output / download_name).read_text(encoding="utf-8-sig")
    response = {
        "dataset_type": dataset_type,
        "analysis": analysis,
        "enrichment_csv": enrichment_csv,
        "download_name": download_name,
    }
    if store:
        response["run_id"] = store.save_analysis(
            dataset_type, analysis, enrichment_csv, download_name
        )
    return response


class ProductLabHandler(BaseHTTPRequestHandler):
    server_version = "AmazonProductLab/1.0"

    def do_GET(self) -> None:
        route = urlparse(self.path).path
        store = self._store()
        if route == "/api/analysis/latest":
            self._send_json(HTTPStatus.OK, store.get_latest_analysis())
            return
        if route == "/api/concepts":
            self._send_json(HTTPStatus.OK, {"concepts": store.list_concepts()})
            return
        concept_route = self._concept_route(route)
        if concept_route and concept_route[1] == "":
            try:
                self._send_json(HTTPStatus.OK, store.get_concept(concept_route[0]))
            except ValueError as error:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": str(error)})
            return
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
        store = self._store()
        if parsed.path == "/api/concepts":
            self._handle_json(lambda data: store.create_concept(data), HTTPStatus.CREATED)
            return
        concept_route = self._concept_route(parsed.path)
        if concept_route:
            concept_id, action = concept_route
            handlers = {
                "update": lambda data: store.update_concept(concept_id, data),
                "quotes": lambda data: store.add_supplier_quote(concept_id, data),
                "profit": lambda data: self._save_profit(store, concept_id, data),
                "listing": lambda data: store.add_listing_version(concept_id, data),
                "status": lambda data: self._change_status(store, concept_id, data),
                "launch-package": lambda data: self._create_launch_package(store, concept_id, data),
                "results": lambda data: self._save_result(store, concept_id, data),
            }
            handler = handlers.get(action)
            if handler:
                self._handle_json(handler, HTTPStatus.CREATED)
                return
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
            response = analyze_upload(filename, self.rfile.read(length), store)
        except (OSError, UnicodeError, ValueError) as error:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        self._send_json(HTTPStatus.OK, response)

    def _store(self) -> ProductLabStore:
        return self.server.store  # type: ignore[attr-defined]

    def _concept_route(self, route: str) -> tuple[int, str] | None:
        parts = route.strip("/").split("/")
        if len(parts) not in {3, 4} or parts[:2] != ["api", "concepts"]:
            return None
        try:
            concept_id = int(parts[2])
        except ValueError:
            return None
        return concept_id, parts[3] if len(parts) == 4 else ""

    def _handle_json(self, handler: object, success_status: HTTPStatus) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            data = json.loads(self.rfile.read(length) or b"{}")
            result = handler(data)  # type: ignore[operator]
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        self._send_json(success_status, result)

    def _save_profit(
        self, store: ProductLabStore, concept_id: int, inputs: dict[str, object]
    ) -> dict[str, object]:
        result = calculate_profit_snapshot(inputs)
        snapshot = store.add_profit_snapshot(concept_id, result, inputs)
        concept = store.get_concept(concept_id)
        if concept["status"] in {"idea", "sourcing"}:
            store.set_status(concept_id, "quoted", "已生成利润快照")
        return snapshot

    def _change_status(
        self, store: ProductLabStore, concept_id: int, data: dict[str, object]
    ) -> dict[str, object]:
        concept = store.get_concept(concept_id)
        next_status = str(data.get("status", ""))
        latest_profit = concept["profit_snapshots"][0] if concept["profit_snapshots"] else None
        has_approved_listing = any(item["approved"] for item in concept["listing_versions"])
        validate_status_transition(concept["status"], next_status, latest_profit, has_approved_listing)
        return store.set_status(concept_id, next_status, str(data.get("reason", "人工操作")))

    def _create_launch_package(
        self, store: ProductLabStore, concept_id: int, data: dict[str, object]
    ) -> dict[str, object]:
        concept = store.get_concept(concept_id)
        package = build_launch_package(concept, int(data.get("inventory_quantity", 0)))
        saved = store.save_launch_package(concept_id, package)
        store.set_status(concept_id, "launch_ready", "已生成上架交接包")
        return saved

    def _save_result(
        self, store: ProductLabStore, concept_id: int, data: dict[str, object]
    ) -> dict[str, object]:
        result = calculate_actual_result(data)
        concept = store.get_concept(concept_id)
        validate_status_transition(
            concept["status"],
            "reviewing",
            concept["profit_snapshots"][0] if concept["profit_snapshots"] else None,
            any(item["approved"] for item in concept["listing_versions"]),
        )
        if concept["profit_snapshots"]:
            predicted_per_unit = concept["profit_snapshots"][0]["scenarios"]["base"]["profit"]
            predicted_total = predicted_per_unit * result["units_sold"]
            result["predicted_contribution_profit"] = round(predicted_total, 5)
            result["profit_variance"] = round(result["contribution_profit"] - predicted_total, 5)
        saved = store.add_experiment_result(concept_id, result)
        store.set_status(concept_id, "reviewing", "已回填真实销售结果")
        return saved

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
    parser.add_argument("--db", type=Path, default=Path("data/product_lab.db"))
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), ProductLabHandler)
    server.store = ProductLabStore(args.db)  # type: ignore[attr-defined]
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
