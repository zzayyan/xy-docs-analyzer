"""Table Extraction with the model faked."""
import threading
import time

import pytest

import app.table as table
from app.config import settings
from app.prompts import table as prompts

# Kept before the autouse fixture below replaces it, for the one test that is about the call itself
real_find_duplicates = table.find_duplicates

COLUMNS = [
    {"name": "Kewajiban", "description": "The obligation as written"},
    {"name": "Tenggat", "description": "Its deadline"},
]


@pytest.fixture(autouse=True)
def document_model(monkeypatch):
    """Every test fakes table.llm; a TABLE_LLM_MODEL in the developer's .env must not route around it."""
    monkeypatch.setattr(settings, "table_llm_model", "")


@pytest.fixture(autouse=True)
def no_duplicates(monkeypatch):
    """No duplicates unless a merge test says otherwise."""
    monkeypatch.setattr(table, "find_duplicates", lambda rows, columns, model: [])


@pytest.fixture
def chunks():
    # Every value the fakes below return is quoted from this text, as a real model's must be
    return [{"id": f"f:{i}", "text": f"text {i}: item {i}, item, other, bayar, lapor 10 Mei, 31 Jan 2027", "pages": [i],
             "headings": [f"Bab {i}"]} for i in range(8)]


def fake_rows(values: list[list[str]]):
    return table.ChunkRows(rows=[table.ExtractedRow(values=v) for v in values])


def test_every_chunk_is_read_once_in_order_and_rows_cite_their_chunk(monkeypatch, chunks):
    threads: set[int] = set()

    def slow_extract(text, columns, model, request):
        threads.add(threading.get_ident())
        time.sleep(0.2)
        return fake_rows([[f"item {text.split(':')[0][-1]}", "2027"]])

    monkeypatch.setattr(settings, "llm_concurrency", 4)
    monkeypatch.setattr(table, "extract_one", slow_extract)

    progress: list[tuple[int, int]] = []
    started = time.time()
    rows = table.run(chunks, COLUMNS, model=None, on_progress=lambda done, total: progress.append((done, total)))
    elapsed = time.time() - started

    assert len(threads) > 1, "chunks were not read in parallel"
    assert elapsed < 8 * 0.2, f"took {elapsed:.1f}s, no faster than sequential"
    assert [row["citations"][0]["chunk_id"] for row in rows] == [c["id"] for c in chunks], "chunk order must be kept"
    assert progress == [(i, 8) for i in range(1, 9)]
    assert rows[0] == {
        "values": {"Kewajiban": "item 0", "Tenggat": "2027"},
        "citations": [{
            "n": 1, "chunk_id": "f:0", "pages": [0], "headings": ["Bab 0"], "regions": [],
            "source": "table", "text": chunks[0]["text"],
        }],
    }


def test_a_chunk_with_regions_gives_its_row_a_highlight(monkeypatch, chunks):
    region = {"page": 1, "l": 0, "t": 0, "r": 10, "b": 10, "page_width": 600, "page_height": 800}
    with_regions = [{**c, "regions": [region]} if c["id"] == "f:0" else c for c in chunks]
    monkeypatch.setattr(table, "extract_one", lambda text, columns, model, request: fake_rows([["item", "2027"]]))

    rows = table.run(with_regions, COLUMNS, model=None)

    assert rows[0]["citations"][0]["regions"] == [region]
    assert rows[1]["citations"][0]["regions"] == [], "a chunk with no regions cites with none"


def test_a_value_the_document_does_not_state_stays_empty(monkeypatch, chunks):
    # The model returns only the first column for one row, and a blank for the other
    monkeypatch.setattr(table, "extract_one", lambda text, columns, model, request: fake_rows([["item"], ["other", "  "]]))

    rows = table.run(chunks[:1], COLUMNS, model=None)

    assert [row["values"] for row in rows] == [
        {"Kewajiban": "item", "Tenggat": ""},
        {"Kewajiban": "other", "Tenggat": ""},
    ]


def test_a_chunk_with_no_matching_item_contributes_no_rows(monkeypatch, chunks):
    monkeypatch.setattr(table, "extract_one", lambda text, columns, model, request: fake_rows([]))

    assert table.run(chunks, COLUMNS, model=None) == []


def test_a_model_failure_on_one_chunk_fails_the_run(monkeypatch, chunks):
    def boom(text, columns, model, request):
        if text.startswith("text 3"):
            raise RuntimeError("model refused")
        return fake_rows([["item", "2027"]])

    monkeypatch.setattr(settings, "llm_concurrency", 4)
    monkeypatch.setattr(table, "extract_one", boom)

    with pytest.raises(RuntimeError, match="model refused"):
        table.run(chunks, COLUMNS, model=None)


def test_propose_columns_returns_name_and_description_per_column(monkeypatch):
    seen = {}

    class FakeModel:
        def with_structured_output(self, schema):
            seen["schema"] = schema
            return self

        def invoke(self, messages):
            seen["messages"] = messages
            return table.ProposedColumns(columns=[table.Column(name="Kewajiban", description="The obligation")])

    monkeypatch.setattr(table, "llm", lambda model=None: FakeModel())

    assert table.propose_columns("setiap kewajiban dan tenggatnya", model=None) == [
        {"name": "Kewajiban", "description": "The obligation"},
    ]
    assert "setiap kewajiban dan tenggatnya" in seen["messages"][-1][1]


SECTIONS = [{"title": f"Bab {i} " + "j" * 400, "id": f"s{i}"} for i in range(60)]


def test_document_context_carries_outline_titles_and_chunk_text_and_stays_bounded():
    chunks = [{"id": f"f:{i}", "text": f"isi {i} " + "x" * 5000, "pages": [i], "headings": []} for i in range(20)]

    context = table.document_context(SECTIONS, chunks)

    assert "Bab 0" in context and "isi 0" in context
    assert "j" * 400 not in context, "a long heading is truncated"
    assert "Bab 59" not in context, "the outline is truncated"
    assert "isi 19" not in context, "only the first chunks are used"
    assert len(context) < 10000, f"context is {len(context)} characters, too long to prepend to every proposal"


def test_document_context_of_a_short_document_is_its_chunks_alone():
    # A short document has no sections, so the passages are all the context there is
    context = table.document_context([], [{"id": "f:0", "text": "isi", "pages": [1], "headings": []}])

    assert "isi" in context


def test_propose_columns_passes_the_document_context_to_the_model(monkeypatch):
    seen = {}

    class FakeModel:
        def with_structured_output(self, schema):
            return self

        def invoke(self, messages):
            seen["messages"] = messages
            return table.ProposedColumns(columns=[table.Column(name="Pasal", description="Nomor pasal")])

    monkeypatch.setattr(table, "llm", lambda model=None: FakeModel())

    table.propose_columns("setiap kewajiban", model=None, context="Outline:\n- Bab I Ketentuan Umum")

    prompt = "\n".join(text for _, text in seen["messages"])
    assert "Bab I Ketentuan Umum" in prompt
    assert "setiap kewajiban" in prompt


def test_suggest_tables_returns_candidate_tables_with_their_columns(monkeypatch):
    seen = {}

    class FakeModel:
        def with_structured_output(self, schema):
            return self

        def invoke(self, messages):
            seen["messages"] = messages
            return table.SuggestedTables(tables=[
                table.SuggestedTable(
                    title="Kewajiban", request="Setiap kewajiban dan pasalnya",
                    columns=[table.Column(name="Pasal", description="Nomor pasal")],
                ),
            ])

    monkeypatch.setattr(table, "llm", lambda model=None: FakeModel())

    assert table.suggest_tables("Outline:\n- Bab I", model=None) == [
        {"title": "Kewajiban", "request": "Setiap kewajiban dan pasalnya",
         "columns": [{"name": "Pasal", "description": "Nomor pasal"}]},
    ]
    assert "Bab I" in "\n".join(text for _, text in seen["messages"])


class LoopingModel:
    """A model that runs away on greedy decoding, the way Qwen3.5-4B does on some chunks."""

    def __init__(self, temperature: float, calls: list):
        self.temperature = temperature
        self.calls = calls

    def with_structured_output(self, schema):
        return self

    def invoke(self, messages):
        self.calls.append(self.temperature)
        if self.temperature == 0:
            raise ValueError("Could not parse response content as the length limit was reached")
        return table.ChunkRows(rows=[table.ExtractedRow(values=["item"])])


def fake_llm(calls: list, seen: list):
    def build(model=None, *, temperature=0.0, max_tokens=None):
        seen.append(max_tokens)
        return LoopingModel(temperature, calls)

    return build


def test_a_chunk_the_model_loops_on_is_read_again_off_greedy(monkeypatch):
    calls, capped = [], []
    monkeypatch.setattr(table, "llm", fake_llm(calls, capped))

    found = table.extract_one("text", COLUMNS, None, "")

    assert calls == [0.0, table.RETRY_TEMPERATURE], "the retry must not repeat the greedy attempt"
    assert capped == [table.EXTRACT_MAX_TOKENS] * 2, "both attempts are capped, so a runaway fails fast"
    assert [row.values for row in found.rows] == [["item"]]


def test_a_chunk_that_fails_twice_still_fails_the_run(monkeypatch):
    class AlwaysFails(LoopingModel):
        def invoke(self, messages):
            self.calls.append(self.temperature)
            raise ValueError("Could not parse response content as the length limit was reached")

    def build(model=None, *, temperature=0.0, max_tokens=None):
        return AlwaysFails(temperature, [])

    monkeypatch.setattr(table, "llm", build)

    with pytest.raises(ValueError, match="length limit"):
        table.extract_one("text", COLUMNS, None, "")


def test_a_cancelled_run_stops_reading_chunks_instead_of_finishing_the_document(monkeypatch, chunks):
    read: list[str] = []

    def slow_extract(text, columns, model, request):
        read.append(text)
        time.sleep(0.1)
        return fake_rows([["item", "2027"]])

    monkeypatch.setattr(settings, "llm_concurrency", 2)
    monkeypatch.setattr(table, "extract_one", slow_extract)
    ticks = []

    with pytest.raises(table.Stopped):
        table.run(chunks, COLUMNS, model=None, should_stop=lambda: len(ticks) >= 2 or ticks.append(1))

    assert len(read) < len(chunks), f"every one of the {len(chunks)} chunks was read anyway"


def test_a_failed_run_drops_the_chunks_it_had_not_started(monkeypatch):
    many = [{"id": f"f:{i}", "text": f"text {i}", "pages": [i], "headings": []} for i in range(12)]
    read: list[str] = []

    def boom(text, columns, model, request):
        read.append(text)
        time.sleep(0.1)
        if text.endswith(" 1"):
            raise RuntimeError("model refused")
        return fake_rows([["item", "2027"]])

    monkeypatch.setattr(settings, "llm_concurrency", 2)
    monkeypatch.setattr(table, "extract_one", boom)

    with pytest.raises(RuntimeError, match="model refused"):
        table.run(many, COLUMNS, model=None)

    assert len(read) < len(many), "a failed run paid for the whole document"


def cited(chunk_id: str, n: int = 1) -> dict:
    return {"n": n, "chunk_id": chunk_id, "pages": [1], "headings": [], "source": "table", "text": chunk_id}


def row(values: dict, *chunk_ids: str) -> dict:
    return {"values": values, "citations": [cited(c) for c in chunk_ids]}


def test_an_item_found_in_several_chunks_becomes_one_row_citing_every_chunk(monkeypatch, chunks):
    # The same obligation is found in chunks 0 and 2; chunk 1 holds a different one
    found = {"text 0": [["bayar", ""]], "text 1": [["lapor", "10 Mei"]], "text 2": [["bayar", "31 Jan"]]}
    monkeypatch.setattr(table, "extract_one", lambda text, columns, model, request: fake_rows(found[text.split(":")[0]]))
    monkeypatch.setattr(table, "find_duplicates", lambda rows, columns, model: [[0, 2]])

    rows = table.run(chunks[:3], COLUMNS, model=None)

    assert [r["values"] for r in rows] == [
        {"Kewajiban": "bayar", "Tenggat": "31 Jan"},  # the empty deadline is filled from its duplicate
        {"Kewajiban": "lapor", "Tenggat": "10 Mei"},
    ]
    assert [c["chunk_id"] for c in rows[0]["citations"]] == ["f:0", "f:2"]
    assert [c["n"] for c in rows[0]["citations"]] == [1, 2], "a merged row numbers its citations like chat"


def test_distinct_items_are_not_merged(monkeypatch, chunks):
    monkeypatch.setattr(table, "extract_one", lambda text, columns, model, request: fake_rows([[text, ""]]))

    rows = table.run(chunks[:3], COLUMNS, model=None)

    assert len(rows) == 3


def test_merge_ignores_numbers_that_are_out_of_range_repeated_or_already_grouped():
    # Identical values, so this is only about which numbers are honoured, not about contradictions
    rows = [row({"Kewajiban": "bayar"}, f"f:{i}") for i in range(4)]

    merged = table.merge_rows(rows, [[0, 1, 1, 99], [1, 2], [3]])

    # [1, 2] loses 1 to the first group, which leaves a group of one: nothing to merge
    assert [[c["chunk_id"] for c in r["citations"]] for r in merged] == [["f:0", "f:1"], ["f:2"], ["f:3"]]


def test_a_merged_row_cites_a_chunk_once_even_if_both_duplicates_came_from_it():
    rows = [row({"Kewajiban": "a"}, "f:0"), row({"Kewajiban": "a"}, "f:0", "f:1")]

    [merged] = table.merge_rows(rows, [[0, 1]])

    assert [c["chunk_id"] for c in merged["citations"]] == ["f:0", "f:1"]


def test_a_failed_merge_keeps_the_rows_unmerged_rather_than_losing_the_table(monkeypatch, chunks):
    def boom(rows, columns, model):
        raise RuntimeError("model refused")

    monkeypatch.setattr(table, "extract_one", lambda text, columns, model, request: fake_rows([["item", ""]]))
    monkeypatch.setattr(table, "find_duplicates", boom)

    assert len(table.run(chunks[:3], COLUMNS, model=None)) == 3


def test_there_is_no_merge_pass_when_there_is_nothing_to_merge(monkeypatch, chunks):
    def must_not_run(rows, columns, model):
        raise AssertionError("a single row cannot have a duplicate")

    monkeypatch.setattr(table, "extract_one", lambda text, columns, model, request: fake_rows([["item", ""]]))
    monkeypatch.setattr(table, "find_duplicates", must_not_run)

    assert len(table.run(chunks[:1], COLUMNS, model=None)) == 1


def test_find_duplicates_shows_the_model_every_row_by_number(monkeypatch):
    seen = {}

    class FakeModel:
        def with_structured_output(self, schema):
            return self

        def invoke(self, messages):
            seen["prompt"] = messages[-1][1]
            return table.DuplicateGroups(groups=[[0, 1]])

    monkeypatch.setattr(table, "llm", lambda model=None, **kw: FakeModel())
    rows = [row({"Kewajiban": "bayar", "Tenggat": ""}, "f:0"), row({"Kewajiban": "bayar", "Tenggat": "31 Jan"}, "f:2")]

    assert real_find_duplicates(rows, COLUMNS, None) == [[0, 1]]
    assert "0. Kewajiban: bayar" in seen["prompt"] and "1. Kewajiban: bayar | Tenggat: 31 Jan" in seen["prompt"]


def test_rows_the_model_groups_but_that_contradict_each_other_stay_apart():
    # Measured on a real document: Qwen3.5-4B grouped these, and they are different parameters
    rows = [
        row({"Parameter": "prev_overlap", "Nilai": "satu chunk dari section tetangga"}, "f:6"),
        row({"Parameter": "next_overlap", "Nilai": "satu chunk dari section tetangga"}, "f:6"),
        row({"Parameter": "db", "Nilai": "Konfigurasi request"}, "f:9"),
        row({"Parameter": "user_id", "Nilai": "Konfigurasi request"}, "f:9"),
    ]

    assert len(table.merge_rows(rows, [[0, 1], [2, 3]])) == 4


def test_the_same_item_stated_more_fully_or_left_blank_elsewhere_still_merges():
    rows = [
        row({"Kewajiban": "menyediakan tenaga ahli", "Tenggat": "paling lambat 15 Februari 2027"}, "f:1"),
        row({"Kewajiban": "Menyediakan tenaga ahli.", "Tenggat": "15 Februari 2027"}, "f:4"),
        row({"Kewajiban": "menyediakan tenaga ahli bersertifikat", "Tenggat": ""}, "f:7"),
    ]

    [merged] = table.merge_rows(rows, [[0, 1, 2]])

    assert [c["chunk_id"] for c in merged["citations"]] == ["f:1", "f:4", "f:7"]


def test_one_contradicting_member_leaves_the_group_and_the_rest_still_merge():
    rows = [
        row({"Kewajiban": "laporan bulanan", "Tenggat": "tanggal 10"}, "f:0"),
        row({"Kewajiban": "laporan bulanan", "Tenggat": "31 Maret"}, "f:3"),  # a different deadline: not the same item
        row({"Kewajiban": "laporan bulanan", "Tenggat": ""}, "f:5"),
    ]

    merged = table.merge_rows(rows, [[0, 1, 2]])

    assert [[c["chunk_id"] for c in r["citations"]] for r in merged] == [["f:0", "f:5"], ["f:3"]]


def test_two_obligations_that_differ_by_one_word_stay_apart_even_with_no_deadline_to_tell_them_apart():
    # "bulanan" and "tahunan" share half their words with each other; that is exactly the case a
    # word-overlap rule cannot tell from a paraphrase, so the rule errs on keeping them apart
    rows = [
        row({"Kewajiban": "menyerahkan laporan bulanan", "Tenggat": ""}, "f:0"),
        row({"Kewajiban": "menyerahkan laporan tahunan", "Tenggat": ""}, "f:3"),
    ]

    assert len(table.merge_rows(rows, [[0, 1]])) == 2


def test_a_value_the_passage_does_not_say_is_blanked_and_an_empty_row_is_dropped(monkeypatch):
    passage = [{"id": "f:0", "text": "PERDA  Provinsi Jawa Timur Nomor 9 Tahun 2024 tentang APBD", "pages": [1], "headings": []}]
    monkeypatch.setattr(table, "extract_one", lambda text, columns, model, request: fake_rows([
        ["Perda Provinsi Jawa Timur Nomor 9 Tahun 2024", "masih berlaku"],  # re-spaced quote kept, invented status blanked
        ["2", "9"],  # "2" is not in the passage; "9" is, as a word
        ["tidak disebutkan", ""],  # nothing quoted at all: not a row
    ]))

    rows = table.run(passage, COLUMNS, model=None)

    assert [r["values"] for r in rows] == [
        {"Kewajiban": "Perda Provinsi Jawa Timur Nomor 9 Tahun 2024", "Tenggat": ""},
        {"Kewajiban": "", "Tenggat": "9"},
    ]


def test_the_request_reaches_every_chunk_read(monkeypatch):
    seen = []
    monkeypatch.setattr(table, "read_structured", lambda schema, messages, model, max_tokens: seen.append(messages) or fake_rows([]))

    table.extract_one("passage", COLUMNS, None, "every regulation that is a legal basis")

    assert "Request:\nevery regulation that is a legal basis" in seen[0][1][1]


def test_a_configured_table_model_takes_every_table_call_over_the_documents_model(monkeypatch):
    monkeypatch.setattr(settings, "table_llm_model", "deepseek-ai/deepseek-v4.1-flash")
    monkeypatch.setattr(table, "table_llm", lambda **options: ("table", options))
    monkeypatch.setattr(table, "llm", lambda *a, **kw: pytest.fail("the document's model was used"))

    assert table.chat("Qwen3.5-4B", max_tokens=3000) == ("table", {"max_tokens": settings.table_llm_max_tokens})


def headed(i: int, heading: str) -> dict:
    return {"id": f"f:{i}", "text": f"{heading}\nbody {i}", "pages": [i], "headings": [heading]}


SCOPED_DOC = [headed(0, "Landasan hukum"), headed(1, "Landasan hukum"), headed(2, "Katalog website"), headed(3, "Kontak")]


def test_scope_reads_only_the_parts_the_model_picks_with_the_whole_outline_in_view(monkeypatch):
    seen = []

    def pick(schema, messages, model, max_tokens):
        seen.append(messages[1][1])
        return table.ScopedParts(parts=[1, 99])  # 99 does not exist and is ignored

    monkeypatch.setattr(table, "read_structured", pick)

    chosen = table.scope("landasan hukum layanan", SCOPED_DOC, None)

    assert [c["id"] for c in chosen] == ["f:0", "f:1"], "a part is every chunk under its heading"
    assert "1. Landasan hukum -- body 0" in seen[0] and "2. Katalog website" in seen[0] and "3. Kontak" in seen[0]


def test_scope_shows_the_captions_of_the_tables_a_part_holds(monkeypatch):
    seen = []
    monkeypatch.setattr(table, "read_structured", lambda schema, messages, model, max_tokens: seen.append(messages[1][1]) or table.ScopedParts(parts=[2]))
    results = {"id": "f:t5", "caption": "Table 6: Absolute impression metrics"}
    doc = [
        {"id": "f:0", "text": "Methods\nWe propose nine methods", "headings": ["Methods"], "tables": []},
        {"id": "f:1", "text": "Methods\n0, Count = 19", "headings": ["Methods"], "tables": [results]},
        {"id": "f:2", "text": "Methods\n1, Count = 21", "headings": ["Methods"], "tables": [results]},
        {"id": "f:3", "text": "Results\nWe ran five seeds", "headings": ["Results"], "tables": []},
    ]

    table.scope("every method in Table 6", doc, None)

    assert "1. Methods -- We propose nine methods [tables: Table 6: Absolute impression metrics]\n" in seen[0]
    parts = seen[0].split("Parts:\n")[1]
    assert parts.endswith("2. Results -- We ran five seeds"), "a part without tables shows none"
    assert parts.count("Table 6") == 1, "a table spanning a part's chunks is listed once"


@pytest.mark.parametrize("answer", [table.ScopedParts(parts=[]), table.ScopedParts(parts=[0, 7]), RuntimeError("down")])
def test_scope_reads_the_whole_document_when_it_gets_no_usable_answer(monkeypatch, answer):
    def reply(*_):
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(table, "read_structured", reply)

    assert table.scope("anything", SCOPED_DOC, None) == SCOPED_DOC


def test_part_titles_name_each_run_of_chunks_under_one_heading_once():
    assert table.part_titles(SCOPED_DOC) == ["Landasan hukum", "Katalog website", "Kontak"]
    assert table.part_titles([{"id": "f:0", "text": "x", "headings": []}]) == ["-"]


def doc_table(rows: int, table_id: str = "f:t0") -> dict:
    body = "\n".join(f"| {i} | bayar termin {i} | {i} Mei 2027 |" for i in range(rows))
    return {"id": table_id, "idx": 0, "caption": "Daftar kewajiban", "pages": [3, 4],
            "regions": [{"page": 3, "l": 0, "t": 0, "r": 1, "b": 1, "page_width": 600, "page_height": 800}],
            "markdown": f"| No | Kewajiban | Tenggat |\n|----|----|----|\n{body}"}


def test_a_table_spread_over_two_chunks_is_read_once_whole_and_cited_as_the_table(monkeypatch):
    spread = doc_table(3)
    chunks = [
        {"id": "f:0", "text": "0, Kewajiban = bayar termin 0", "prose": "Pasal 1 pembuka", "pages": [3],
         "headings": ["Pasal 1"], "tables": [spread]},
        {"id": "f:1", "text": "2, Kewajiban = bayar termin 2", "prose": "", "pages": [4],
         "headings": ["Pasal 1"], "tables": [spread]},
    ]
    tables_read, passages_read = [], []
    monkeypatch.setattr(table, "extract_from_table",
                        lambda text, columns, model, request: tables_read.append(text) or fake_rows([["bayar termin 1", "1 Mei 2027"]]))
    monkeypatch.setattr(table, "extract_one", lambda text, columns, model, request: passages_read.append(text) or fake_rows([]))
    progress: list[tuple[int, int]] = []

    rows = table.run(chunks, COLUMNS, model=None, on_progress=lambda done, total: progress.append((done, total)))

    assert tables_read == ["Daftar kewajiban\n\n" + spread["markdown"]], "the table goes in once, whole, with its caption"
    assert passages_read == ["Pasal 1 pembuka"], "a chunk holding a table is read as its prose, never its triplet text"
    [citation] = rows[0]["citations"]
    assert (citation["chunk_id"], citation["pages"], citation["regions"]) == ("f:0", [3, 4], spread["regions"])
    assert progress == [(2, 2)], "progress counts chunks, done once the reads behind them are"


def test_a_long_table_is_read_in_batches_each_under_its_header(monkeypatch):
    long = doc_table(100)
    read = []
    monkeypatch.setattr(table, "extract_from_table", lambda text, columns, model, request: read.append(text) or fake_rows([]))

    table.run([{"id": "f:0", "text": "t", "prose": "", "pages": [3], "headings": [], "tables": [long]}], COLUMNS)

    assert len(read) == 3
    header = "Daftar kewajiban\n\n| No | Kewajiban | Tenggat |\n|----|----|----|\n"
    assert all(batch.startswith(header) for batch in read)
    assert [batch.count("bayar termin") for batch in read] == [40, 40, 20]
    assert "| 40 | bayar termin 40 |" in read[1] and "| 39 |" not in read[1]


def test_a_value_from_a_table_is_checked_against_the_table_not_the_chunk(monkeypatch):
    chunks = [{"id": "f:0", "text": "triplet text only", "prose": "", "pages": [3], "headings": [],
               "tables": [doc_table(2)]}]
    monkeypatch.setattr(table, "extract_from_table",
                        lambda text, columns, model, request: fake_rows([["bayar termin 1", "31 Desember 2099"]]))

    [found] = table.run(chunks, COLUMNS)

    assert found["values"] == {"Kewajiban": "bayar termin 1", "Tenggat": ""}


def test_the_table_prompt_frames_its_text_as_a_table_with_a_larger_cap(monkeypatch):
    seen = {}

    class FakeModel:
        def with_structured_output(self, schema):
            return self

        def invoke(self, messages):
            seen["messages"] = messages
            return fake_rows([])

    def build(model=None, *, temperature=0.0, max_tokens=None):
        seen["max_tokens"] = max_tokens
        return FakeModel()

    monkeypatch.setattr(table, "llm", build)

    table.extract_from_table("| a | b |", COLUMNS, None, "kewajiban")

    (_, system), (_, human) = seen["messages"]
    assert system == prompts.EXTRACT_TABLE
    assert human.endswith("Table:\n| a | b |") and human.startswith("Request:\nkewajiban")
    assert seen["max_tokens"] == table.TABLE_EXTRACT_MAX_TOKENS


def test_a_chunk_ingested_before_tables_were_kept_is_read_from_its_text(monkeypatch, chunks):
    read = []
    monkeypatch.setattr(table, "extract_from_table", lambda *a: pytest.fail("no table to read"))
    monkeypatch.setattr(table, "extract_one", lambda text, columns, model, request: read.append(text) or fake_rows([]))

    # No table_ids on the node: list_chunks returns them as None, and the API resolves that to no tables
    table.run([{**c, "table_ids": None, "prose": None, "tables": []} for c in chunks], COLUMNS)

    assert read == [c["text"] for c in chunks]
