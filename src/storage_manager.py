"""Persist vocabulary metadata in RAM and retrieve positional records from disk."""

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from src.preprocessor import Preprocessor


_VOCABULARY_FILE = "vocabulary.json"
_POSTINGS_FILE = "postings.bin"
_MANIFEST_FILE = "current.json"
_POSTINGS_HEADER = b"TELUGU-POSITIONAL-INDEX 1 "
_BUILD_ID = re.compile(r"^[0-9a-f]{32}$")
_CHECKSUM = re.compile(r"^[0-9a-f]{64}$")


class StorageManager:
    """Keep the complete vocabulary in RAM and read postings on demand."""

    def __init__(
        self,
        storage_dir: str | Path,
        preprocessor: Preprocessor | None = None,
    ) -> None:
        self.storage_dir = Path(storage_dir)
        self._preprocessor = preprocessor or Preprocessor()
        self.last_postings_bytes_read = 0
        self.postings_read_count = 0

        manifest_path = self.storage_dir / _MANIFEST_FILE
        self.index_id: str | None = None
        if manifest_path.exists():
            with manifest_path.open("r", encoding="utf-8") as source:
                manifest = json.load(source)
            if (
                not isinstance(manifest, dict)
                or manifest.get("schema_version") != 1
            ):
                raise ValueError("Invalid index generation manifest.")
            manifest_index_id = manifest.get("index_id")
            if (
                not isinstance(manifest_index_id, str)
                or _BUILD_ID.fullmatch(manifest_index_id) is None
                or manifest.get("generation") != manifest_index_id
            ):
                raise ValueError("Invalid index generation manifest.")
            self.index_id = manifest_index_id
            self.index_dir = self.storage_dir / "generations" / self.index_id
        else:
            # Root-layout indexes are accepted only when their records are checksummed.
            self.index_dir = self.storage_dir

        self.vocabulary_path = self.index_dir / _VOCABULARY_FILE
        self.postings_path = self.index_dir / _POSTINGS_FILE
        with self.vocabulary_path.open("r", encoding="utf-8") as source:
            data = json.load(source)
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise ValueError("Unsupported or invalid vocabulary file.")

        file_index_id = data.get("index_id")
        if (
            not isinstance(file_index_id, str)
            or _BUILD_ID.fullmatch(file_index_id) is None
        ):
            raise ValueError("Invalid vocabulary index ID.")
        if self.index_id is not None and file_index_id != self.index_id:
            raise ValueError("Manifest and vocabulary refer to different builds.")
        self.index_id = file_index_id
        self.document_count = self._nonnegative_int(data, "document_count")
        self.total_tokens = self._nonnegative_int(data, "total_tokens")

        raw_vocabulary = data.get("vocabulary")
        if not isinstance(raw_vocabulary, dict):
            raise ValueError("Vocabulary metadata must be a JSON object.")
        self.vocabulary = raw_vocabulary
        ranges: list[tuple[int, int, str]] = []
        for term, metadata in raw_vocabulary.items():
            if not isinstance(term, str) or not term or not isinstance(metadata, dict):
                raise ValueError("Invalid vocabulary entry.")
            for key in ("df", "cf", "offset", "length"):
                self._metadata_int(metadata, key)
            if metadata["df"] < 1 or metadata["cf"] < metadata["df"]:
                raise ValueError(f"Inconsistent CF/DF values for term {term!r}.")
            if metadata["df"] > self.document_count:
                raise ValueError(f"DF exceeds document count for term {term!r}.")
            checksum = metadata.get("sha256")
            if not isinstance(checksum, str) or _CHECKSUM.fullmatch(checksum) is None:
                raise ValueError(
                    f"Missing or invalid postings checksum for {term!r}; rebuild the index."
                )
            metadata["sha256"] = checksum
            offset = int(metadata["offset"])
            length = int(metadata["length"])
            ranges.append((offset, offset + length, term))
        total_collection_frequency = sum(
            int(metadata["cf"]) for metadata in self.vocabulary.values()
        )
        if total_collection_frequency != self.total_tokens:
            raise ValueError("Vocabulary CF totals do not match total_tokens.")

        header_length = len(_POSTINGS_HEADER) + 32 + 1
        with self.postings_path.open("rb") as source:
            header = source.read(header_length)
            file_size = source.seek(0, os.SEEK_END)
        expected_header = _POSTINGS_HEADER + self.index_id.encode("ascii") + b"\n"
        if header != expected_header:
            raise ValueError("Vocabulary and postings files are from different builds.")

        expected_offset = header_length
        for start, end, term in sorted(ranges):
            if start != expected_offset or end <= start or end > file_size:
                raise ValueError(f"Invalid or overlapping postings range for {term!r}.")
            expected_offset = end
        if expected_offset != file_size:
            raise ValueError("Postings file contains gaps or unindexed trailing bytes.")

    @property
    def unique_term_count(self) -> int:
        return len(self.vocabulary)

    @property
    def total_token_count(self) -> int:
        return self.total_tokens

    @property
    def total_term_occurrences(self) -> int:
        return self.total_tokens

    @staticmethod
    def _nonnegative_int(data: dict[str, Any], key: str) -> int:
        value = data.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{key} must be a non-negative integer.")
        return value

    @staticmethod
    def _metadata_int(metadata: dict[str, Any], key: str) -> int:
        value = metadata.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"Vocabulary field {key!r} must be a non-negative integer.")
        return value

    def get_term_statistics(self, term: str) -> dict[str, int] | None:
        """Return CF/DF from in-memory metadata without reading postings."""
        normalized_term = self._normalize_term(term)
        metadata = self.vocabulary.get(normalized_term) if normalized_term else None
        if metadata is None:
            return None
        return {"df": int(metadata["df"]), "cf": int(metadata["cf"])}

    def get_document_frequency(self, term: str) -> int:
        statistics = self.get_term_statistics(term)
        return statistics["df"] if statistics is not None else 0

    def get_collection_frequency(self, term: str) -> int:
        statistics = self.get_term_statistics(term)
        return statistics["cf"] if statistics is not None else 0

    def get_postings(self, term: str) -> dict[str, list[int]]:
        """Seek to and deserialize only the requested term's byte range."""
        normalized_term = self._normalize_term(term)
        if normalized_term is None:
            return {}
        metadata = self.vocabulary.get(normalized_term)
        if metadata is None:
            return {}

        record_length = int(metadata["length"])
        with self.postings_path.open("rb") as source:
            source.seek(int(metadata["offset"]))
            record = source.read(record_length)
        self.last_postings_bytes_read = len(record)
        self.postings_read_count += 1
        if len(record) != record_length:
            raise OSError(f"Truncated postings record for {normalized_term!r}.")
        expected_checksum = metadata.get("sha256")
        if (
            expected_checksum is not None
            and hashlib.sha256(record).hexdigest() != expected_checksum
        ):
            raise ValueError(f"Postings checksum mismatch for {normalized_term!r}.")

        decoded = json.loads(record.decode("utf-8"))
        if not isinstance(decoded, list):
            raise ValueError(f"Invalid postings record for {normalized_term!r}.")
        postings: dict[str, list[int]] = {}
        for item in decoded:
            if not isinstance(item, dict):
                raise ValueError(f"Invalid posting entry for {normalized_term!r}.")

            document_id = item.get("document_id")
            positions = item.get("positions")
            if (
                not isinstance(document_id, str)
                or not document_id
                or not isinstance(positions, list)
                or not positions
            ):
                raise ValueError(f"Invalid positions for {normalized_term!r}.")

            if any(
                isinstance(position, bool)
                or not isinstance(position, int)
                or position < 0
                for position in positions
            ):
                raise ValueError(f"Invalid positions for {normalized_term!r}.")
            if positions != sorted(set(positions)):
                raise ValueError(f"Invalid positions for {normalized_term!r}.")
            if document_id in postings:
                raise ValueError(f"Invalid positions for {normalized_term!r}.")
            postings[document_id] = positions
        if (
            len(postings) != metadata["df"]
            or sum(map(len, postings.values())) != metadata["cf"]
        ):
            raise ValueError(f"Postings CF/DF mismatch for {normalized_term!r}.")
        return postings

    def verify(self) -> dict[str, int | bool]:
        """Read and validate each record individually."""
        verified_occurrences = 0
        for term, metadata in self.vocabulary.items():
            postings = self.get_postings(term)
            if len(postings) != metadata["df"]:
                raise ValueError(f"DF verification failed for {term!r}.")
            term_occurrences = sum(map(len, postings.values()))
            if term_occurrences != metadata["cf"]:
                raise ValueError(f"CF verification failed for {term!r}.")
            verified_occurrences += term_occurrences
        if verified_occurrences != self.total_tokens:
            raise ValueError("Total token count does not match postings.")
        return {
            "valid": True,
            "terms_verified": len(self.vocabulary),
            "occurrences_verified": verified_occurrences,
            "documents": self.document_count,
        }

    def _normalize_term(self, term: str) -> str | None:
        tokens = self._preprocessor.process(term)
        return tokens[0] if len(tokens) == 1 else None
