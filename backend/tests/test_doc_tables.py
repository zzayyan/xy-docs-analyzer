"""Ingest keeps the tables Docling recognises, whole, beside the chunks. A real Markdown conversion: no
OCR or layout models load for Markdown, only the bge-m3 tokenizer the chunker counts with."""
from app.ingest.convert import convert

ROWS = 60  # long enough that the chunker splits the table over several chunks


def test_a_table_is_kept_whole_and_each_chunk_points_at_it_with_its_prose_apart(tmp_path):
    body = "\n".join(f"| {i} | Kewajiban nomor {i} yang cukup panjang untuk memakan token | 1 Mei 2027 |" for i in range(ROWS))
    path = tmp_path / "kontrak.md"
    path.write_text(
        f"# Kontrak\n\n## Pasal 1\n\nPihak pertama wajib membayar.\n\n"
        f"| No | Kewajiban | Tenggat |\n|----|----|----|\n{body}\n\nParagraf setelah tabel.\n",
        encoding="utf-8",
    )

    _, _, chunks, tables = convert(str(path))

    [table] = tables
    assert table["idx"] == 0
    lines = table["markdown"].splitlines()
    assert lines[:3] == [
        "| No | Kewajiban | Tenggat |", "|---|---|---|",
        "| 0 | Kewajiban nomor 0 yang cukup panjang untuk memakan token | 1 Mei 2027 |",
    ], "the export's padding is collapsed"
    assert len(lines) == ROWS + 2, "header, separator, then every row"

    holding = [c for c in chunks if c["table_refs"]]
    assert len(holding) > 1, "the table is split over chunks, which is why it is read whole"
    assert all(c["table_refs"] == [0] for c in holding)
    assert all("Kewajiban nomor" not in (c["prose"] or "") for c in holding), "prose never repeats the table"
    assert holding[-1]["prose"].endswith("Paragraf setelah tabel.")
    assert all(c["prose"] is None for c in chunks if not c["table_refs"])


def test_a_tables_caption_is_kept_apart_from_its_markdown():
    from docling_core.types.doc.document import DocItemLabel, DoclingDocument, TableCell, TableData

    from app.ingest.convert import document_tables

    doc = DoclingDocument(name="d")
    cells = [TableCell(text=text, start_row_offset_idx=r, end_row_offset_idx=r + 1, start_col_offset_idx=c,
                       end_col_offset_idx=c + 1, column_header=r == 0)
             for r, row in enumerate([["Metode", "Skor"], ["Kutipan", "41%"]]) for c, text in enumerate(row)]
    caption = doc.add_text(label=DocItemLabel.CAPTION, text="Table 6: Skor metode")
    doc.add_table(data=TableData(num_rows=2, num_cols=2, table_cells=cells), caption=caption)

    [table] = document_tables(doc).values()

    assert table["caption"] == "Table 6: Skor metode"
    assert table["markdown"] == "| Metode | Skor |\n|---|---|\n| Kutipan | 41% |"
