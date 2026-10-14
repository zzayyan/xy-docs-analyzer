"""Section tree construction."""
from app.ingest.tree import build_sections, infer_levels


def test_flat_pdf_headings_use_numbering():
    # Real heading shapes from a Docling PDF conversion where every heading came back as level 1
    headings = [(1, title) for title in [
        "Setup LangFlow Chatbot User & AI Fact Check",
        "Quick Start - Deployment Production",
        "Step 1: Update Database Production",
        "A. Setup Database Chatbot User",
        "0. Prasyarat: Install PyMySQL di Env LangFlow",
        "Cara Install PyMySQL:",
        "1. Persiapan Konfigurasi Database MySQL",
        "B. Setup AI Fact Check (Admin)",
        "2.1 Detail",
        "Implementasi:",
    ]]
    assert infer_levels(headings) == [1, 1, 1, 1, 2, 3, 2, 1, 3, 4]


def test_nested_docling_levels_are_kept():
    assert infer_levels([(0, "Judul"), (1, "1 Bab"), (2, "1.1 Sub"), (1, "2 Bab")]) == [0, 1, 2, 1]


def test_numbers_inside_titles_are_not_numbering():
    assert infer_levels([(1, "Anggaran Rp 12,5 miliar"), (1, "2.3 Rincian")]) == [1, 2]


def test_build_sections_links_parents_chunks_and_pages():
    headings = [(1, "A. Setup"), (1, "1. Install"), (1, "Contoh:"), (1, "B. Deploy")]
    chunks = [
        {"id": "c0", "headings": ["1. Install"], "pages": [1]},
        {"id": "c1", "headings": ["Contoh:"], "pages": [2]},
        {"id": "c2", "headings": ["Contoh:"], "pages": [3]},
        {"id": "c3", "headings": ["B. Deploy"], "pages": [4]},
    ]
    sections, chunk_section = build_sections("f", headings, chunks)
    by_title = {s["title"]: s for s in sections}

    assert [s["level"] for s in sections] == [1, 2, 3, 1]
    assert by_title["1. Install"]["parent"] == by_title["A. Setup"]["id"]
    assert by_title["Contoh:"]["parent"] == by_title["1. Install"]["id"]
    assert by_title["B. Deploy"]["parent"] is None
    assert chunk_section == {"c0": "f:s1", "c1": "f:s2", "c2": "f:s2", "c3": "f:s3"}
    # Container section without its own chunks still gets its descendants' page range
    assert (by_title["A. Setup"]["start_page"], by_title["A. Setup"]["end_page"]) == (1, 3)


def test_repeated_titles_match_in_document_order():
    headings = [(1, "1. Chatbot"), (1, "Contoh:"), (1, "2. Fact Check"), (1, "Contoh:")]
    chunks = [
        {"id": "c0", "headings": ["Contoh:"], "pages": []},
        {"id": "c1", "headings": ["2. Fact Check"], "pages": []},
        {"id": "c2", "headings": ["Contoh:"], "pages": []},
    ]
    _sections, chunk_section = build_sections("f", headings, chunks)
    assert chunk_section == {"c0": "f:s1", "c1": "f:s2", "c2": "f:s3"}


def test_document_without_headings_groups_chunks():
    chunks = [{"id": f"c{i}", "headings": [], "pages": [i + 1]} for i in range(10)]
    sections, chunk_section = build_sections("f", [], chunks)
    assert len(sections) == 2
    assert chunk_section["c9"] == "f:s1"
    assert (sections[1]["start_page"], sections[1]["end_page"]) == (9, 10)
