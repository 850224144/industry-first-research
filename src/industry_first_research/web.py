"""Local read-only research console and task-resolution API.

The console is intentionally local-only. It reads bounded metadata from saved
JSON snapshots and can persist a resolved research task, but it never fetches
market data, calls a model, creates a decision snapshot, or enables execution.
"""

from __future__ import annotations

from collections import Counter
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .task_resolution import TaskResolutionError, resolve_research_task


WEB_API_SCHEMA_VERSION = "research-web-api.v1"
_MAX_BODY_BYTES = 512 * 1024
_MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024
_SNAPSHOT_DIRS = (
    "research_tasks",
    "research_versions",
    "radar",
    "company_pools",
    "opportunity_scans",
    "company_research_reports",
    "futures_fundamentals",
    "futures_tracking",
    "data_source_refreshes",
    "decision_snapshots",
    "public_drafts",
)


class WebApplicationError(ValueError):
    """Raised when a local web request is invalid."""


class ResearchWebApplication:
    """Pure application layer used by the HTTP handler and unit tests."""

    def __init__(
        self,
        data_root: str | Path = "data",
        commodity_directory: str | Path = "config/commodities",
        web_root: str | Path = "web",
    ) -> None:
        self.data_root = Path(data_root)
        self.commodity_directory = Path(commodity_directory)
        self.web_root = Path(web_root)

    def health(self) -> dict[str, Any]:
        return {
            "schema_version": WEB_API_SCHEMA_VERSION,
            "status": "READY",
            "mode": "LOCAL_ONLY",
            "data_root": str(self.data_root),
            "execution_enabled": False,
            "network_calls": 0,
            "model_calls": 0,
            "decision_snapshot_created": False,
            "publication_api_called": False,
            "policy": {
                "read_only_snapshot_index": True,
                "task_resolution_only": True,
                "no_market_fetch": True,
                "no_automatic_trade": True,
                "manual_publication_required": True,
            },
        }

    def summary(self) -> dict[str, Any]:
        snapshots = self.snapshots(limit=500)
        schema_counts = Counter(item["schema_version"] for item in snapshots)
        status_counts = Counter(item["status"] for item in snapshots)
        return {
            "schema_version": WEB_API_SCHEMA_VERSION,
            "snapshot_count": len(snapshots),
            "schema_counts": dict(sorted(schema_counts.items())),
            "status_counts": dict(sorted(status_counts.items())),
            "latest": snapshots[:10],
            "execution_enabled": False,
        }

    def snapshots(self, *, limit: int = 100) -> list[dict[str, Any]]:
        if limit < 1 or limit > 500:
            raise WebApplicationError("limit must be between 1 and 500")
        records: list[dict[str, Any]] = []
        for directory_name in _SNAPSHOT_DIRS:
            directory = self.data_root / directory_name
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
                record = self._snapshot_metadata(path, directory_name)
                if record is not None:
                    records.append(record)
        records.sort(key=lambda item: item["modified_at"], reverse=True)
        return records[:limit]

    def resolve_task(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise WebApplicationError("request body must be a JSON object")
        input_text = str(payload.get("input") or payload.get("query") or "").strip()
        if not input_text:
            raise WebApplicationError("input is required")
        task = resolve_research_task(
            payload,
            task_type=str(payload.get("task_type") or ""),
            subject_type=str(payload.get("subject_type") or ""),
            research_as_of=str(payload.get("research_as_of") or payload.get("as_of") or ""),
            requested_depth=str(payload.get("requested_depth") or "STANDARD"),
            simulation_mode=bool(payload.get("simulation_mode", True)),
            confirmed=bool(payload.get("confirmed", False)),
            commodity_definitions=self._commodity_definitions(),
        )
        task_path = self.data_root / "research_tasks" / f"{task['task_id']}.json"
        task_path.parent.mkdir(parents=True, exist_ok=True)
        if task_path.exists():
            try:
                existing = json.loads(task_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise WebApplicationError(f"existing task cannot be read: {error}") from error
            if existing.get("content_hash") != task.get("content_hash"):
                raise WebApplicationError("existing task has a different content hash")
            task = existing
            persisted = True
        else:
            try:
                task_path.write_text(
                    json.dumps(task, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            except OSError as error:
                raise WebApplicationError(f"task cannot be persisted: {error}") from error
            persisted = True
        return {
            "schema_version": WEB_API_SCHEMA_VERSION,
            "task": task,
            "task_path": str(task_path),
            "persisted": persisted,
            "execution_enabled": False,
        }

    def get(self, path: str, query: dict[str, list[str]] | None = None) -> tuple[int, dict[str, Any]] | tuple[int, bytes, str]:
        parsed = urlparse(path)
        route = parsed.path
        query = query or parse_qs(parsed.query)
        if route == "/api/health":
            return HTTPStatus.OK, self.health()
        if route == "/api/summary":
            return HTTPStatus.OK, self.summary()
        if route == "/api/snapshots":
            raw_limit = (query.get("limit") or ["100"])[0]
            try:
                limit = int(raw_limit)
            except ValueError as error:
                raise WebApplicationError("limit must be an integer") from error
            return HTTPStatus.OK, {
                "schema_version": WEB_API_SCHEMA_VERSION,
                "snapshots": self.snapshots(limit=limit),
                "execution_enabled": False,
            }
        return self.static(route)

    def post(self, route: str, payload: Any) -> tuple[int, dict[str, Any]]:
        if urlparse(route).path == "/api/resolve-task":
            return HTTPStatus.OK, self.resolve_task(payload)
        raise WebApplicationError("unknown POST endpoint")

    def static(self, route: str) -> tuple[int, bytes, str]:
        relative = "index.html" if route in {"", "/"} else route.lstrip("/")
        candidate = (self.web_root / relative).resolve()
        root = self.web_root.resolve()
        if root != candidate and root not in candidate.parents:
            raise WebApplicationError("static path is outside web root")
        if not candidate.is_file():
            raise WebApplicationError("static file not found")
        content_type = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
        }.get(candidate.suffix, "application/octet-stream")
        return HTTPStatus.OK, candidate.read_bytes(), content_type

    def _commodity_definitions(self) -> list[dict[str, Any]]:
        definitions: list[dict[str, Any]] = []
        if not self.commodity_directory.is_dir():
            return definitions
        for path in sorted(self.commodity_directory.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                definitions.append(payload)
        return definitions

    def _snapshot_metadata(self, path: Path, directory_name: str) -> dict[str, Any] | None:
        try:
            if path.stat().st_size > _MAX_SNAPSHOT_BYTES:
                return None
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        identifier = next(
            (
                str(payload.get(key) or "").strip()
                for key in (
                    "task_id",
                    "report_id",
                    "snapshot_id",
                    "scan_id",
                    "version_id",
                    "tracking_id",
                    "refresh_id",
                    "decision_snapshot_id",
                    "public_draft_id",
                )
                if str(payload.get(key) or "").strip()
            ),
            path.stem,
        )
        review = payload.get("review") if isinstance(payload.get("review"), dict) else {}
        status = str(
            payload.get("status")
            or payload.get("state")
            or review.get("status")
            or "UNKNOWN"
        )
        return {
            "id": identifier,
            "directory": directory_name,
            "path": str(path),
            "schema_version": str(payload.get("schema_version") or "UNKNOWN"),
            "status": status,
            "as_of": str(payload.get("as_of") or payload.get("research_as_of") or ""),
            "modified_at": path.stat().st_mtime,
            "review_only": payload.get("review_only") is True,
            "execution_enabled": payload.get("execution_enabled") is True,
            "investment_conclusion": payload.get("investment_conclusion") is True,
        }


class _RequestHandler(BaseHTTPRequestHandler):
    application: ResearchWebApplication

    def do_GET(self) -> None:  # noqa: N802
        try:
            result = self.application.get(self.path)
            if len(result) == 2:
                status, payload = result
                self._json(status, payload)
            else:
                status, content, content_type = result
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
        except (OSError, WebApplicationError, TaskResolutionError) as error:
            self._error(HTTPStatus.BAD_REQUEST, str(error))

    def do_POST(self) -> None:  # noqa: N802
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length < 0 or content_length > _MAX_BODY_BYTES:
                raise WebApplicationError("request body exceeds 512 KiB")
            raw = self.rfile.read(content_length)
            payload = json.loads(raw.decode("utf-8"))
            status, response = self.application.post(self.path, payload)
            self._json(status, response)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, WebApplicationError, TaskResolutionError) as error:
            self._error(HTTPStatus.BAD_REQUEST, str(error))

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def _json(self, status: int, payload: Any) -> None:
        content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _error(self, status: int, message: str) -> None:
        self._json(status, {"error": message, "execution_enabled": False})


def run_web_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    data_root: str | Path = "data",
    commodity_directory: str | Path = "config/commodities",
    web_root: str | Path = "web",
) -> None:
    application = ResearchWebApplication(
        data_root=data_root,
        commodity_directory=commodity_directory,
        web_root=web_root,
    )
    handler = type(
        "ResearchWebRequestHandler",
        (_RequestHandler,),
        {"application": application},
    )
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Industry First Research web console: http://{host}:{port}")
    print("LOCAL_ONLY; execution_enabled=false; press Ctrl-C to stop")
    try:
        server.serve_forever()
    finally:
        server.server_close()
