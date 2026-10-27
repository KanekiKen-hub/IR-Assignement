# Reuters Information Retrieval System

This project will build an information retrieval system using the Reuters corpus distributed by NLTK. Development is split into phases; this setup currently downloads and verifies the corpus only. Indexing and search features will be added in later phases.

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
