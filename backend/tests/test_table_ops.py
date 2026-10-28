"""Structured operations over a spreadsheet's tables, computed by the backend instead of the model."""
import pytest

from app.retrieval.table import Filter, Table, TableOperation, run

KONTRAK = Table.from_grid("Kontrak", "#/tables/0", [
    ["vendor", "nilai", "mulai", "kategori"],
    ["PT A", "Rp 1.250.000", "2024-01-15 00:00:00", "IT"],
    ["PT B", "2500000", "01/03/2024", "Umum"],
    ["PT C", "750000.5", "2024-05-20", "IT"],
    ["PT D", "1,5", "20/07/2024", "Umum"],
])


def test_a_sum_over_filtered_rows_reads_numbers_written_in_any_format_and_cites_those_rows():
    result = run(TableOperation(operation="sum", column="nilai", filters=[Filter(column="kategori", op="=", value="it")]), [KONTRAK])

    assert "2000000.5" in result["text"]
    assert result["refs"] == ["#/tables/0/rows/1", "#/tables/0/rows/3"]


def test_an_average_grouped_by_a_column_gives_one_result_per_group():
    result = run(TableOperation(operation="avg", column="nilai", group_by="kategori"), [KONTRAK])

    assert "IT: 1000000.25 (2 rows)" in result["text"]
    assert "Umum: 1250000.75 (2 rows)" in result["text"]
    assert len(result["refs"]) == 4


def test_a_count_needs_no_column():
    result = run(TableOperation(operation="count", filters=[Filter(column="nilai", op=">", value="1000000")]), [KONTRAK])

    assert "COUNT = 2" in result["text"]
    assert result["refs"] == ["#/tables/0/rows/1", "#/tables/0/rows/2"]


def test_the_earliest_and_latest_date_read_iso_and_day_first_dates():
    earliest = run(TableOperation(operation="min", column="mulai"), [KONTRAK])
    latest = run(TableOperation(operation="max", column="mulai"), [KONTRAK])

    assert "2024-01-15" in earliest["text"] and earliest["refs"] == ["#/tables/0/rows/1"]
    assert "2024-07-20" in latest["text"] and latest["refs"] == ["#/tables/0/rows/4"]


def test_top_n_ranks_rows_by_a_column_largest_first_unless_asked_for_the_smallest():
    largest = run(TableOperation(operation="top_n", column="nilai", limit=2), [KONTRAK])
    smallest = run(TableOperation(operation="top_n", column="nilai", limit=1, ascending=True), [KONTRAK])

    assert largest["text"].index("PT B") < largest["text"].index("PT A")
    assert "PT C" not in largest["text"]
    assert largest["refs"] == ["#/tables/0/rows/1", "#/tables/0/rows/2"]
    assert "PT D" in smallest["text"] and smallest["refs"] == ["#/tables/0/rows/4"]


def test_list_gives_every_matching_row_with_all_its_values():
    result = run(TableOperation(operation="list", filters=[Filter(column="kategori", op="=", value="Umum")]), [KONTRAK])

    assert "vendor = PT B, nilai = 2500000, mulai = 01/03/2024, kategori = Umum" in result["text"]
    assert result["refs"] == ["#/tables/0/rows/2", "#/tables/0/rows/4"]


def test_a_column_or_sheet_the_table_does_not_have_is_rejected_naming_what_it_has():
    with pytest.raises(ValueError, match="vendor, nilai, mulai, kategori"):
        run(TableOperation(operation="sum", column="harga"), [KONTRAK])
    with pytest.raises(ValueError, match="Kontrak"):
        run(TableOperation(operation="count", sheet="Diskon"), [KONTRAK])


def test_the_sheet_named_is_the_one_computed_over():
    diskon = Table.from_grid("Diskon", "#/tables/1", [["kode", "persen"], ["HEMAT", "10"], ["LOYAL", "15"]])

    result = run(TableOperation(operation="max", sheet="diskon", column="persen"), [KONTRAK, diskon])

    assert "= 15" in result["text"] and result["refs"] == ["#/tables/1/rows/2"]


def test_a_totals_row_at_the_bottom_is_left_out_so_nothing_is_counted_twice():
    table = Table.from_grid("Biaya", "#/tables/0", [["item", "biaya"], ["Server", "100"], ["Lisensi", "50"], ["Total", "150"]])

    result = run(TableOperation(operation="sum", column="biaya"), [table])

    assert "= 150 (2 rows)" in result["text"]
    assert "Total" in result["text"], "says the totals row was left out"
    assert "#/tables/0/rows/3" not in result["refs"]


def test_a_workbooks_sheets_load_from_its_converted_document_with_the_rows_the_viewer_marks(monkeypatch, tmp_path):
    """Real Docling. Row n of a table is "{ref}/rows/{n}", the anchor GET /documents/{id}/view marks."""
    import openpyxl

    from app.config import settings
    from app.ingest.convert import convert, converted_path
    from app.retrieval.table import load_tables

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    path = tmp_path / "harga.xlsx"
    book = openpyxl.Workbook()
    book.active.title = "Paket"
    for row in [("paket", "harga"), ("Basic", 100000), ("Pro", 250000)]:
        book.active.append(row)
    book.create_sheet("Diskon").append(("kode", "persen"))
    book["Diskon"].append(("HEMAT", 10))
    book.save(path)
    doc, _, _ = convert(str(path), set())
    converted_path("d1").parent.mkdir(parents=True)
    doc.save_as_json(converted_path("d1"))

    paket, diskon = load_tables("d1")

    assert (paket.name, paket.ref, paket.header) == ("Paket", "#/tables/0", ["paket", "harga"])
    assert paket.rows == {1: ["Basic", "100000"], 2: ["Pro", "250000"]}
    assert (diskon.name, diskon.ref) == ("Diskon", "#/tables/1")
    assert run(TableOperation(operation="sum", column="harga"), [paket, diskon])["refs"] == ["#/tables/0/rows/1", "#/tables/0/rows/2"]


def test_a_document_converted_before_converted_documents_were_kept_has_no_tables(monkeypatch, tmp_path):
    from app.config import settings
    from app.retrieval.table import load_tables

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    assert load_tables("old") == []
