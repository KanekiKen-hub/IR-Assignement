# Telugu Wikipedia Positional Inverted Index

This Information Retrieval project builds a disk-based positional inverted
index for Telugu Wikipedia articles. It streams and cleans compressed
Wikipedia Wikitext, tokenizes Telugu text, and uses bounded external sorting
to construct postings without holding the complete postings list in memory.
The verified local index covers the first **10,000 valid articles**, containing
**4,916,974 token occurrences** and **303,366 vocabulary terms**. Each term has
collection frequency (CF) and document frequency (DF) statistics. Vocabulary
metadata is loaded into memory when the index is opened; positional postings
are stored on disk and retrieved by byte offset.

The repository also contains a separate legacy in-memory Reuters search
demonstration. It is not part of the Telugu Wikipedia indexing pipeline.

## Dataset and indexed subset

The Telugu pipeline uses the compressed pages-articles dump:

```text
tewiki-latest-pages-articles.xml.bz2
```

The loader streams the bzip2-compressed MediaWiki XML directly. It yields
non-empty, non-redirect pages in the main namespace, retaining the Wikipedia
page ID as the document ID. It does not extract a second uncompressed copy of
the dump. The dump and generated index files are excluded from Git by
`.gitignore`.

The verified local index contains the first **10,000 valid articles** from the
dump. It is not an index of the entire eligible dataset of **130,248 articles**.
The actual build encountered 12,911 XML pages while finding those 10,000 valid
articles: 2,218 non-main-namespace pages and 693 redirects were skipped; no
empty articles were encountered before the limit was reached.

The official Wikimedia dump index is
<https://dumps.wikimedia.org/tewiki/latest/>. Download the
`tewiki-latest-pages-articles.xml.bz2` pages-articles file from that index and
place it in the repository root. If it is already present, verify its location
in PowerShell with:

```powershell
Get-Item .\tewiki-latest-pages-articles.xml.bz2
```

No separate dataset or generated-index download URL is provided by this
project. The index can be regenerated locally from the dump using the build
command below.

## Technologies

- Python 3.10 or later
- `mwparserfromhell` for structured MediaWiki markup parsing
- Python standard library: `bz2`, `xml.etree.ElementTree`, SQLite, JSON,
  temporary files, heap-based merging, Unicode normalization, and hashing
- `pytest` for automated tests
- `nltk` for the retained Reuters demo only

Install dependencies from the repository root in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

`requirements.txt` pins the supported major-version ranges for NLTK, pytest,
and mwparserfromhell. Building or opening the Wikipedia index does not require
downloading the Reuters corpus. The Reuters demo requires its NLTK Reuters
corpus to be available.

## Project structure

```text
.
├── main.py
├── requirements.txt
├── scripts/
│   └── download_dataset.py       # Legacy Reuters corpus download/check helper
├── src/
│   ├── __init__.py
│   ├── dataset_loader.py
│   ├── disk_index_builder.py
│   ├── evaluation.py
│   ├── index_builder.py
│   ├── inverted_index.py
│   ├── positional_index.py
│   ├── preprocessor.py
│   ├── search_engine.py
│   ├── storage_manager.py
│   ├── wikipedia_dataset_loader.py
│   └── wikitext_cleaner.py
└── tests/
    ├── test_dataset_loader.py
    ├── test_disk_index.py
    ├── test_evaluation.py
    ├── test_inverted_index.py
    ├── test_main.py
    ├── test_positional_index.py
    ├── test_preprocessor.py
    ├── test_search_engine.py
    ├── test_wikipedia_dataset_loader.py
    └── test_wikitext_cleaner.py
```

The generated `storage/` directory is local, ignored output. Its current
generation is selected by `storage/current.json`; each generation contains
`vocabulary.json` and `postings.bin`.

### Module responsibilities

- `main.py`: command-line application for building or opening the Telugu
  disk index and for the separate Reuters in-memory search demonstration. Its
  Telugu prompt tokenizes a multi-word query and displays each term's
  statistics and postings independently.
- `src/__init__.py`: marks `src` as a Python package.
- `src/wikipedia_dataset_loader.py`: incrementally reads the compressed
  MediaWiki XML dump and yields eligible main-namespace pages with Wikipedia
  page IDs.
- `src/wikitext_cleaner.py`: parses Wikitext, removes or renders markup as
  appropriate, and returns normalized readable text.
- `src/preprocessor.py`: applies NFC normalization and lowercasing and
  tokenizes Unicode text in source order.
- `src/positional_index.py`: in-memory reference positional index that tracks
  term positions, CF, and DF.
- `src/index_builder.py`: builds the in-memory positional reference index
  from document IDs and already-tokenized documents.
- `src/disk_index_builder.py`: builds the large disk-backed positional
  index using bounded buffers, sorted runs, and external merging.
- `src/storage_manager.py`: loads vocabulary metadata, validates the
  generation and postings ranges, and retrieves individual checksummed
  postings records from disk.
- `src/dataset_loader.py`: lazily loads Reuters corpus documents.
- `src/inverted_index.py`: in-memory term-to-document index used by Reuters.
- `src/search_engine.py`: single-term, Boolean, and phrase retrieval for the
  Reuters in-memory indexes; it does not power Telugu disk-index query
  evaluation.
- `src/evaluation.py`: Reuters in-memory index measurements and correctness
  checks.
- `scripts/download_dataset.py`: downloads/checks the NLTK Reuters corpus; it
  does not download the Telugu Wikipedia dump.
- `tests/`: automated tests for the modules and CLI workflows.

## Processing and storage architecture

```mermaid
flowchart TD
    A[Compressed Wikipedia XML] -->|streaming bzip2 and XML parsing| B[WikipediaDatasetLoader]
    B -->|page ID, title, raw Wikitext| C[WikipediaTextCleaner]
    C --> D[Telugu Preprocessor]
    D -->|ordered token sequence| E[Bounded term-document record buffer]
    E -->|sort and flush| F[Temporary sorted runs]
    F -->|bounded fan-in merge| G[Sequential postings writer]
    G --> H[(postings.bin on disk)]
    G --> I[Vocabulary metadata: CF, DF, byte offset, length, checksum]
    I --> J[vocabulary.json on disk]
    J --> K[StorageManager loads vocabulary into RAM]
    K -->|seek and read requested byte range| H
```

### Loading and cleaning

`WikipediaDatasetLoader` uses incremental XML parsing over the bzip2 stream.
It filters non-main-namespace pages, redirects, and empty text and yields each
eligible page with its stable Wikipedia page ID, title, and raw Wikitext.

`WikipediaTextCleaner` parses Wikitext and handles common markup, including
internal and external links, references, headings, formatting, categories,
file/image markup, tables, HTML entities, and tags. It retains readable text
where appropriate and normalizes whitespace and Unicode to NFC.

`Preprocessor` applies NFC normalization and lowercasing, then emits tokens in
source order. Unicode letters and numbers are retained; combining marks remain
attached to a preceding token. Punctuation, underscores, and whitespace are
separators. Telugu stop words are not removed by default, and no English
stemming is applied.

### Positional postings, CF, and DF

For each token in the processed sequence, its zero-based list index is the
token position. Repeated terms receive all of their positions in that
document.

- **CF (collection frequency):** total occurrences of a term across the
  indexed documents.
- **DF (document frequency):** number of distinct indexed documents containing
  that term.
- **Document ID:** the original Wikipedia page ID provided by the loader.
- **Position:** zero-based index in the preprocessor's ordered token sequence.

For example, the processed tokens `["తెలుగు", "భాష", "తెలుగు"]` produce
`తెలుగు → document:[0, 2]` and `భాష → document:[1]`. The first 10,000-article
index reports `తెలుగు` with CF 6,806 and DF 3,251.

### External sorting and disk lookup

The disk builder groups each article's token positions by term, then appends
term/document/positions records to a buffer capped by a configurable record
count (50,000 by default). Full buffers are sorted by term and document ID and
written as temporary runs. Runs are merged externally with a fan-in of at most
32 files per merge operation, using multiple merge levels as needed. Duplicate
document IDs are checked in a temporary SQLite database rather than a
corpus-sized Python set.

During the final merge, postings are written sequentially to `postings.bin`.
Each term's vocabulary entry stores CF, DF, byte offset, byte length, and a
SHA-256 checksum for that serialized record. The vocabulary and postings are
written to a new generation and validated before the single
`current.json` manifest is atomically updated. Previous generations are not
deleted by the builder.

When `StorageManager` opens an index, it loads the vocabulary metadata into
memory and validates the generation ID, record ranges, and file bounds. It
does not load the complete postings file. A term lookup uses the in-memory
metadata to seek to the record's byte offset and read only its byte length;
the record is decoded as UTF-8 and checked against its checksum and CF/DF.
An individual lookup returns all postings for that term, so a very frequent
term can itself have a large result.

The record-count buffer bounds the number of buffered records, not their total
byte size. One large article and the in-memory vocabulary therefore still
affect peak memory. Vocabulary memory is intentionally proportional to the
number of unique terms, as required by the assignment.

## Build, reopen, and search

Place the compressed dump in the repository root, then build the verified
10,000-valid-article subset:

```powershell
python -X utf8 main.py `
  --dump .\tewiki-latest-pages-articles.xml.bz2 `
  --limit 10000 `
  --storage .\storage `
  --verify
```

`--limit` counts valid yielded articles, not all XML pages scanned. The
application reports indexing progress every 500 articles, prints statistics,
and enters an interactive Telugu term prompt when indexing completes.
`--verify` checks every postings record after building. Verification reads the
records one at a time; it does not load the complete postings file.

Open the currently published index later, without reading the XML dump:

```powershell
python -X utf8 main.py --load-existing --storage .\storage
```

To re-run full record verification when opening:

```powershell
python -X utf8 main.py --load-existing --storage .\storage --verify
```

At the prompt, enter one Telugu term, for example `తెలుగు`, to display its
CF, DF, and complete postings; enter `q` to exit. The CLI also accepts
multiple whitespace- or punctuation-separated terms. It tokenizes the input
with the existing preprocessor, then retrieves and displays each term's CF,
DF, and postings independently. Repeated terms are displayed repeatedly.
Unknown terms are reported individually. The postings lists are never
combined.

For example, enter:

```text
భారతదేశం అంకగణితం చరిత్ర సంస్కృతి
```

The Telugu CLI does **not** evaluate this as a phrase, AND, or OR query; it
only performs separate term lookups. Phrase and Boolean search are available
only in the separate legacy Reuters in-memory search workflow.

The index can also be inspected from Python while limiting displayed examples:

```powershell
@'
import sys
sys.stdout.reconfigure(encoding="utf-8")
from src.storage_manager import StorageManager

index = StorageManager("storage")
term = "\u0c24\u0c46\u0c32\u0c41\u0c17\u0c41"
statistics = index.get_term_statistics(term)
print("Statistics:", statistics)
if statistics is not None:
    postings = index.get_postings(term)
    print("Sample postings:", dict(list(postings.items())[:5]))
'@ | python -X utf8 -
```

The main CLI's `--limit` defaults to 5,000 when omitted. Set it explicitly to
10,000 to reproduce the documented subset size.

## Verified 10,000-article results

The following values are from the actual completed local build and full
postings verification; they are measurements, not estimates.

| Metric | Verified result |
|---|---:|
| Valid documents indexed | 10,000 |
| XML pages encountered to reach the limit | 12,911 |
| Non-main-namespace pages skipped | 2,218 |
| Redirects skipped | 693 |
| Empty articles encountered | 0 |
| Token occurrences | 4,916,974 |
| Total CF summed over vocabulary | 4,916,974 |
| Unique vocabulary terms | 303,366 |
| `postings.bin` | 127,229,948 bytes |
| `vocabulary.json` | 45,875,367 bytes |
| Combined index files | 173,105,315 bytes |
| Build time | 367.4 seconds |
| Full verification time | 106.48 seconds |
| Total elapsed build and verification | 473.88 seconds |
| Estimated retained vocabulary object memory | 127,273,556 bytes |
| Peak process RSS during build/verification | 539,963,392 bytes |
| Peak temporary build data | 312,597,685 bytes |

Memory and timing depend on machine load and environment. The vocabulary
memory value is an estimate of retained Python vocabulary objects; RSS is the
measured process working-set peak. The indexed data is the first 10,000 valid
articles, not the full corpus.

### Actual sample term searches

These are sample excerpts from the actual postings. Positions are zero-based;
posting lists shown here are abbreviated, while the CLI prints the full list.

| Term | Exists | CF | DF | Sample document IDs and positions |
|---|---:|---:|---:|---|
| తెలుగు | Yes | 6,806 | 3,251 | `1:[7]`, `10050:[68]`, `10085:[189,207,215,279]` |
| భారతదేశం | Yes | 447 | 222 | `10267:[281]`, `10277:[34]`, `10278:[17,351]` |
| ఆంధ్రప్రదేశ్ | Yes | 1,714 | 1,008 | `10028:[135]`, `10039:[219]`, `10046:[39]` |
| కంప్యూటర్ | Yes | 131 | 64 | `10306:[71]`, `1150:[291,339]`, `1212:[68,127,151,169,197,246,304,367]` |

### Multi-term terminal example

The following actual query is processed as four independent term lookups.
Postings shown are excerpts from the complete lists printed by the CLI:

```text
Query: భారతదేశం అంకగణితం చరిత్ర సంస్కృతి

Term: భారతదేశం
CF: 447
DF: 222
Postings:
10267: [281]
10277: [34]
10278: [17, 351]
... (219 additional document postings)

Term: అంకగణితం
CF: 1
DF: 1
Postings:
2495: [203]

Term: చరిత్ర
CF: 1430
DF: 804
Postings:
10099: [621]
10121: [54]
10206: [136]
... (801 additional document postings)

Term: సంస్కృతి
CF: 278
DF: 149
Postings:
10195: [35]
10277: [78, 3138]
10300: [1225]
... (146 additional document postings)
```

The ellipses above abbreviate the documentation excerpt only. During the
actual terminal run, the CLI printed each term's complete postings list.

## Assignment output

The root `output.txt` contains five multi-word Telugu test queries, with two
selected rare terms from each query (ten unique terms total). It lists CF and
DF for every selected term, each term's complete positional postings as a
separate list, and checks that the postings' document-entry count equals DF
and their total position count equals CF. The query strings provide context;
the Telugu CLI retrieves the selected terms independently and does not claim
phrase or AND-query matching.

## Tests

Run the complete test suite from the repository root:

```powershell
python -m pytest -q tests --import-mode=importlib
```

The verified result for the current project state is **96 passed**. Tests
cover preprocessing, Wikitext cleaning, XML loading, in-memory indexing, disk
serialization and retrieval, checksums, generation publication, and CLI
behavior, including multi-term Telugu lookups.

## Limitations

- The delivered disk index covers 10,000 valid articles only; it is not an
  index of the entire eligible 130,248-article dataset or full Telugu
  Wikipedia corpus.
- Multi-word input to the Telugu disk-index CLI is split into separate terms.
  Each term's CF, DF, and positional postings are displayed independently;
  Telugu phrase, AND, and OR matching are not implemented.
- The legacy Reuters CLI's Boolean and phrase-search capabilities use
  separate in-memory Reuters indexes; they do not operate on the Telugu
  disk index.
- The configured sort-buffer limit is in records rather than bytes, and
  vocabulary metadata is held in memory by design.
- Generated index files and the compressed dataset are local artifacts and
  are not committed to Git.

## GitHub repository

Project source code and documentation:
<https://github.com/KanekiKen-hub/IR-Assignement>

The dataset can be obtained from the official
[Telugu Wikipedia Wikimedia dump index](https://dumps.wikimedia.org/tewiki/latest/).
This repository does not provide a separate generated-index download link;
build the index locally from the compressed dump using the command in
**Build, reopen, and search**.
