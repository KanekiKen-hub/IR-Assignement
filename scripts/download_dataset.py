"""Download and verify the NLTK Reuters corpus."""

import nltk


def main() -> None:
    """Download Reuters and report basic corpus information."""
    print("Downloading the NLTK Reuters corpus if it is not already installed...")
    if not nltk.download("reuters"):
        raise SystemExit(
            "Reuters download failed. Check your internet connection and try again."
        )

    from nltk.corpus import reuters

    fileids = reuters.fileids()
    categories = reuters.categories()
    if not fileids:
        raise SystemExit("Reuters was downloaded, but no documents were found.")

    sample_fileid = fileids[0]
    sample_word_count = len(reuters.words(sample_fileid))

    print("Reuters corpus is ready.")
    print(f"Documents: {len(fileids)}")
    print(f"Categories: {len(categories)}")
    print(f"Sample document: {sample_fileid}")
    print(f"Sample document tokens: {sample_word_count}")


if __name__ == "__main__":
    main()
