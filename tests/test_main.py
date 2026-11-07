import bz2

from src.dataset_loader import DatasetLoader
from src.disk_index_builder import build_disk_index
from main import run_cli, run_wikipedia_index_cli
from main import main as main_entry


class FakeReutersCorpus:
    def __init__(self):
        self.documents = {
            "test/1": "Oil prices rose.",
            "training/2": "Oil prices fell.",
            "training/3": "Gold prices rose.",
        }

    def fileids(self):
        return list(self.documents)

    def raw(self, fileid):
        return self.documents[fileid]

    def categories(self):
        return ["commodities"]


def test_cli_builds_indexes_searches_and_prints_snippets():
    inputs = iter(["oil AND prices", "2", "q"])
    outputs = []

    run_cli(
        DatasetLoader(FakeReutersCorpus()),
        input_fn=lambda _prompt: next(inputs),
        output_fn=outputs.append,
    )

    assert "Documents indexed: 3" in outputs
    assert "Unique terms: 5" in outputs
    assert "Results found: 2" in outputs
    assert any(line.startswith("- test/1: Oil prices rose.") for line in outputs)
    assert any(line.startswith("- training/2: Oil prices fell.") for line in outputs)
    assert outputs[-1] == "Goodbye."


def test_cli_supports_phrase_selection_and_empty_query():
    inputs = iter(["", '"oil prices"', "3", "q"])
    outputs = []

    run_cli(
        DatasetLoader(FakeReutersCorpus()),
        input_fn=lambda _prompt: next(inputs),
        output_fn=outputs.append,
    )

    assert "Please enter a non-empty query." in outputs
    assert "Search type: Phrase" in outputs
    assert "Results found: 2" in outputs


def test_cli_reports_malformed_query_and_invalid_search_type():
    inputs = iter(
        [
            "oil prices",
            "1",
            "oil AND prices",
            "1",
            "oil AND",
            "2",
            "oil",
            "4",
            "oil",
            "2",
            "q",
        ]
    )
    outputs = []

    run_cli(
        DatasetLoader(FakeReutersCorpus()),
        input_fn=lambda _prompt: next(inputs),
        output_fn=outputs.append,
    )

    assert any(message.startswith("Invalid query:") for message in outputs)
    assert "Invalid search type. Choose 1, 2, or 3." in outputs
    assert "Keyword search requires exactly one term." in outputs
    assert "Boolean search requires two terms joined by AND or OR." in outputs


def test_cli_handles_terms_with_no_results():
    inputs = iter(["unknown", "1", "q"])
    outputs = []

    run_cli(
        DatasetLoader(FakeReutersCorpus()),
        input_fn=lambda _prompt: next(inputs),
        output_fn=outputs.append,
    )

    assert "Results found: 0" in outputs


def test_wikipedia_cli_builds_index_and_displays_cf_df_and_positions(tmp_path):
    dump_path = tmp_path / "synthetic-wikipedia.xml.bz2"
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.11/">'
        "<page><title>తెలుగు</title><ns>0</ns><id>786</id><revision><id>1</id>"
        "<text>'''తెలుగు''' భాష తెలుగు</text></revision></page>"
        "<page><title>భాష</title><ns>0</ns><id>787</id><revision><id>2</id>"
        "<text>తెలుగు వార్త</text></revision></page>"
        "</mediawiki>"
    )
    with bz2.open(dump_path, "wt", encoding="utf-8") as dump:
        dump.write(xml)

    inputs = iter(["తెలుగు", "q"])
    outputs = []
    index = run_wikipedia_index_cli(
        dump_path,
        max_articles=100,
        storage_dir=tmp_path / "index",
        input_fn=lambda _prompt: next(inputs),
        output_fn=outputs.append,
    )

    assert index.document_count == 2
    assert index.total_token_count == 5
    assert index.unique_term_count == 3
    assert index.get_collection_frequency("తెలుగు") == 3
    assert index.get_document_frequency("తెలుగు") == 2
    assert "Articles indexed: 2" in outputs
    assert "Total tokens: 5" in outputs
    assert "Vocabulary size: 3" in outputs
    assert "DF: 2" in outputs
    assert "CF: 3" in outputs
    assert "786: [0, 2]" in outputs
    assert "787: [0]" in outputs


def test_cli_loads_existing_disk_index_without_dataset_dump(
    tmp_path,
    monkeypatch,
    capsys,
):
    storage_dir = tmp_path / "index"
    build_disk_index([("786", ["తెలుగు", "భాష", "తెలుగు"])], storage_dir)
    inputs = iter(["తెలుగు", "q"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(inputs))

    main_entry(
        [
            "--dump",
            str(tmp_path / "not-downloaded.xml.bz2"),
            "--storage",
            str(storage_dir),
            "--load-existing",
            "--verify",
        ]
    )

    output = capsys.readouterr().out
    assert "Articles indexed: 1" in output
    assert "Verification:" in output
    assert "DF: 1" in output
    assert "CF: 2" in output
    assert "786: [0, 2]" in output
