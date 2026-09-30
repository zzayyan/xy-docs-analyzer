# 4. Scope a Table Extraction to the parts of the document that answer it

Date: 2026-09-30

## Status

Accepted

## Context

A Table Extraction reads every chunk on its own and returns the rows each one holds. On
`RANGKUMAN WEBSITE JDIH (1).pdf` (46 chunks), the request "Kumpulkan semua peraturan dan keputusan
yang menjadi landasan hukum bagi layanan informasi hukum di Jawa Timur" is answered by 5
regulations, all in chunks 0 and 1. Measured:

- Qwen3.5-4B, with the request in the per-chunk prompt: 80 rows.
- Nemotron-3-Super-120B, same prompt: 73 rows. The 5 right ones, complete and quoted correctly, then
  the website's whole catalogue: every Perda, Pergub, Kepgub, Surat Edaran and court ruling it lists
  as an example of its services.

A passage listing "PERDA Provinsi Jawa Timur Nomor 2 Tahun 2025 ..." under "APA SAJA LAYANAN PADA
WEBSITE JDIH ?" reads, on its own, like an answer to "semua peraturan". Only seeing that heading next
to "BAGAIMANA LANDASAN DAN REGULASI LAYANAN INFORMASI HUKUM ...?" shows it is not. A bigger model
did not fix this; a step that sees the whole document does.

## Decision

Before extraction, one model call gets the request and the document's parts (consecutive chunks
under the same headings), each shown as its heading and the first words of its text, and returns
the parts to read. Only those parts' chunks are extracted.

The call fails open: a failed call, no valid part, or more than `SCOPE_MAX_PARTS` parts to show reads
the whole document. The prompt tells the model to return every part when the request asks for every
item of its kind anywhere in the document, or when it cannot tell.

## Consequences

- This relaxes "a partial table would silently claim to cover the whole document" (the reason one
  failed chunk fails a whole run). The run now reads what the scope chose, and its `chunks_total`
  counts those chunks, not the document's.
- A wrong scope misses rows without saying so, where the old behaviour only added noise the user
  could see and delete. Failing open on every doubtful answer keeps that risk to a wrong confident
  answer.
- A scoped run is also cheaper: fewer chunks read, fewer rows to merge.
- Past `SCOPE_MAX_PARTS` parts the listing no longer fits a small model's context and the whole
  document is read. Scoping section by section is the upgrade if long documents need it.
