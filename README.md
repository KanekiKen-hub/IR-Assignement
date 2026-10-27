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
