# 6. Show documents without pages as text blocks, not as rendered HTML

Date: 2026-10-28

## Status

Accepted

## Context

A citation opens the Original's page with Highlights (ADR 3), but only a PDF has pages to render. A
picture's OCR regions are in its own pixels, so it can be shown as a one-page Original. DOCX, HTML,
Markdown, PPTX, XLSX and CSV have no page to draw a box on, so their Highlight has to mark something
else (#22). Two ways to show them:

- **Rendered HTML**: Docling's HTML export, with every item wrapped in an element carrying its ref.
  The stock export has no ids, so this needs a custom serializer. Uploaded HTML, Markdown and DOCX can
  carry scripts and links, so the output also needs a sanitizer, and React would inject it with
  `dangerouslySetInnerHTML`.
- **Text blocks**: the Converted Document's items in reading order as JSON (heading, paragraph, list
  item, table grid), each keyed by its Docling ref, rendered by React as plain text.

## Decision

Text blocks. Ingest keeps the Converted Document as JSON under `DATA_DIR/docling/`, and each Chunk
stores the refs of the items it came from (`Chunk.refs`). A table chunk is narrowed to
`{ref}/rows/{n}` for the rows whose "row, column = value" triplets are in its text.
`GET /documents/{id}/view` returns the blocks, and the source panel and viewer dialog mark every block
or table row a citation's refs name. PPTX blocks carry their slide number, so slides show as cards.

## Consequences

- Nothing in an uploaded file can run in the app: React escapes all text, and no sanitizer or new
  dependency is needed.
- The view is not the original's look. Styling, embedded pictures and links are dropped, and a slide
  is a card of its text, not an image of the slide. Real slide images need LibreOffice on the server.
- Row matching assumes one header row. A table with more is cited whole, and a row whose triplet a
  long table's chunk boundary cuts in two is marked in neither chunk.
- Documents ingested before this have no Converted Document, so `/view` is 404 and their citations
  show the cited text only, until they are ingested again ("Try again").
- One more JSON file per Document, deleted with it. PDFs keep one too although their viewer does not
  use it.
