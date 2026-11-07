TELUGU WIKIPEDIA POSITIONAL INVERTED INDEX
Information Retrieval Assignment 1 - Post-Index (M2026)
Roll number: S20240010101
GitHub repository: https://github.com/KanekiKen-hub/IR-Assignement

1. PROJECT DESCRIPTION AND OBJECTIVES

This project streams Telugu Wikipedia articles from a compressed MediaWiki
XML dump, cleans their Wikitext, tokenizes Telugu Unicode text, and builds a
positional inverted index. It records each term's positions within documents,
its collection frequency (CF), and its document frequency (DF). The disk-based
index keeps vocabulary metadata in memory and stores complete postings on
secondary storage for on-demand retrieval.

The project also retains a separate, legacy in-memory Reuters search
demonstration. That demonstration is not part of the Telugu Wikipedia indexing
pipeline.

Objectives:
- Process a compressed Wikipedia dump without extracting an uncompressed copy.
- Preserve Wikipedia page IDs as document IDs.
- Normalize and tokenize Telugu text while retaining token order.
- Build and validate a positional index with CF and DF.
- Store postings on disk and load vocabulary metadata in main memory.
- Search terms and inspect their statistics and positional postings.

2. DATASET

The Telugu pipeline expects the compressed pages-articles dump named:

    tewiki-latest-pages-articles.xml.bz2

The loader streams bzip2-compressed MediaWiki XML and selects non-empty,
non-redirect pages in the main namespace. The verified local index described
in the project README was built from the first 10,000 valid articles. This is
a subset, not the complete Telugu Wikipedia corpus.

The existing project documentation does not provide a dataset download URL
or a generated-index download URL. No external link is supplied here. The
compressed dataset and generated index are local artifacts, not included in
this submission.

3. SYSTEM REQUIREMENTS

- Python 3.10 or later.
- Windows PowerShell commands below assume the project files have been
  extracted into a folder.
- Internet access is needed to install Python packages. Building or opening
  the Telugu Wikipedia index does not require the Reuters corpus.
- The legacy Reuters demonstration additionally requires the NLTK Reuters
  corpus to be available through NLTK.

4. INSTALLATION AND DEPENDENCIES

Open PowerShell in the extracted project folder and run:

    py -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install -r requirements.txt

requirements.txt declares:
- mwparserfromhell >=0.7,<1 (MediaWiki Wikitext parsing)
- pytest >=8.0,<9 (automated tests)
- nltk >=3.8.1,<4 (legacy Reuters demo)

The index pipeline otherwise uses Python standard-library modules, including
bz2, XML parsing, SQLite, JSON, temporary files, heap-based merging, Unicode
normalization, and hashing.

5. BUILD THE POSITIONAL INDEX

Place tewiki-latest-pages-articles.xml.bz2 in the project root. To build the
documented 10,000-valid-article subset, verify all postings, and then enter
interactive term searches:

    python -X utf8 main.py --dump .\tewiki-latest-pages-articles.xml.bz2 --limit 10000 --storage .\storage --verify

The --limit value counts valid yielded articles, not every XML page scanned.
The default limit is 5,000 if --limit is omitted. The builder writes a
generation under storage and publishes it through storage\current.json.
Previous generations are not deleted by the builder.

6. LOAD AN EXISTING INDEX AND SEARCH

With an already-built index in storage, open it without rebuilding:

    python -X utf8 main.py --load-existing --storage .\storage

To verify all postings while opening the existing index:

    python -X utf8 main.py --load-existing --storage .\storage --verify

At the prompt, type one Telugu term, such as తెలుగు, to display its DF, CF,
and postings; type q to exit. The CLI prints all postings for the requested
term, so common terms may produce extensive output.

The Python API can also open an existing index and inspect a term:

    from src.storage_manager import StorageManager

    index = StorageManager("storage")
    term = "తెలుగు"
    statistics = index.get_term_statistics(term)
    print("Statistics:", statistics)
    if statistics is not None:
        print("Sample postings:", dict(list(index.get_postings(term).items())[:5]))

Run the complete test suite from the project root:

    python -m pytest -q

The documented project state passed 95 tests.

7. SOURCE MODULES

Top-level and helper files:
- main.py: command-line entry points for the legacy Reuters workflow and the
  Telugu Wikipedia index build/load/search workflow.
- scripts\download_dataset.py: legacy Reuters corpus download helper; not
  required to build the Telugu Wikipedia index.
- requirements.txt: supported dependency ranges for the project and tests.

src modules:
- src\__init__.py: marks src as a Python package.
- src\dataset_loader.py: lazy access to documents and metadata in the NLTK
  Reuters corpus.
- src\disk_index_builder.py: constructs the disk-backed positional index
  using bounded buffers, sorted temporary runs, external merging, and
  generation publication.
- src\evaluation.py: legacy Reuters index statistics, query timings, storage
  estimates, and consistency checks.
- src\index_builder.py: builds the in-memory positional reference index from
  document IDs and token sequences.
- src\inverted_index.py: in-memory term-to-document index used by the legacy
  Reuters search workflow.
- src\positional_index.py: in-memory reference positional index with term
  positions and CF/DF statistics.
- src\preprocessor.py: NFC normalization, lowercasing, and Unicode-aware
  tokenization while preserving token order.
- src\search_engine.py: legacy Reuters single-term, Boolean, and phrase
  retrieval over the in-memory indexes.
- src\storage_manager.py: loads vocabulary metadata and statistics, validates
  index files, and retrieves/checks positional postings from disk.
- src\wikipedia_dataset_loader.py: incrementally streams and filters pages
  from the compressed Wikipedia XML dump.
- src\wikitext_cleaner.py: converts MediaWiki Wikitext to normalized readable
  text for indexing.

8. POSITIONAL INVERTED INDEX, CF, AND DF

For each processed document, tokens retain their source order. A token's
position is its zero-based index in that ordered token sequence. A term's
postings associate document IDs with all positions where the term occurs.
Repeated occurrences in a document are all represented.

- CF (collection frequency) is the total number of occurrences of a term
  across all indexed documents.
- DF (document frequency) is the number of distinct indexed documents that
  contain the term.
- Document IDs in the Wikipedia index are the original Wikipedia page IDs.

For the processed sequence ["తెలుగు", "భాష", "తెలుగు"], the postings are:

    తెలుగు -> document:[0, 2]
    భాష    -> document:[1]

9. DISK STORAGE AND EXTERNAL SORTING

The builder groups each article's token positions by term and accumulates
term/document/positions records in a buffer capped by a configurable record
count (50,000 by default). Full buffers are sorted by term and document ID
and flushed to temporary runs. The runs are merged externally with a maximum
fan-in of 32 files per merge operation, using multiple merge levels when
needed. Duplicate document IDs are tracked in temporary SQLite storage.

The final merge writes postings sequentially to postings.bin. Each vocabulary
entry records CF, DF, the postings record's byte offset and byte length, and a
SHA-256 checksum. StorageManager loads the vocabulary metadata into main
memory, but does not load the complete postings file. It seeks to the stored
offset, reads the stored length, decodes the record, and validates its
checksum and CF/DF. A term lookup returns that term's complete postings.

The record-count buffer bounds record count rather than total bytes. A large
article and the in-memory vocabulary still affect peak memory; vocabulary
memory is proportional to the number of unique terms.

10. VERIFIED INDEX INFORMATION

The existing README reports these measurements for the verified local
10,000-article subset (not the full Telugu Wikipedia corpus):

- 10,000 valid documents; 12,911 XML pages encountered.
- 2,218 non-main-namespace pages and 693 redirects skipped; no empty
  articles encountered before reaching the limit.
- 4,916,974 token occurrences and 303,366 unique vocabulary terms.
- postings.bin: 127,229,948 bytes.
- vocabulary.json: 45,875,367 bytes.
- Combined index files: 173,105,315 bytes.
- Build time: 367.4 seconds; full verification: 106.48 seconds; total:
  473.88 seconds.
- Estimated retained vocabulary object memory: 127,273,556 bytes.
- Peak process RSS: 539,963,392 bytes.
- Peak temporary build data: 312,597,685 bytes.

These are measurements from the documented completed local build. Build time,
verification time, and memory use depend on machine load and environment. The
vocabulary-memory figure estimates retained Python vocabulary objects; RSS is
the measured process working-set peak.

11. SAMPLE SEARCH OUTPUT

The following is a documented excerpt from an actual search of the existing
10,000-article index. These sample postings are abbreviated; the CLI prints
the complete postings for the requested term.

    Term: తెలుగు
    DF: 3251
    CF: 6806
    Sample postings: {'1': [7], '10050': [68], '10085': [189, 207, 215, 279]}

Other documented term statistics include:
- భారతదేశం: CF 447, DF 222.
- ఆంధ్రప్రదేశ్: CF 1,714, DF 1,008.
- కంప్యూటర్: CF 131, DF 64.

12. TEST FILES

The tests folder contains:
- tests\test_dataset_loader.py
- tests\test_disk_index.py
- tests\test_evaluation.py
- tests\test_inverted_index.py
- tests\test_main.py
- tests\test_positional_index.py
- tests\test_preprocessor.py
- tests\test_search_engine.py
- tests\test_wikipedia_dataset_loader.py
- tests\test_wikitext_cleaner.py

The tests cover preprocessing, Wikitext cleaning, XML loading, in-memory
indexing, disk serialization and retrieval, checksums, generation publication,
and command-line behavior.

13. LIMITATIONS

- The documented disk index covers 10,000 valid articles only.
- The Telugu disk-index CLI supports single-term CF/DF and postings
  inspection. Boolean and phrase search are implemented in the separate
  legacy in-memory Reuters workflow, not on the Telugu disk index.
- The local compressed dump and generated index are not included in this
  source submission. Build the index using the command in section 5 and a
  locally available dump.
