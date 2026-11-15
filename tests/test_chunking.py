import pytest

from app.rag.pdf import chunk_pages, clean, extract_pages


def test_clean_rejoins_hyphenated_linebreaks():
    assert "knowledge" in clean("know-\nledge base")


def test_clean_collapses_blank_lines():
    assert clean("a\n\n\n\n\nb") == "a\n\nb"


def test_chunks_carry_their_page_number():
    pages = [(1, "alpha " * 500), (2, "beta " * 500)]
    chunks = chunk_pages(pages, chunk_size=400, overlap=50)

    assert {c.page for c in chunks} == {1, 2}
    assert all(c.text for c in chunks)


def test_chunks_overlap_so_context_is_not_cut_in_half():
    pages = [(1, "word " * 1000)]
    chunks = chunk_pages(pages, chunk_size=500, overlap=100)

    assert len(chunks) > 1

    assert chunks[0].text[-50:] in chunks[1].text or chunks[1].text[:50] in chunks[0].text


def test_chunking_terminates_on_pathological_input():

    chunks = chunk_pages([(1, "x" * 5000)], chunk_size=100, overlap=500)
    assert len(chunks) > 0


def test_indices_are_unique():
    chunks = chunk_pages([(1, "a " * 2000), (2, "b " * 2000)], 400, 50)
    indices = [c.index for c in chunks]
    assert len(indices) == len(set(indices))


def test_scanned_pdf_raises_a_useful_error():
    import pymupdf

    doc = pymupdf.open()
    doc.new_page() 
    data = doc.tobytes()
    doc.close()

    with pytest.raises(ValueError, match="scan"):
        extract_pages(data)
