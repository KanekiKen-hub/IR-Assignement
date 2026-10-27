# Reuters Information Retrieval System

This project will build an information retrieval system using the Reuters corpus distributed by NLTK. Development is split into phases; the current implementation downloads and verifies the corpus, loads Reuters articles lazily, and preprocesses text into deterministic tokens. Indexing and search features will be added in later phases.

## Phase 1: Setup

### Requirements

- Python 3
- An internet connection for the initial Reuters corpus download

From the project directory in PowerShell, create and activate a virtual environment, then install the project dependencies:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Download and verify Reuters:

```powershell
python scripts\download_dataset.py
```

The script uses NLTK's Reuters corpus and reports its document and category counts, plus a small sample check. NLTK typically stores downloaded data in its user-level `nltk_data` directory, outside this repository; the corpus is not copied into Git.

To run the setup again, use the same command. NLTK reuses an existing download.

## Phase 2: Dataset Loading and Preprocessing

The `DatasetLoader` exposes the Reuters document count and categories, and
`iter_documents()` yields each original Reuters file ID with its raw article
text. It retrieves each article only as it is iterated, rather than retaining
the corpus text in memory.

`Preprocessor.process(text)` lowercases text and produces tokens in source
order. Letters, digits, and mixed alphanumeric tokens are retained; punctuation
and underscores separate tokens. Numbers are kept rather than discarded. Stop
word removal and NLTK Porter stemming are optional and off by default. Token
positions in later indexes will refer to this returned list, using zero-based
positions.

Run the unit tests from the project directory:

```powershell
python -m pytest
```

To check a few actual Reuters documents after completing Phase 1:

```powershell
python -c "from itertools import islice; from src.dataset_loader import DatasetLoader; from src.preprocessor import Preprocessor; loader = DatasetLoader(); processor = Preprocessor(); print('Documents:', loader.document_count); [print(doc['document_id'], processor.process(doc['text'])[:12]) for doc in islice(loader.iter_documents(), 3)]"
```

## Phase 3: Inverted Index

`InvertedIndex.build(documents)` consumes the loader's document iterator and
uses the same `Preprocessor` to normalize article text. It maps each token to
the set of original Reuters file IDs containing it. Repeated occurrences in one
article do not duplicate that document ID. `get_postings(term)` returns a copy
of the matching ID set, while `get_document_frequency(term)` returns its size.
Unknown terms (and inputs that do not preprocess to exactly one token) return
empty postings and frequency zero.

The index is in memory; the loader still yields article text incrementally.
Run its unit tests with `python -m pytest -q`.

To build an index over the actual Reuters corpus and inspect example postings:

```powershell
python -c "from src.dataset_loader import DatasetLoader; from src.inverted_index import InvertedIndex; index = InvertedIndex(); index.build(DatasetLoader().iter_documents()); print('Documents:', index.document_count); print('Unique terms:', index.unique_term_count); print('oil document frequency:', index.get_document_frequency('oil')); print('oil sample postings:', sorted(index.get_postings('oil'))[:10])"
```

## Phase 4: Positional Index

`PositionalIndex.build(documents)` uses the same preprocessing pipeline and
stores every term occurrence by document ID. Positions are zero-based indexes
into the processed token sequence, so optional stop-word removal changes the
sequence being indexed consistently. `get_postings(term)` returns a copy of
the term's document-to-positions mapping; `get_positions(term, document_id)`
and `get_term_frequency(term, document_id)` provide document-level lookups.

Run the unit tests with `python -m pytest -q`. To inspect positions from a few
actual Reuters documents:

```powershell
python -c "from itertools import islice; from src.dataset_loader import DatasetLoader; from src.positional_index import PositionalIndex; index = PositionalIndex(); index.build(islice(DatasetLoader().iter_documents(), 3)); print('Documents:', index.document_count); print('oil postings:', index.get_postings('oil'))"
```

## Phase 5: Search

`SearchEngine` uses the inverted index for term lookup and Boolean AND/OR
intersection/union, and the positional index for exact phrase search. A phrase
must match consecutive processed-token positions; `phrase_positions()` returns
the zero-based start positions for each matching document. It handles unknown
terms and empty queries with empty results. Malformed non-empty syntax raises a
`ValueError` with a query explanation.

Supported queries are a single term (`oil`), two terms joined by one Boolean
operator (`oil AND prices`, `oil OR prices`), or a quoted phrase (`"oil prices"`).
Unquoted multiple terms, mixed/repeated operators, and malformed quotes are
rejected rather than interpreted ambiguously. Pass the same `Preprocessor`
instance to both indexes so query normalization matches indexing.

Run the search tests with `python -m pytest -q`. For a small deterministic
example:

```powershell
python -c "from src.inverted_index import InvertedIndex; from src.positional_index import PositionalIndex; from src.search_engine import SearchEngine; docs = [{'document_id': 'example-1', 'text': 'oil prices rose'}]; inverted = InvertedIndex(); positional = PositionalIndex(); inverted.build(docs); positional.build(docs); engine = SearchEngine(inverted, positional); print(engine.search('oil AND prices')); print(engine.phrase_positions('oil prices'))"
```
