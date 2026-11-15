import logging
import re
from dataclasses import dataclass

import pymupdf

log = logging.getLogger(__name__)


@dataclass
class Chunk:
    text: str
    page: int
    index: int


def extract_pages(pdf_bytes: bytes) -> list[tuple[int, str]]:
    """Pull text out page by page.

    Keeping the page number attached is what lets us show "Source: page 4"
    in the UI later - without it the citations are useless.
    """
    pages: list[tuple[int, str]] = []

    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page_no, page in enumerate(doc, start=1):
            text = page.get_text("text")
            if text and text.strip():
                pages.append((page_no, clean(text)))

    if not pages:

        raise ValueError(
            "No selectable text found in this PDF. "
            "It is probably a scan - try a text-based PDF."
        )

    return pages


def clean(text: str) -> str:

    text = re.sub(r"-\n(\w)", r"\1", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_pages(
    pages: list[tuple[int, str]],
    chunk_size: int = 1200,
    overlap: int = 200,
) -> list[Chunk]:

    chunks: list[Chunk] = []
    idx = 0

    for page_no, text in pages:
        start = 0

        while start < len(text):
            end = min(start + chunk_size, len(text))

            if end < len(text):

                window = text[start:end]
                for marker in ("\n\n", ". ", "\n"):
                    cut = window.rfind(marker)
                    if cut > chunk_size * 0.5:
                        end = start + cut + len(marker)
                        break

            body = text[start:end].strip()
            if len(body) > 50: 
                chunks.append(Chunk(text=body, page=page_no, index=idx))
                idx += 1

            if end >= len(text):
                break

            start = max(end - overlap, start + 1)

    log.info("split pdf into %d chunks across %d pages", len(chunks), len(pages))
    return chunks
