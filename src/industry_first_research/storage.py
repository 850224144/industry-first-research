"""Small local JSON snapshot store; it stores decisions and metadata, not market dumps."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SnapshotExistsError(FileExistsError):
    """Raised when an immutable snapshot ID already exists."""


class JsonSnapshotStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def write(self, snapshot_id: str, payload: dict[str, Any]) -> Path:
        target = self.root / f"{snapshot_id}.json"
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return target

    def write_immutable(self, snapshot_id: str, payload: dict[str, Any]) -> Path:
        """Write once; callers must create a new ID for a new historical version."""

        target = self.root / f"{snapshot_id}.json"
        if target.exists():
            raise SnapshotExistsError(
                f"immutable snapshot already exists: {target}; use a new versioned ID"
            )
        return self.write(snapshot_id, payload)

    def read(self, snapshot_id: str) -> dict[str, Any]:
        target = self.root / f"{snapshot_id}.json"
        return json.loads(target.read_text(encoding="utf-8"))
