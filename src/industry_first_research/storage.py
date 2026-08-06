"""Small local JSON stores for mutable state and immutable research artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


class SnapshotExistsError(FileExistsError):
    """Raised when an immutable snapshot ID already exists."""


class SnapshotIdError(ValueError):
    """Raised when a snapshot ID could escape or ambiguously name the store."""


class ArtifactSnapshotError(ValueError):
    """Raised when an unversioned payload is written as a research artifact."""


class ImmutableFileExistsError(FileExistsError):
    """Raised when a derived immutable file already exists."""


def write_bytes_immutable(path: str | Path, payload: bytes) -> Path:
    """Create one file exactly once without a check-then-write race."""

    return write_files_immutable(((path, payload),))[0]


def write_text_immutable(
    path: str | Path,
    text: str,
    *,
    encoding: str = "utf-8",
) -> Path:
    """Create one text file exactly once."""

    return write_bytes_immutable(path, text.encode(encoding))


def write_files_immutable(
    files: Iterable[tuple[str | Path, bytes]],
) -> list[Path]:
    """Create an immutable bundle, accepting exact-content replays."""

    normalized = [(Path(path), payload) for path, payload in files]
    paths = [path for path, _payload in normalized]
    if len(paths) != len(set(paths)):
        raise ValueError("immutable file bundle contains duplicate paths")
    if any(not isinstance(payload, bytes) for _path, payload in normalized):
        raise TypeError("immutable file payloads must be bytes")

    created: list[Path] = []
    try:
        for path, payload in normalized:
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with path.open("xb") as handle:
                    created.append(path)
                    handle.write(payload)
            except FileExistsError as error:
                try:
                    existing = path.read_bytes()
                except OSError as read_error:
                    raise ImmutableFileExistsError(
                        f"immutable file already exists and cannot be read: {path}"
                    ) from read_error
                if existing == payload:
                    continue
                raise ImmutableFileExistsError(
                    f"immutable file already exists with different content: {path}; "
                    "use a new versioned path"
                ) from error
    except Exception:
        for path in reversed(created):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        raise
    return paths


class JsonSnapshotStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def write(self, snapshot_id: str, payload: dict[str, Any]) -> Path:
        """Write replaceable operational state.

        Research outputs should use :meth:`write_artifact` so a rerun cannot
        silently rewrite history.
        """

        target = self._target(snapshot_id)
        return self._write(target, payload, exclusive=False)

    def write_immutable(self, snapshot_id: str, payload: dict[str, Any]) -> Path:
        """Write once, with exact-content retries treated as idempotent."""

        target = self._target(snapshot_id)
        try:
            return self._write(target, payload, exclusive=True)
        except ImmutableFileExistsError as error:
            raise SnapshotExistsError(
                f"immutable snapshot already exists: {target}; use a new versioned ID"
            ) from error

    def write_artifact(self, snapshot_id: str, payload: dict[str, Any]) -> Path:
        """Write a schema-versioned research artifact exactly once."""

        if not isinstance(payload, dict):
            raise ArtifactSnapshotError("artifact payload must be a JSON object")
        if not str(payload.get("schema_version") or "").strip():
            raise ArtifactSnapshotError(
                "immutable research artifact requires schema_version"
            )
        return self.write_immutable(snapshot_id, payload)

    def read(self, snapshot_id: str) -> dict[str, Any]:
        target = self._target(snapshot_id)
        return json.loads(target.read_text(encoding="utf-8"))

    def _target(self, snapshot_id: str) -> Path:
        identifier = str(snapshot_id or "").strip()
        if (
            not identifier
            or identifier in {".", ".."}
            or "/" in identifier
            or "\\" in identifier
            or "\x00" in identifier
        ):
            raise SnapshotIdError("snapshot_id must be a non-empty local file identifier")
        target = (self.root / f"{identifier}.json").resolve()
        try:
            target.relative_to(self.root)
        except ValueError as error:
            raise SnapshotIdError(
                "snapshot_id must stay within the snapshot store"
            ) from error
        return target

    @staticmethod
    def _write(
        target: Path, payload: dict[str, Any], *, exclusive: bool
    ) -> Path:
        text = json.dumps(
            payload, ensure_ascii=False, indent=2, sort_keys=True
        ) + "\n"
        if exclusive:
            return write_text_immutable(target, text)
        with target.open("w", encoding="utf-8") as handle:
            handle.write(text)
        return target
