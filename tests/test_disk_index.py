import json
from pathlib import Path

import pytest

import src.disk_index_builder as disk_index_builder
from src.disk_index_builder import build_disk_index
from src.storage_manager import StorageManager


def test_disk_index_persists_unicode_positions_and_cf_df(tmp_path):
    documents = [
        ("786", ["తెలుగు", "భాష", "తెలుగు"]),
        ("787", ["తెలుగు", "తెలుగు", "భాష"]),
    ]

    stats = build_disk_index(
        documents,
        tmp_path / "index",
        buffer_record_limit=1,
    )
    index = StorageManager(tmp_path / "index")

    assert stats.documents_processed == 2
    assert stats.total_tokens == 6
    assert stats.total_occurrences == 6
    assert stats.vocabulary_size == 2
    assert stats.temporary_bytes_peak >= (
        stats.postings_file_bytes + stats.vocabulary_file_bytes
    )
    assert index.get_term_statistics("తెలుగు") == {"df": 2, "cf": 4}
    assert index.get_postings("తెలుగు") == {"786": [0, 2], "787": [0, 1]}
    assert index.get_term_statistics("భాష") == {"df": 2, "cf": 2}
    assert index.get_postings("భాష") == {"786": [1], "787": [2]}
    assert index.verify() == {
        "valid": True,
        "terms_verified": 2,
        "occurrences_verified": 6,
        "documents": 2,
    }


def test_disk_index_merges_multiple_passes_and_cleans_temporary_runs(
    tmp_path,
    monkeypatch,
):
    documents = [
        (f"doc-{number:04d}", [f"పదం{number:04d}"])
        for number in range(1025)
    ]
    storage_dir = tmp_path / "index"
    opened_run_batch_sizes = []
    actual_open_runs = disk_index_builder._open_runs

    def observe_run_opening(paths):
        opened_run_batch_sizes.append(len(paths))
        return actual_open_runs(paths)

    monkeypatch.setattr(
        disk_index_builder,
        "_open_runs",
        observe_run_opening,
    )
    stats = build_disk_index(documents, storage_dir, buffer_record_limit=1)

    index = StorageManager(storage_dir)

    assert stats.temporary_run_count > 32 * 32
    assert stats.buffer_records_peak == 1
    assert max(opened_run_batch_sizes) <= disk_index_builder._MERGE_FAN_IN
    assert index.document_count == 1025
    assert index.get_postings("పదం0000") == {"doc-0000": [0]}
    assert list((storage_dir / "temp").iterdir()) == []


def test_term_lookup_reads_only_its_postings_record(tmp_path):
    documents = [
        (f"doc-{number:03d}", ["తెలుగు"] * 20 + ["చిన్న"])
        for number in range(50)
    ]
    storage_dir = tmp_path / "index"
    build_disk_index(documents, storage_dir)
    index = StorageManager(storage_dir)

    assert index.get_term_statistics("చిన్న") == {"df": 50, "cf": 50}
    assert index.postings_read_count == 0
    assert index.get_postings("చిన్న")["doc-000"] == [20]
    assert index.last_postings_bytes_read < index.postings_path.stat().st_size
    assert index.postings_read_count == 1


def test_failed_build_preserves_previous_index(tmp_path):
    storage_dir = tmp_path / "index"
    build_disk_index([("doc-1", ["పాత"])], storage_dir)

    with pytest.raises(ValueError, match="Duplicate document ID"):
        build_disk_index(
            [("doc-2", ["కొత్త"]), ("doc-2", ["పదం"])],
            storage_dir,
            buffer_record_limit=1,
        )

    index = StorageManager(storage_dir)
    assert index.get_term_statistics("పాత") == {"df": 1, "cf": 1}
    assert index.get_term_statistics("కొత్త") is None
    assert list((storage_dir / "temp").iterdir()) == []


def test_storage_manager_rejects_mismatched_build_files(tmp_path):
    storage_dir = tmp_path / "index"
    build_disk_index([("doc-1", ["తెలుగు"])], storage_dir)
    index = StorageManager(storage_dir)
    vocabulary_path = index.vocabulary_path
    data = json.loads(vocabulary_path.read_text(encoding="utf-8"))
    data["index_id"] = "0" * 32
    vocabulary_path.write_text(
        json.dumps(data, ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="different builds"):
        StorageManager(storage_dir)


def test_empty_index_is_valid_and_unknown_terms_are_empty(tmp_path):
    storage_dir = tmp_path / "index"
    stats = build_disk_index([("empty-document", [])], storage_dir)
    index = StorageManager(storage_dir)

    assert stats.documents_processed == 1
    assert stats.total_tokens == 0
    assert index.document_count == 1
    assert index.unique_term_count == 0
    assert index.get_postings("తెలుగు") == {}
    assert index.verify()["valid"] is True


def test_progress_status_reports_vocabulary_runs_and_postings(tmp_path):
    reports = []
    stats = build_disk_index(
        [("1", ["తెలుగు", "భాష"]), ("2", ["తెలుగు"])],
        tmp_path / "index",
        buffer_record_limit=10,
        status_callback=reports.append,
        progress_interval=1,
    )

    reading = [report for report in reports if report.stage == "reading"]
    merging = [report for report in reports if report.stage == "merging"]
    assert reading
    assert max(report.vocabulary_size for report in reading) == 2
    assert merging
    assert merging[-1].postings_bytes > 0
    assert stats.temporary_bytes_peak >= merging[-1].temporary_bytes


def test_open_and_lookup_read_only_header_and_requested_record(tmp_path, monkeypatch):
    storage_dir = tmp_path / "index"
    build_disk_index(
        [("1", ["తెలుగు"]), ("2", ["భాష"])],
        storage_dir,
    )
    index = StorageManager(storage_dir)
    expected_record_length = int(index.vocabulary["తెలుగు"]["length"])
    reads = []
    original_open = Path.open

    class TrackedFile:
        def __init__(self, wrapped):
            self.wrapped = wrapped

        def __enter__(self):
            self.wrapped.__enter__()
            return self

        def __exit__(self, *args):
            return self.wrapped.__exit__(*args)

        def read(self, size=-1):
            reads.append(size)
            return self.wrapped.read(size)

        def __getattr__(self, name):
            return getattr(self.wrapped, name)

    def tracked_open(path, *args, **kwargs):
        opened = original_open(path, *args, **kwargs)
        if path.name == "postings.bin":
            return TrackedFile(opened)
        return opened

    monkeypatch.setattr(Path, "open", tracked_open)
    reopened = StorageManager(storage_dir)
    assert reads == [len(b"TELUGU-POSITIONAL-INDEX 1 ") + 32 + 1]
    reads.clear()
    assert reopened.get_postings("తెలుగు") == {"1": [0]}
    assert reads == [expected_record_length]


def test_reopening_preserves_stats_and_postings(tmp_path):
    storage_dir = tmp_path / "index"
    build_disk_index(
        [("786", ["తెలుగు", "భాష", "తెలుగు"]), ("787", ["తెలుగు"])],
        storage_dir,
        buffer_record_limit=1,
    )

    first = StorageManager(storage_dir)
    second = StorageManager(storage_dir)
    assert second.get_term_statistics("తెలుగు") == first.get_term_statistics("తెలుగు")
    assert second.get_postings("తెలుగు") == first.get_postings("తెలుగు")
    assert second.verify() == first.verify()


def test_record_checksum_detects_same_length_corruption(tmp_path):
    storage_dir = tmp_path / "index"
    build_disk_index([("doc-1", ["తెలుగు"])], storage_dir)
    index = StorageManager(storage_dir)
    data = index.postings_path.read_bytes()
    offset = int(index.vocabulary["తెలుగు"]["offset"])
    record_length = int(index.vocabulary["తెలుగు"]["length"])
    record = data[offset : offset + record_length]
    corrupted = record.replace(b"[0]", b"[9]")
    assert len(corrupted) == len(record)
    index.postings_path.write_bytes(
        data[:offset] + corrupted + data[offset + record_length :]
    )

    with pytest.raises(ValueError, match="checksum mismatch"):
        index.get_postings("తెలుగు")


def test_storage_manager_rejects_checksumless_legacy_metadata(tmp_path):
    storage_dir = tmp_path / "index"
    build_disk_index([("doc-1", ["తెలుగు"])], storage_dir)
    index = StorageManager(storage_dir)
    vocabulary_path = index.vocabulary_path
    data = json.loads(vocabulary_path.read_text(encoding="utf-8"))
    data["vocabulary"]["తెలుగు"].pop("sha256")
    vocabulary_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="rebuild the index"):
        StorageManager(storage_dir)


def test_storage_manager_rejects_overlapping_offsets_and_truncation(tmp_path):
    storage_dir = tmp_path / "index"
    build_disk_index([("doc-1", ["తెలుగు", "భాష"])], storage_dir)
    index = StorageManager(storage_dir)
    vocabulary_path = index.vocabulary_path
    metadata = json.loads(vocabulary_path.read_text(encoding="utf-8"))
    terms = list(metadata["vocabulary"])
    metadata["vocabulary"][terms[1]]["offset"] = metadata["vocabulary"][terms[0]]["offset"]
    vocabulary_path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="overlapping"):
        StorageManager(storage_dir)

    build_disk_index([("doc-1", ["తెలుగు", "భాష"])], storage_dir)
    refreshed = StorageManager(storage_dir)
    last_term = max(
        refreshed.vocabulary,
        key=lambda term: (
            int(refreshed.vocabulary[term]["offset"])
            + int(refreshed.vocabulary[term]["length"])
        ),
    )
    with refreshed.postings_path.open("r+b") as postings:
        postings.truncate(postings.seek(0, 2) - 1)
    with pytest.raises(OSError, match="Truncated postings record"):
        refreshed.get_postings(last_term)
    with pytest.raises(ValueError, match="range"):
        StorageManager(storage_dir)


def test_failed_manifest_publish_keeps_previous_generation_available(
    tmp_path,
    monkeypatch,
):
    storage_dir = tmp_path / "index"
    build_disk_index([("old", ["పాత"])], storage_dir)
    original_replace = disk_index_builder.os.replace

    def fail_manifest_replace(source, destination):
        if Path(destination).name == "current.json":
            raise OSError("simulated manifest publication failure")
        original_replace(source, destination)

    monkeypatch.setattr(disk_index_builder.os, "replace", fail_manifest_replace)
    with pytest.raises(OSError, match="manifest publication"):
        build_disk_index([("new", ["కొత్త"])], storage_dir)

    index = StorageManager(storage_dir)
    assert index.get_term_statistics("పాత") == {"df": 1, "cf": 1}
    assert index.get_term_statistics("కొత్త") is None
    assert list((storage_dir / "temp").iterdir()) == []
