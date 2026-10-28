import re
from dataclasses import dataclass
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.ingest.convert import converted_path, sheet_tables
from app.models import llm
from app.prompts import retrieval as prompts

# A sum over thousands of rows would otherwise send every row's ref with the citation
# ponytail: only the first rows are marked in the viewer; page through the cited rows if that matters
MAX_CITED_ROWS = 500
SAMPLE_VALUES = 3


class Filter(BaseModel):
    column: str
    op: Literal["=", "!=", ">", ">=", "<", "<=", "contains"]
    value: str


class TableOperation(BaseModel):
    """What the model asks the backend to compute; every name is checked against the table before running."""

    operation: Literal["none", "sum", "avg", "count", "min", "max", "top_n", "list"] = Field(
        description='"none" when the question is not a calculation, count, ranking or listing over the rows',
    )
    sheet: str | None = Field(default=None, description="The sheet's name; leave empty when there is one")
    column: str | None = Field(default=None, description="The column summed, averaged, ranked or compared")
    filters: list[Filter] = []
    group_by: str | None = Field(default=None, description="A column whose values each get their own result")
    limit: int | None = Field(default=None, description="How many rows top_n or list gives")
    ascending: bool = Field(default=False, description="top_n: smallest first instead of largest")


@dataclass
class Table:
    name: str
    ref: str
    header: list[str]
    # Keyed by the grid row number, so "{ref}/rows/{n}" marks the same row in the document view
    rows: dict[int, list[str]]
    # A "Total" row at the bottom, kept out of every operation so nothing is counted twice
    totals_row: int | None = None

    @classmethod
    def from_grid(cls, name: str, ref: str, grid: list[list[str]]) -> "Table":
        header = [cell.strip() for cell in grid[0]]
        rows = {i: [cell.strip() for cell in row] for i, row in enumerate(grid[1:], start=1)}
        last = max(rows, default=None)
        totals_row = last if last and rows[last][0].lower().startswith(TOTALS) else None
        rows.pop(totals_row, None)
        return cls(name, ref, header, rows, totals_row)


TOTALS = ("total", "grand total", "subtotal", "jumlah")
DEFAULT_LIMIT = {"top_n": 5, "list": 20}


CURRENCY = re.compile(r"^(rp\.?|idr|usd|\$|€)\s*")


def parse_number(text: str) -> float | None:
    """ "Rp 1.250.000", "2,500,000", "1,5" and "750000.5" alike; None for anything that is not a number."""
    core = CURRENCY.sub("", text.strip().lower()).replace(" ", "")
    negative = core.startswith("-")
    core = core.lstrip("-")
    if not re.fullmatch(r"\d[\d.,]*", core):
        return None
    if "." in core and "," in core:
        # The separator written last is the decimal one
        decimal = "." if core.rfind(".") > core.rfind(",") else ","
        core = core.replace("," if decimal == "." else ".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}([.,]\d{3})+", core):
        # ponytail: a number with exactly three decimals ("1.125") reads as thousands, as Indonesian writes them
        core = core.replace(".", "").replace(",", "")
    else:
        core = core.replace(",", ".")
    try:
        value = float(core)
    except ValueError:
        return None
    return -value if negative else value


def parse_date(text: str) -> date | None:
    """ISO dates ("2024-01-15", "2024-01-15 00:00:00") and day-first ones ("15/01/2024", "15-01-2024")."""
    # ponytail: two formats; month names ("15 Januari 2024") stay text
    try:
        if m := re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", text.strip()):
            return date(int(m[1]), int(m[2]), int(m[3]))
        if m := re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", text.strip()):
            return date(int(m[3]), int(m[2]), int(m[1]))
    except ValueError:
        return None
    return None


def number_text(value: float) -> str:
    return str(int(value)) if value == int(value) else str(round(value, 4))


def column_index(table: Table, name: str) -> int:
    for i, column in enumerate(table.header):
        if column.lower() == name.strip().lower():
            return i
    raise ValueError(f'no column "{name}" in {table.name}; columns: {", ".join(table.header)}')


def comparable(cell: str, value: str) -> tuple:
    """Both as numbers, else both as dates, else both as lowercase text."""
    for parse in (parse_number, parse_date):
        if (left := parse(cell)) is not None and (right := parse(value)) is not None:
            return left, right
    return cell.lower(), value.strip().lower()


def matches(cell: str, condition: Filter) -> bool:
    if condition.op == "contains":
        return condition.value.lower() in cell.lower()
    left, right = comparable(cell, condition.value)
    return {
        "=": left == right, "!=": left != right,
        ">": left > right, ">=": left >= right, "<": left < right, "<=": left <= right,
    }[condition.op]


def aggregate(operation: str, cells: dict[int, str]) -> tuple[str, list[int]]:
    """One aggregate over a column's cells keyed by row number: its value as text, and the rows it used."""
    if operation == "count":
        return str(len(cells)), list(cells)
    numbers = {n: v for n, cell in cells.items() if (v := parse_number(cell)) is not None}
    if operation in ("sum", "avg"):
        if not numbers:
            raise ValueError("the column holds no numbers")
        total = sum(numbers.values())
        return number_text(total if operation == "sum" else total / len(numbers)), list(numbers)
    # min and max: numbers when the column has any, else dates
    values = numbers or {n: v for n, cell in cells.items() if (v := parse_date(cell)) is not None}
    if not values:
        raise ValueError("the column holds no numbers or dates")
    extreme = (min if operation == "min" else max)(values.values())
    text = number_text(extreme) if numbers else extreme.isoformat()
    return text, [n for n, v in values.items() if v == extreme]


def describe(table: Table, row: list[str]) -> str:
    return ", ".join(f"{column} = {cell}" for column, cell in zip(table.header, row) if cell)


def pick(tables: list[Table], sheet: str | None) -> Table:
    if not sheet:
        return tables[0]
    for table in tables:
        if table.name.lower() == sheet.strip().lower():
            return table
    raise ValueError(f'no sheet "{sheet}"; sheets: {", ".join(t.name for t in tables)}')


def rank(op: TableOperation, table: Table, rows: dict[int, list[str]], column: int) -> tuple[list[str], list[int]]:
    values = {n: v for n, row in rows.items() if (v := parse_number(row[column])) is not None}
    values = values or {n: v for n, row in rows.items() if (v := parse_date(row[column])) is not None}
    if not values:
        raise ValueError("the column holds no numbers or dates")
    ranked = sorted(values, key=values.get, reverse=not op.ascending)[:op.limit or DEFAULT_LIMIT["top_n"]]
    return [f"{i}. {describe(table, rows[n])}" for i, n in enumerate(ranked, start=1)], ranked


def run(op: TableOperation, tables: list[Table]) -> dict:
    """The operation's result as a context block's text, plus the refs of the rows it used."""
    table = pick(tables, op.sheet)
    rows = dict(table.rows)
    for condition in op.filters:
        i = column_index(table, condition.column)
        rows = {n: row for n, row in rows.items() if matches(row[i], condition)}
    column = column_index(table, op.column) if op.column else None
    where = " where " + " and ".join(f"{f.column} {f.op} {f.value}" for f in op.filters) if op.filters else ""
    heading = f'Sheet "{table.name}", {len(rows)} of {len(table.rows)} rows{where}.'

    if op.operation == "top_n":
        if column is None:
            raise ValueError("top_n needs a column to rank by")
        ranked, used = rank(op, table, rows, column)
        lines = [f"{'Smallest' if op.ascending else 'Largest'} by {table.header[column]}:", *ranked]
    elif op.operation == "list":
        used = sorted(rows)[:op.limit or DEFAULT_LIMIT["list"]]
        more = f" (first {len(used)})" if len(used) < len(rows) else ""
        lines = [f"Rows{more}:", *(describe(table, rows[n]) for n in used)]
    else:
        expression = f"{op.operation.upper()}({table.header[column] if column is not None else '*'})"
        cells = lambda group: {n: row[column] if column is not None else "" for n, row in group.items()}
        if op.group_by:
            g = column_index(table, op.group_by)
            groups: dict[str, dict[int, list[str]]] = {}
            for n, row in rows.items():
                groups.setdefault(row[g], {})[n] = row
            lines, used = [f"{expression} by {table.header[g]}:"], []
            for key, group in groups.items():
                value, group_used = aggregate(op.operation, cells(group))
                lines.append(f"{key or '(empty)'}: {value} ({len(group_used)} rows)")
                used += group_used
        else:
            value, used = aggregate(op.operation, cells(rows))
            lines = [f"{expression if column is not None else 'COUNT'} = {value} ({len(used)} rows)"]

    if table.totals_row:
        lines.append(f"Row {table.totals_row} is a Total/Jumlah row and was left out.")
    refs = [f"{table.ref}/rows/{n}" for n in sorted(used)]
    return {"sheet": table.name, "text": "\n".join([heading, *lines]), "refs": refs}


def load_tables(doc_id: str) -> list[Table]:
    """The Converted Document's tables; none for a Document converted before those were kept."""
    path = converted_path(doc_id)
    return [Table.from_grid(*table) for table in sheet_tables(path)] if path.exists() else []


def column_kind(table: Table, i: int) -> str:
    cells = [row[i] for row in table.rows.values() if row[i]]
    for kind, parse in (("number", parse_number), ("date", parse_date)):
        if cells and sum(parse(cell) is not None for cell in cells) >= 0.8 * len(cells):
            return kind
    return "text"


def schema(tables: list[Table]) -> str:
    """What the model picks names from: each sheet's columns, their kind and a few of their values."""
    lines = []
    for table in tables:
        lines.append(f'Sheet "{table.name}", {len(table.rows)} rows:')
        for i, column in enumerate(table.header):
            samples = list(dict.fromkeys(row[i] for row in table.rows.values() if row[i]))[:SAMPLE_VALUES]
            lines.append(f"- {column} ({column_kind(table, i)}), e.g. {'; '.join(samples)}")
    return "\n".join(lines)


def search(doc_id: str, question: str, model: str | None = None) -> list[dict]:
    """The computed answer to a calculation over a spreadsheet, as one context block; none for any other question."""
    tables = load_tables(doc_id)
    if not tables:
        return []
    try:
        op = llm(model).with_structured_output(TableOperation).invoke([
            ("system", prompts.TABLE_OPERATION.format(schema=schema(tables))), ("human", question),
        ])
        if op.operation == "none":
            return []
        result = run(op, tables)
    except Exception:
        # A column the table lacks, or a failed call: vector search still answers
        return []
    return [{
        "id": "table:result",
        "text": result["text"],
        "pages": [], "headings": [result["sheet"]], "regions": [], "refs": result["refs"][:MAX_CITED_ROWS],
        "source": "table",
    }]
