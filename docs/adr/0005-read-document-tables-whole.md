# 5. Read a document's own tables whole, not from their chunk text

Date: 2026-10-05

## Status

Accepted

## Context

A Table Extraction reads chunk text. Docling recognises the tables printed in a document (header,
rows, columns), but at chunking time `HybridChunker` flattens each one into triplet text
(`row, column = value`, docling_core's `TripletTableSerializer`), and a table longer than
`CHUNK_MAX_TOKENS` is split over several chunks wherever the token budget runs out. Converting a
Markdown file with one 60-row table gave four chunks for it, cut mid-row: one ended
`17, Tenggat` and the next began `= 2027-09-01`. The model then has to rediscover the rows from
that text, chunk by chunk, and a row cut in two is seen whole by neither read. The `DoclingDocument`
was thrown away after ingest, so the structure was lost.

## Decision

Ingest keeps every table Docling recognises as a `DocTable` node: its Markdown (the export's cell
padding collapsed), caption, pages and regions. Each Chunk records the tables it holds
(`table_ids`) and, only when it holds one, its `prose`: its headings and other items without the
table.

A Table Extraction reads each table touched by the chosen chunks once, whole, at the first of those
chunks, in batches of `TABLE_BATCH_ROWS` rows under the repeated header. It reads each chunk's
`prose` instead of its `text` when the chunk holds a table, so the table's rows are not read a second
time from its triplets. A row from a table is quote-checked against that table's Markdown and cites
the table's pages and regions, so its Highlight is the table. A table is read when any of its chunks
is chosen, and the merge pass folds rows found both in a table and in the text around it.

The scope pass also lists the captions of the tables each part holds. A table can sit under a
heading that says nothing about it: in `2311.09735v3.pdf`, "Table 6" (results) is under "B.4 GEO
Methods", and with only headings and openings in view the scope chose "C RESULTS" and the run found
no rows. With the captions shown, it chose "B.4 GEO Methods" on both of two tries.

Chunk text, embeddings and retrieval for questions are unchanged.

## Consequences

- A document ingested before this has no `table_ids` and keeps the chunk-by-chunk behaviour. Getting
  the new path needs a re-ingest, so `POST /documents/{id}/retry` now also accepts a finished
  Document (still refused while an ingest runs).
- A table Docling misreads stays misread: there is no chunk-text fallback for a table it recognised.
  A table whose Markdown export is empty is not kept, and its chunks keep their triplet text.
- One large table is one read per batch instead of one per chunk, and no row is cut at a chunk
  boundary. A batch's answer can be longer than a chunk's, so table reads get a larger output cap
  (`TABLE_EXTRACT_MAX_TOKENS`), not yet measured.
- A paragraph too long for one chunk is split into segments that share it as their item; a segment
  merged into a chunk with a table gives back the whole paragraph as `prose`, so its rows can come
  twice and lean on the merge pass.
- Progress still counts chunks: a chunk is done once every read up to it is.
