import pytest

from industry_first_research.storage import (
    ArtifactSnapshotError,
    ImmutableFileExistsError,
    JsonSnapshotStore,
    SnapshotExistsError,
    SnapshotIdError,
    write_files_immutable,
    write_text_immutable,
)


def test_immutable_snapshot_uses_atomic_create_and_cannot_be_rewritten(tmp_path):
    store = JsonSnapshotStore(tmp_path)
    first = {"schema_version": "test-artifact.v1", "value": 1}
    second = {"schema_version": "test-artifact.v1", "value": 2}

    store.write_artifact("artifact-001", first)

    with pytest.raises(SnapshotExistsError, match="already exists"):
        store.write_artifact("artifact-001", second)
    assert store.read("artifact-001") == first


def test_immutable_snapshot_accepts_exact_content_replay(tmp_path):
    store = JsonSnapshotStore(tmp_path)
    payload = {"schema_version": "test-artifact.v1", "value": 1}

    first = store.write_artifact("artifact-001", payload)
    second = store.write_artifact("artifact-001", payload)

    assert first == second
    assert store.read("artifact-001") == payload


def test_artifact_store_requires_schema_version(tmp_path):
    store = JsonSnapshotStore(tmp_path)

    with pytest.raises(ArtifactSnapshotError, match="schema_version"):
        store.write_artifact("artifact-001", {"value": 1})


def test_snapshot_id_cannot_escape_store(tmp_path):
    store = JsonSnapshotStore(tmp_path)

    with pytest.raises(SnapshotIdError, match="snapshot_id"):
        store.write("../outside", {"value": 1})


def test_mutable_write_remains_available_for_scheduler_state(tmp_path):
    store = JsonSnapshotStore(tmp_path)

    store.write("state-daily", {"status": "PENDING"})
    store.write("state-daily", {"status": "DONE"})

    assert store.read("state-daily")["status"] == "DONE"


def test_immutable_text_file_cannot_be_overwritten(tmp_path):
    path = tmp_path / "report.md"
    write_text_immutable(path, "first\n")

    with pytest.raises(ImmutableFileExistsError, match="already exists"):
        write_text_immutable(path, "second\n")
    assert path.read_text(encoding="utf-8") == "first\n"


def test_immutable_text_file_accepts_exact_content_replay(tmp_path):
    path = tmp_path / "report.md"

    first = write_text_immutable(path, "same\n")
    second = write_text_immutable(path, "same\n")

    assert first == second == path
    assert path.read_text(encoding="utf-8") == "same\n"


def test_immutable_file_bundle_rolls_back_new_files_on_conflict(tmp_path):
    existing = tmp_path / "report.html"
    existing.write_text("existing", encoding="utf-8")
    markdown = tmp_path / "report.md"

    with pytest.raises(ImmutableFileExistsError, match="already exists"):
        write_files_immutable(
            (
                (markdown, b"new markdown"),
                (existing, b"new html"),
            )
        )

    assert not markdown.exists()
    assert existing.read_text(encoding="utf-8") == "existing"
