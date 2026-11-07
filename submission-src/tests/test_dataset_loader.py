from src.dataset_loader import DatasetLoader


class FakeReutersCorpus:
    def __init__(self):
        self.documents = {
            "training/example-1": "A first article.",
            "test/example-2": "A second article.",
        }
        self.requested_fileids = []

    def fileids(self):
        return list(self.documents)

    def raw(self, fileid):
        self.requested_fileids.append(fileid)
        return self.documents[fileid]

    def categories(self):
        return ["example"]


def test_loader_reports_metadata_and_yields_original_ids_lazily():
    corpus = FakeReutersCorpus()
    loader = DatasetLoader(corpus)

    assert loader.document_count == 2
    assert loader.categories == ["example"]
    documents = loader.iter_documents()
    assert corpus.requested_fileids == []

    assert next(documents) == {
        "document_id": "training/example-1",
        "text": "A first article.",
    }
    assert corpus.requested_fileids == ["training/example-1"]
    assert next(documents) == {
        "document_id": "test/example-2",
        "text": "A second article.",
    }
