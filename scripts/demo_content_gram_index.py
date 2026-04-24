"""Demonstrate how multiple documents map into a content gram index.

This is a standalone script for inspecting the proposed MSSQL-side
"chunk + trigram posting" content index shape. It does not touch the
database. Instead, it:

1. Splits each document into overlapping chunks.
2. Extracts per-chunk trigrams.
3. Aggregates each trigram into one posting row per chunk and variant.
4. Prints both the document-local view and the combined inverted index.

Run:

    uv run python scripts/demo_content_gram_index.py

Optional:

    uv run python scripts/demo_content_gram_index.py --chunk-size 48 --overlap 8
    uv run python scripts/demo_content_gram_index.py --show-grams log,aut,def,ret
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass


DEFAULT_DOCS: dict[str, str] = {
    "auth.py": (
        "def login_user(email, password):\n"
        "    token = issue_session_token(email)\n"
        "    audit_log('login', email)\n"
        "    return token\n"
    ),
    "session.py": (
        "def issue_session_token(user_id):\n"
        "    session_token = sign_token(user_id)\n"
        "    return session_token\n"
    ),
    "docs.txt": (
        "Login flow overview.\n"
        "The session token is created after password validation.\n"
        "Audit logging records each successful login event.\n"
    ),
}


@dataclass(frozen=True)
class Chunk:
    doc_id: str
    chunk_id: str
    ordinal: int
    start_char: int
    end_char: int
    content: str


@dataclass(frozen=True)
class Posting:
    doc_id: str
    chunk_id: str
    ordinal: int
    variant: str
    gram: str
    loc_mask: int
    next_mask: int
    freq: int


def chunk_text(doc_id: str, text: str, *, chunk_size: int, overlap: int) -> list[Chunk]:
    """Split *text* into overlapping chunks."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    if overlap < 0:
        raise ValueError("overlap must be >= 0")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    if not text:
        return [Chunk(doc_id=doc_id, chunk_id=f"{doc_id}:0", ordinal=0, start_char=0, end_char=0, content="")]

    chunks: list[Chunk] = []
    start = 0
    ordinal = 0
    step = chunk_size - overlap

    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunks.append(
            Chunk(
                doc_id=doc_id,
                chunk_id=f"{doc_id}:{ordinal}",
                ordinal=ordinal,
                start_char=start,
                end_char=end,
                content=text[start:end],
            )
        )
        if end == len(text):
            break
        start += step
        ordinal += 1

    return chunks


def next_bucket(ch: str) -> int:
    """Map a following character to one of 8 tiny mask buckets."""
    return hash(ch) & 7


def aggregate_trigrams(text: str) -> dict[str, tuple[int, int, int]]:
    """Return gram -> (loc_mask, next_mask, freq) for one chunk."""
    if len(text) < 3:
        return {}

    acc: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])

    for i in range(len(text) - 2):
        gram = text[i : i + 3]
        loc_bit = 1 << (i & 7)
        follow_mask = 0
        if i + 3 < len(text):
            follow_mask = 1 << next_bucket(text[i + 3])

        row = acc[gram]
        row[0] |= loc_bit
        row[1] |= follow_mask
        row[2] += 1

    return {gram: (vals[0], vals[1], vals[2]) for gram, vals in acc.items()}


def build_postings(chunks: list[Chunk]) -> list[Posting]:
    """Build both case-sensitive and case-insensitive posting variants."""
    postings: list[Posting] = []

    for chunk in chunks:
        for variant, source in (("cs", chunk.content), ("ci", chunk.content.casefold())):
            for gram, (loc_mask, next_mask, freq) in sorted(aggregate_trigrams(source).items()):
                postings.append(
                    Posting(
                        doc_id=chunk.doc_id,
                        chunk_id=chunk.chunk_id,
                        ordinal=chunk.ordinal,
                        variant=variant,
                        gram=gram,
                        loc_mask=loc_mask,
                        next_mask=next_mask,
                        freq=freq,
                    )
                )

    return postings


def format_mask(mask: int) -> str:
    return f"{mask:08b}"


def print_documents(docs: dict[str, str]) -> None:
    print("Documents")
    print("=========")
    for doc_id, text in docs.items():
        preview = text.replace("\n", "\\n")
        if len(preview) > 110:
            preview = preview[:107] + "..."
        print(f"- {doc_id}: {len(text)} chars")
        print(f"  {preview}")
    print()


def print_chunks(chunks: list[Chunk]) -> None:
    print("Chunks")
    print("======")
    by_doc: dict[str, list[Chunk]] = defaultdict(list)
    for chunk in chunks:
        by_doc[chunk.doc_id].append(chunk)

    for doc_id, doc_chunks in by_doc.items():
        print(f"{doc_id}")
        for chunk in doc_chunks:
            preview = chunk.content.replace("\n", "\\n")
            if len(preview) > 80:
                preview = preview[:77] + "..."
            print(
                f"  chunk={chunk.chunk_id:<12} ord={chunk.ordinal:<2} "
                f"span=[{chunk.start_char:>3},{chunk.end_char:>3})  {preview}"
            )
        print()


def print_document_postings(postings: list[Posting], *, variant: str, limit: int) -> None:
    print(f"{variant.upper()} document-local postings")
    print("=" * (len(variant) + 23))

    by_doc: dict[str, list[Posting]] = defaultdict(list)
    for posting in postings:
        if posting.variant == variant:
            by_doc[posting.doc_id].append(posting)

    for doc_id, doc_postings in by_doc.items():
        print(f"{doc_id}  ({len(doc_postings)} posting rows)")
        for posting in doc_postings[:limit]:
            print(
                f"  gram={posting.gram!r} chunk={posting.chunk_id:<12} freq={posting.freq:<2} "
                f"loc={format_mask(posting.loc_mask)} next={format_mask(posting.next_mask)}"
            )
        if len(doc_postings) > limit:
            print(f"  ... {len(doc_postings) - limit} more rows")
        print()


def print_inverted_index(postings: list[Posting], *, variant: str, show_grams: list[str] | None) -> None:
    print(f"{variant.upper()} combined inverted index")
    print("=" * (len(variant) + 24))

    inverted: dict[str, list[Posting]] = defaultdict(list)
    for posting in postings:
        if posting.variant == variant:
            inverted[posting.gram].append(posting)

    grams = sorted(inverted)
    if show_grams:
        grams = [gram for gram in grams if gram in show_grams]

    for gram in grams:
        rows = inverted[gram]
        doc_hits = sorted({row.doc_id for row in rows})
        print(f"gram={gram!r}  docs={doc_hits}")
        for row in rows:
            print(
                f"  {row.doc_id:<10} chunk={row.chunk_id:<12} ord={row.ordinal:<2} "
                f"freq={row.freq:<2} loc={format_mask(row.loc_mask)} next={format_mask(row.next_mask)}"
            )
        print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunk-size", type=int, default=64, help="Chunk width in characters.")
    parser.add_argument("--overlap", type=int, default=12, help="Overlap between adjacent chunks.")
    parser.add_argument(
        "--posting-limit",
        type=int,
        default=18,
        help="Max posting rows to print per document in the local view.",
    )
    parser.add_argument(
        "--show-grams",
        type=str,
        default="log,ses,tok,def,ret",
        help="Comma-separated grams to show in the combined inverted index. Use '*' for all.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    show_grams = None if args.show_grams == "*" else [part for part in args.show_grams.split(",") if part]

    docs = DEFAULT_DOCS
    chunks = [
        chunk
        for doc_id, text in docs.items()
        for chunk in chunk_text(doc_id, text, chunk_size=args.chunk_size, overlap=args.overlap)
    ]
    postings = build_postings(chunks)

    print_documents(docs)
    print_chunks(chunks)
    print_document_postings(postings, variant="cs", limit=args.posting_limit)
    print_document_postings(postings, variant="ci", limit=args.posting_limit)
    print_inverted_index(postings, variant="cs", show_grams=show_grams)


if __name__ == "__main__":
    main()
