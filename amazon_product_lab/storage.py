from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProductLabStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS analysis_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dataset_type TEXT NOT NULL,
                    analysis_json TEXT NOT NULL,
                    enrichment_csv TEXT NOT NULL,
                    download_name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS product_concepts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'idea',
                    target_customer TEXT NOT NULL,
                    pain_point TEXT NOT NULL,
                    differentiation TEXT NOT NULL,
                    target_price REAL NOT NULL,
                    sku TEXT NOT NULL DEFAULT '',
                    compliance_risk TEXT NOT NULL DEFAULT 'unknown',
                    ip_risk TEXT NOT NULL DEFAULT 'unknown',
                    hazmat INTEGER NOT NULL DEFAULT 0,
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS concept_benchmarks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    concept_id INTEGER NOT NULL REFERENCES product_concepts(id) ON DELETE CASCADE,
                    asin TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS supplier_quotes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    concept_id INTEGER NOT NULL REFERENCES product_concepts(id) ON DELETE CASCADE,
                    supplier_name TEXT NOT NULL,
                    product_url TEXT NOT NULL DEFAULT '',
                    unit_cost REAL NOT NULL,
                    domestic_shipping REAL NOT NULL DEFAULT 0,
                    international_shipping REAL NOT NULL DEFAULT 0,
                    tariff REAL NOT NULL DEFAULT 0,
                    packaging REAL NOT NULL DEFAULT 0,
                    moq INTEGER NOT NULL DEFAULT 0,
                    lead_time_days INTEGER NOT NULL DEFAULT 0,
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS profit_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    concept_id INTEGER NOT NULL REFERENCES product_concepts(id) ON DELETE CASCADE,
                    input_json TEXT NOT NULL DEFAULT '{}',
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS listing_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    concept_id INTEGER NOT NULL REFERENCES product_concepts(id) ON DELETE CASCADE,
                    content_json TEXT NOT NULL,
                    approved INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS launch_packages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    concept_id INTEGER NOT NULL REFERENCES product_concepts(id) ON DELETE CASCADE,
                    package_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS experiment_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    concept_id INTEGER NOT NULL REFERENCES product_concepts(id) ON DELETE CASCADE,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS decision_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    concept_id INTEGER NOT NULL REFERENCES product_concepts(id) ON DELETE CASCADE,
                    from_status TEXT NOT NULL,
                    to_status TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def save_analysis(
        self,
        dataset_type: str,
        analysis: dict[str, Any],
        enrichment_csv: str,
        download_name: str,
    ) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO analysis_runs (dataset_type, analysis_json, enrichment_csv, download_name, created_at) VALUES (?, ?, ?, ?, ?)",
                (dataset_type, json.dumps(analysis, ensure_ascii=False), enrichment_csv, download_name, _now()),
            )
            return int(cursor.lastrowid)

    def get_latest_analysis(self) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM analysis_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "dataset_type": row["dataset_type"],
            "analysis": json.loads(row["analysis_json"]),
            "enrichment_csv": row["enrichment_csv"],
            "download_name": row["download_name"],
            "created_at": row["created_at"],
        }

    def create_concept(self, data: dict[str, Any]) -> dict[str, Any]:
        required = ("name", "target_customer", "pain_point", "differentiation", "target_price")
        missing = [field for field in required if data.get(field) in (None, "")]
        if missing:
            raise ValueError(f"缺少产品方案字段: {', '.join(missing)}")
        created_at = _now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO product_concepts
                (name, target_customer, pain_point, differentiation, target_price, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(data["name"]).strip(),
                    str(data["target_customer"]).strip(),
                    str(data["pain_point"]).strip(),
                    str(data["differentiation"]).strip(),
                    float(data["target_price"]),
                    created_at,
                    created_at,
                ),
            )
            concept_id = int(cursor.lastrowid)
            for benchmark in data.get("benchmarks", []):
                connection.execute(
                    "INSERT INTO concept_benchmarks (concept_id, asin, snapshot_json, created_at) VALUES (?, ?, ?, ?)",
                    (concept_id, benchmark["asin"], json.dumps(benchmark, ensure_ascii=False), created_at),
                )
        return self.get_concept(concept_id)

    def list_concepts(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM product_concepts ORDER BY updated_at DESC, id DESC"
            ).fetchall()
        return [self._concept_summary(row) for row in rows]

    def get_concept(self, concept_id: int) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM product_concepts WHERE id = ?", (concept_id,)
            ).fetchone()
            if row is None:
                raise ValueError("产品方案不存在")
            benchmarks = [
                json.loads(item["snapshot_json"])
                for item in connection.execute(
                    "SELECT snapshot_json FROM concept_benchmarks WHERE concept_id = ? ORDER BY id",
                    (concept_id,),
                )
            ]
            quotes = [dict(item) for item in connection.execute(
                "SELECT * FROM supplier_quotes WHERE concept_id = ? ORDER BY id DESC", (concept_id,)
            )]
            snapshots = [
                {
                    "id": item["id"],
                    "inputs": json.loads(item["input_json"]),
                    **json.loads(item["result_json"]),
                    "created_at": item["created_at"],
                }
                for item in connection.execute(
                    "SELECT * FROM profit_snapshots WHERE concept_id = ? ORDER BY id DESC", (concept_id,)
                )
            ]
            listings = [
                {"id": item["id"], **json.loads(item["content_json"]), "approved": bool(item["approved"]), "created_at": item["created_at"]}
                for item in connection.execute(
                    "SELECT * FROM listing_versions WHERE concept_id = ? ORDER BY id DESC", (concept_id,)
                )
            ]
            results = [
                {"id": item["id"], **json.loads(item["result_json"]), "created_at": item["created_at"]}
                for item in connection.execute(
                    "SELECT * FROM experiment_results WHERE concept_id = ? ORDER BY id DESC", (concept_id,)
                )
            ]
            decisions = [dict(item) for item in connection.execute(
                "SELECT * FROM decision_events WHERE concept_id = ? ORDER BY id DESC", (concept_id,)
            )]
        concept = dict(row)
        concept["hazmat"] = bool(concept["hazmat"])
        concept.update(
            benchmarks=benchmarks,
            supplier_quotes=quotes,
            profit_snapshots=snapshots,
            listing_versions=listings,
            experiment_results=results,
            decision_events=decisions,
        )
        return concept

    def _concept_summary(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"], "name": row["name"], "status": row["status"],
            "target_price": row["target_price"], "differentiation": row["differentiation"],
            "updated_at": row["updated_at"],
        }

    def update_concept(self, concept_id: int, data: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "name", "target_customer", "pain_point", "differentiation",
            "target_price", "sku", "compliance_risk", "ip_risk", "hazmat", "notes",
        }
        updates = {key: value for key, value in data.items() if key in allowed}
        if not updates:
            return self.get_concept(concept_id)
        updates["updated_at"] = _now()
        assignments = ", ".join(f"{key} = ?" for key in updates)
        values = [int(value) if key == "hazmat" else value for key, value in updates.items()]
        with self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE product_concepts SET {assignments} WHERE id = ?", (*values, concept_id)
            )
            if cursor.rowcount == 0:
                raise ValueError("产品方案不存在")
        return self.get_concept(concept_id)

    def set_status(self, concept_id: int, status: str, reason: str = "") -> dict[str, Any]:
        with self._connect() as connection:
            current = connection.execute(
                "SELECT status FROM product_concepts WHERE id = ?", (concept_id,)
            ).fetchone()
            if current is None:
                raise ValueError("产品方案不存在")
            cursor = connection.execute(
                "UPDATE product_concepts SET status = ?, updated_at = ? WHERE id = ?",
                (status, _now(), concept_id),
            )
            if cursor.rowcount and current["status"] != status:
                connection.execute(
                    "INSERT INTO decision_events (concept_id, from_status, to_status, reason, created_at) VALUES (?, ?, ?, ?, ?)",
                    (concept_id, current["status"], status, reason.strip(), _now()),
                )
        return self.get_concept(concept_id)

    def add_supplier_quote(self, concept_id: int, data: dict[str, Any]) -> dict[str, Any]:
        if not str(data.get("supplier_name", "")).strip():
            raise ValueError("供应商名称不能为空")
        product_url = str(data.get("product_url", "")).strip()
        if product_url:
            parsed_url = urlparse(product_url)
            if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
                raise ValueError("供应商链接必须是有效的 http/https 地址")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO supplier_quotes
                (concept_id, supplier_name, product_url, unit_cost, domestic_shipping,
                 international_shipping, tariff, packaging, moq, lead_time_days, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    concept_id, str(data["supplier_name"]).strip(), product_url,
                    float(data["unit_cost"]), float(data.get("domestic_shipping", 0)),
                    float(data.get("international_shipping", 0)), float(data.get("tariff", 0)),
                    float(data.get("packaging", 0)), int(data.get("moq", 0)),
                    int(data.get("lead_time_days", 0)), str(data.get("notes", "")), _now(),
                ),
            )
            quote_id = int(cursor.lastrowid)
            row = connection.execute("SELECT * FROM supplier_quotes WHERE id = ?", (quote_id,)).fetchone()
        return dict(row)

    def add_profit_snapshot(
        self, concept_id: int, result: dict[str, Any], inputs: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO profit_snapshots (concept_id, input_json, result_json, created_at) VALUES (?, ?, ?, ?)",
                (concept_id, json.dumps(inputs or {}, ensure_ascii=False), json.dumps(result, ensure_ascii=False), _now()),
            )
            snapshot_id = int(cursor.lastrowid)
        return {"id": snapshot_id, "inputs": inputs or {}, **result}

    def add_listing_version(self, concept_id: int, content: dict[str, Any]) -> dict[str, Any]:
        required = (
            "title", "bullet_points", "description", "search_terms", "evidence", "image_paths"
        )
        missing = [field for field in required if not content.get(field)]
        if missing:
            raise ValueError(f"缺少 Listing 字段: {', '.join(missing)}")
        approved = bool(content.get("approved"))
        if approved and not content.get("image_rights_confirmed"):
            raise ValueError("批准 Listing 前必须确认图片授权与实物一致")
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO listing_versions (concept_id, content_json, approved, created_at) VALUES (?, ?, ?, ?)",
                (concept_id, json.dumps(content, ensure_ascii=False), int(approved), _now()),
            )
            listing_id = int(cursor.lastrowid)
        return {"id": listing_id, **content, "approved": approved}

    def add_experiment_result(self, concept_id: int, result: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO experiment_results (concept_id, result_json, created_at) VALUES (?, ?, ?)",
                (concept_id, json.dumps(result, ensure_ascii=False), _now()),
            )
            result_id = int(cursor.lastrowid)
        return {"id": result_id, **result}

    def save_launch_package(self, concept_id: int, package: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO launch_packages (concept_id, package_json, created_at) VALUES (?, ?, ?)",
                (concept_id, json.dumps(package, ensure_ascii=False), _now()),
            )
            package_id = int(cursor.lastrowid)
        return {"id": package_id, **package}
