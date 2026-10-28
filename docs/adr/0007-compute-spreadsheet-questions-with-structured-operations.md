# 7. Compute spreadsheet questions with structured operations, not SQL

Date: 2026-10-28

## Status

Accepted

## Context

A spreadsheet's rows become sentence chunks, and at most 8,000 tokens of the best chunks reach the
model. A lookup ("berapa harga paket Pro?") works. A total, average, count, ranking or listing over
many rows does not: the model sees only some rows and does the arithmetic itself (#23). The options:

- **Text-to-SQL**: load each sheet into SQLite and let the model write the query. It covers any
  question, but a 4B model writes SQL unreliably, and free SQL widens what a crafted question can do.
- **Structured operation**: the model fills one Pydantic model (`sum | avg | count | min | max | top_n
  | list`, a column, filters, `group_by`, a limit), and the backend checks every name against the
  sheet and computes the result in Python.

The tables also need a home: typed Parquet files written at ingest, or the Converted Document that
ingest keeps since ADR 6.

## Decision

Structured operations, computed from the Converted Document. `app/retrieval/table.py` reads its
tables at question time, parses numbers ("Rp 1.250.000", "1,5") and dates (ISO and day-first), and
leaves out a "Total"/"Jumlah" row at the bottom. A `table_query` node runs next to vector search for
XLSX and CSV Documents only. Its result is the first context block, marked for the answer prompt as
computed, and its citation (`source: "table"`) carries the operation's text and the refs of the rows
it used, so the table viewer marks them.

## Consequences

- No new storage or ingest step, and row numbers match the viewer's by construction. Documents
  converted before ADR 6 have no tables and keep the vector path only.
- Questions outside the seven operations (ratios, a sum of two columns, joins across sheets) still go
  through vector search.
- The model can pick a wrong column or filter. The citation shows the operation so the reader can
  check it, and an unknown name falls back to vector search instead of failing.
- A small model also picks an operation for some lookups (a one-row list). The answer stays correct,
  with one extra citation.
- One more LLM call per question on spreadsheets. It runs in parallel with vector search.
- Number parsing reads "1.125" as 1125, the Indonesian way. A value with exactly three decimals written
  with a dot is misread.
