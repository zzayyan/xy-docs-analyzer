# 3. Render Original pages server-side, not with a client-side PDF library

Date: 2026-09-30

## Status

Accepted

## Context

Highlighting a cited passage (#5) needs a picture of the Original's page to draw the Highlight boxes
on. Two ways to get one:

- **Client-side**: ship `pdfjs-dist` to the browser, render the page to a `<canvas>`, position
  Highlights in the PDF viewport's transformed pixel space.
- **Server-side**: render the page to a PNG with `pypdfium2` and serve it like any other image; the
  browser just shows an `<img>`.

`pypdfium2` is already installed (a transitive dependency of `docling`, imported directly in
`convert.py` for `page_count`/`has_text_layer`) and never used for rendering. No PDF library exists in
the frontend today, and adding one means a worker script, bundler/CORS considerations, and a viewport
coordinate transform for every Highlight box.

## Decision

Render pages server-side. `GET /documents/{id}/original/pages/{n}` returns a PNG
(`pypdfium2`, `RENDER_SCALE = 2`, roughly 144 DPI); the response is cached forever
(`Cache-Control: public, max-age=31536000, immutable`) since an Original never changes once kept.

Regions are stored per Chunk with their own page's width/height in PDF points, so a Highlight box is
placed with plain percentages of the `<img>`'s box (`left: 100*l/page_width` etc.) -- no pixel-space
transform, no dependency on the render scale matching anything client-side.

## Consequences

- Zero new frontend dependency, zero worker/bundler/CORS setup.
- `pypdfium2` is promoted from an undeclared transitive import to a direct dependency in
  `pyproject.toml` -- fixing a pre-existing gap, not adding a new cost.
- No text layer, no in-browser search or selection inside the rendered page. Not asked for by the
  spec; add `pdfjs-dist` later if that changes.
- A page with `/Rotate 90` renders rotated by pdfium while Docling's page size may report the
  unrotated box, which would misplace a Highlight on such a page. Not seen in testing; a
  `ponytail:`-worthy ceiling if a real document hits it.
- Every render is a fresh request; no cache is kept beyond the browser's own, no measurement suggested
  one is needed (`pypdfium2` renders a page in tens of milliseconds).
