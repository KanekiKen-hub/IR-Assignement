"""Build disk-backed positional indexes with bounded external sorting."""

import hashlib
import heapq
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from collections.abc import Callable, Generator, Iterable, Iterator, Sequence
from contextlib import ExitStack, closing, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO
from uuid import uuid4

from src.preprocessor import Preprocessor
from src.storage_manager import StorageManager, _POSTINGS_HEADER


ProcessedDocument = tuple[str, Sequence[str]]
_MERGE_FAN_IN = 32


@dataclass(frozen=True)
class DiskIndexBuildStats:
    documents_processed: int
    total_tokens: int
    vocabulary_size: int
    total_occurrences: int
    indexing_seconds: float
    temporary_run_count: int
    temporary_bytes_peak: int
    postings_file_bytes: int
    vocabulary_file_bytes: int
    vocabulary_memory_bytes: int
    buffer_records_peak: int


@dataclass(frozen=True)
class DiskIndexProgress:
    stage: str
    documents_processed: int
    total_tokens: int
    vocabulary_size: int
    temporary_run_count: int
    temporary_bytes: int
    postings_bytes: int


def build_disk_index(
    documents: Iterable[ProcessedDocument],
    storage_dir: str | Path,
    *,
    buffer_record_limit: int = 50_000,
    preprocessor: Preprocessor | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    status_callback: Callable[[DiskIndexProgress], None] | None = None,
    progress_interval: int = 1000,
) -> DiskIndexBuildStats:
    """Sort bounded records externally and retain only vocabulary metadata in RAM."""
    if (
        isinstance(buffer_record_limit, bool)
        or not isinstance(buffer_record_limit, int)
        or buffer_record_limit < 1
    ):
        raise ValueError("buffer_record_limit must be a positive integer.")
    if (
        isinstance(progress_interval, bool)
        or not isinstance(progress_interval, int)
        or progress_interval < 1
    ):
        raise ValueError("progress_interval must be a positive integer.")

    started_at = time.perf_counter()
    preprocessor = preprocessor or Preprocessor()
    destination = Path(storage_dir)
    destination.mkdir(parents=True, exist_ok=True)
    temp_root = destination / "temp"
    temp_root.mkdir(parents=True, exist_ok=True)
    generations_dir = destination / "generations"
    generations_dir.mkdir(parents=True, exist_ok=True)
    build_id = uuid4().hex

    document_count = 0
    total_tokens = 0
    run_count = 0
    next_run_id = 0
    active_run_bytes = 0
    temporary_bytes_peak = 0
    buffer_records_peak = 0
    current_vocabulary_size = 0
    posting_records: list[tuple[str, str, list[int]]] = []
    run_levels: list[list[Path]] = []
    vocabulary: dict[str, dict[str, int | str]] = {}

    with tempfile.TemporaryDirectory(prefix=f"build-{build_id}-", dir=temp_root) as temp:
        temp_directory = Path(temp)
        document_ids_path = temp_directory / "document-ids.sqlite3"

        def update_temporary_bytes_peak(extra_run_bytes: int = 0) -> None:
            nonlocal temporary_bytes_peak
            database_bytes = (
                document_ids_path.stat().st_size
                if document_ids_path.exists()
                else 0
            )
            temporary_bytes_peak = max(
                temporary_bytes_peak,
                database_bytes + active_run_bytes + extra_run_bytes,
            )

        def report_status(stage: str, postings_bytes: int = 0) -> None:
            if status_callback is None:
                return
            current_bytes = sum(
                path.stat().st_size
                for path in temp_directory.iterdir()
                if path.is_file()
            )
            status_callback(
                DiskIndexProgress(
                    stage=stage,
                    documents_processed=document_count,
                    total_tokens=total_tokens,
                    vocabulary_size=current_vocabulary_size
                    if stage == "reading"
                    else len(vocabulary),
                    temporary_run_count=run_count,
                    temporary_bytes=current_bytes,
                    postings_bytes=postings_bytes,
                )
            )

        def merge_batch(batch: list[Path]) -> Path:
            nonlocal run_count, next_run_id, active_run_bytes
            merged_path = temp_directory / f"merge-{next_run_id:08d}.jsonl"
            next_run_id += 1
            input_run_bytes = sum(path.stat().st_size for path in batch)
            with (
                merged_path.open("w", encoding="utf-8", newline="\n") as target,
                _open_runs(batch) as streams,
            ):
                for record in heapq.merge(
                    *(_iter_run(stream) for stream in streams),
                    key=lambda item: (item[0], item[1]),
                ):
                    target.write(
                        json.dumps(
                            record,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    )
                    target.write("\n")
            merged_run_bytes = merged_path.stat().st_size
            update_temporary_bytes_peak(merged_run_bytes)
            for path in batch:
                path.unlink()
            active_run_bytes += merged_run_bytes - input_run_bytes
            run_count += 1
            return merged_path

        def add_run(run_path: Path, level: int = 0) -> None:
            while len(run_levels) <= level:
                run_levels.append([])
            run_levels[level].append(run_path)
            if len(run_levels[level]) == _MERGE_FAN_IN:
                run_batch = run_levels[level]
                run_levels[level] = []
                add_run(merge_batch(run_batch), level + 1)

        def flush_run() -> None:
            nonlocal run_count, next_run_id, active_run_bytes
            nonlocal current_vocabulary_size, buffer_records_peak
            if not posting_records:
                return
            posting_records.sort(key=lambda item: (item[0], item[1]))
            buffer_records_peak = max(buffer_records_peak, len(posting_records))
            run_path = temp_directory / f"run-{next_run_id:08d}.jsonl"
            next_run_id += 1
            with run_path.open("w", encoding="utf-8", newline="\n") as run:
                for term, document_id, positions in posting_records:
                    run.write(
                        json.dumps(
                            [term, document_id, positions],
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    )
                    run.write("\n")
            run_bytes = run_path.stat().st_size
            active_run_bytes += run_bytes
            update_temporary_bytes_peak()
            term_cursor = tracking_db.executemany(
                "INSERT OR IGNORE INTO vocabulary_terms (term) VALUES (?)",
                ((term,) for term in {item[0] for item in posting_records}),
            )
            current_vocabulary_size += term_cursor.rowcount
            run_count += 1
            posting_records.clear()
            add_run(run_path)
            report_status("reading")

        with closing(sqlite3.connect(document_ids_path)) as tracking_db:
            tracking_db.isolation_level = None
            tracking_db.execute("PRAGMA journal_mode=OFF")
            tracking_db.execute("PRAGMA synchronous=OFF")
            tracking_db.execute("PRAGMA temp_store=FILE")
            tracking_db.execute("PRAGMA cache_size=-4096")
            tracking_db.execute(
                "CREATE TABLE document_ids (document_id TEXT PRIMARY KEY)"
            )
            tracking_db.execute(
                "CREATE TABLE vocabulary_terms (term TEXT PRIMARY KEY)"
            )

            for document_id, tokens in documents:
                if not isinstance(document_id, str) or not document_id:
                    raise ValueError("document_id must be a non-empty string.")
                try:
                    tracking_db.execute(
                        "INSERT INTO document_ids (document_id) VALUES (?)",
                        (document_id,),
                    )
                except sqlite3.IntegrityError:
                    raise ValueError(
                        f"Duplicate document ID: {document_id!r}."
                    ) from None
                document_count += 1
                update_temporary_bytes_peak()
                if any(not isinstance(token, str) or not token for token in tokens):
                    raise ValueError("tokens must contain only non-empty strings.")

                positions_by_term: dict[str, list[int]] = {}
                for position, term in enumerate(tokens):
                    positions_by_term.setdefault(term, []).append(position)
                total_tokens += len(tokens)

                for term, positions in positions_by_term.items():
                    posting_records.append((term, document_id, positions))
                    if len(posting_records) >= buffer_record_limit:
                        flush_run()
                if progress_callback is not None:
                    progress_callback(document_count, total_tokens)
                if (
                    status_callback is not None
                    and document_count % progress_interval == 0
                ):
                    flush_run()
                    report_status("reading")
                positions_by_term.clear()
                del tokens
            update_temporary_bytes_peak()
            flush_run()

        runs = [path for level in run_levels for path in level]
        while len(runs) > _MERGE_FAN_IN:
            merged_runs: list[Path] = []
            for start in range(0, len(runs), _MERGE_FAN_IN):
                run_batch = runs[start : start + _MERGE_FAN_IN]
                if len(run_batch) == 1:
                    merged_runs.append(run_batch[0])
                else:
                    merged_runs.append(merge_batch(run_batch))
            runs = merged_runs

        with _open_runs(runs) as run_streams:
            merged = heapq.merge(
                *(_iter_run(stream) for stream in run_streams),
                key=lambda record: (record[0], record[1]),
            )
            postings_temp = temp_directory / "postings.bin"
            vocabulary_temp = temp_directory / "vocabulary.json"
            with postings_temp.open("wb") as postings_file:
                postings_file.write(_POSTINGS_HEADER)
                postings_file.write(build_id.encode("ascii"))
                postings_file.write(b"\n")
                record_offset = postings_file.tell()
                current_term: str | None = None
                term_df = 0
                term_cf = 0
                first_posting = True
                record_digest: hashlib._Hash | None = None

                def write_record_bytes(data: bytes) -> None:
                    postings_file.write(data)
                    if record_digest is None:
                        raise RuntimeError("No active postings record.")
                    record_digest.update(data)

                def start_term() -> None:
                    nonlocal record_offset, term_df, term_cf
                    nonlocal first_posting, record_digest
                    record_offset = postings_file.tell()
                    term_df = 0
                    term_cf = 0
                    first_posting = True
                    record_digest = hashlib.sha256()
                    write_record_bytes(b"[")

                def write_posting(document_id: str, positions: list[int]) -> None:
                    nonlocal term_df, term_cf, first_posting
                    if not first_posting:
                        write_record_bytes(b",")
                    first_posting = False
                    payload = json.dumps(
                        {"document_id": document_id, "positions": positions},
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ).encode("utf-8")
                    write_record_bytes(payload)
                    term_df += 1
                    term_cf += len(positions)

                def finish_term(term: str) -> None:
                    nonlocal record_digest
                    write_record_bytes(b"]")
                    record_end = postings_file.tell()
                    if record_digest is None:
                        raise RuntimeError("No active postings record.")
                    vocabulary[term] = {
                        "df": term_df,
                        "cf": term_cf,
                        "offset": record_offset,
                        "length": record_end - record_offset,
                        "sha256": record_digest.hexdigest(),
                    }
                    record_digest = None
                    if status_callback is not None and len(vocabulary) % 50_000 == 0:
                        report_status("merging", postings_file.tell())

                for term, document_id, positions in merged:
                    if term != current_term:
                        if current_term is not None:
                            finish_term(current_term)
                        current_term = term
                        start_term()
                    write_posting(document_id, positions)
                if current_term is not None:
                    finish_term(current_term)
                report_status("merging", postings_file.tell())
                postings_file.flush()
                os.fsync(postings_file.fileno())

            vocabulary_document = {
                "schema_version": 1,
                "index_id": build_id,
                "document_count": document_count,
                "total_tokens": total_tokens,
                "vocabulary": vocabulary,
            }
            with vocabulary_temp.open("w", encoding="utf-8", newline="\n") as target:
                json.dump(
                    vocabulary_document,
                    target,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                target.flush()
                os.fsync(target.fileno())
        temporary_bytes_peak = max(
            temporary_bytes_peak,
            sum(
                path.stat().st_size
                for path in temp_directory.iterdir()
                if path.is_file()
            ),
        )

        vocabulary_size = len(vocabulary)
        total_occurrences = sum(
            int(metadata["cf"]) for metadata in vocabulary.values()
        )
        vocabulary_memory_bytes = _deep_size(vocabulary)
        del vocabulary_document
        del vocabulary

        generation_staging = generations_dir / f".{build_id}.tmp"
        generation_path = generations_dir / build_id
        generation_staging.mkdir()
        try:
            os.replace(postings_temp, generation_staging / "postings.bin")
            os.replace(vocabulary_temp, generation_staging / "vocabulary.json")
            StorageManager(generation_staging, preprocessor=preprocessor)
            os.replace(generation_staging, generation_path)

            manifest_temp = destination / f".current-{build_id}.tmp"
            try:
                with manifest_temp.open("w", encoding="utf-8", newline="\n") as target:
                    json.dump(
                        {
                            "schema_version": 1,
                            "index_id": build_id,
                            "generation": build_id,
                        },
                        target,
                        separators=(",", ":"),
                    )
                    target.flush()
                    os.fsync(target.fileno())
                os.replace(manifest_temp, destination / "current.json")
            finally:
                manifest_temp.unlink(missing_ok=True)
        except Exception:
            if generation_staging.exists():
                shutil.rmtree(generation_staging)
            raise

    elapsed = time.perf_counter() - started_at
    postings_path = generation_path / "postings.bin"
    vocabulary_path = generation_path / "vocabulary.json"
    return DiskIndexBuildStats(
        documents_processed=document_count,
        total_tokens=total_tokens,
        vocabulary_size=vocabulary_size,
        total_occurrences=total_occurrences,
        indexing_seconds=elapsed,
        temporary_run_count=run_count,
        temporary_bytes_peak=temporary_bytes_peak,
        postings_file_bytes=postings_path.stat().st_size,
        vocabulary_file_bytes=vocabulary_path.stat().st_size,
        vocabulary_memory_bytes=vocabulary_memory_bytes,
        buffer_records_peak=buffer_records_peak,
    )


def _iter_run(stream: TextIO) -> Iterator[tuple[str, str, list[int]]]:
    for line in stream:
        term, document_id, positions = json.loads(line)
        yield term, document_id, positions


@contextmanager
def _open_runs(paths: Sequence[Path]) -> Generator[list[TextIO], None, None]:
    if len(paths) > _MERGE_FAN_IN:
        raise ValueError("Cannot open more than the configured merge fan-in.")
    with ExitStack() as stack:
        yield [
            stack.enter_context(path.open("r", encoding="utf-8"))
            for path in paths
        ]


def _deep_size(value: object) -> int:
    pending = [value]
    seen: set[int] = set()
    total = 0
    while pending:
        current = pending.pop()
        identity = id(current)
        if identity in seen:
            continue
        seen.add(identity)
        total += sys.getsizeof(current)
        if isinstance(current, dict):
            pending.extend(current.keys())
            pending.extend(current.values())
        elif isinstance(current, (list, tuple, set, frozenset)):
            pending.extend(current)
    return total
