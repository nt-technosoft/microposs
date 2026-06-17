#!/usr/bin/env python3
"""E99 smoke test: count words in data/notes.md (sandbox, throwaway)."""
from pathlib import Path

NOTES = Path(__file__).resolve().parent.parent / "data" / "notes.md"


def count_words(text: str) -> int:
    return len(text.split())


def main() -> None:
    text = NOTES.read_text(encoding="utf-8")
    print(f"file: {NOTES.name}")
    print(f"words: {count_words(text)}")


if __name__ == "__main__":
    main()
