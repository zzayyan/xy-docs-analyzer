# docs-analyzer

A document analyzer: people upload a document and ask it questions, with every answer
traceable back to the place in the document it came from. Built as both a public open-source
repo and the company's client demo.

## Documents

**Document**:
One uploaded file, together with everything derived from it: its chunks, sections, graph
and turns.
_Avoid_: File, upload, doc

**Original**:
The uploaded file exactly as received, kept so a citation can open the real page.
_Avoid_: Source file, raw file

**Converted Document**:
Docling's reading of the Original (headings, paragraphs, slides, tables), kept so a document without
pages can be shown with its cited passages marked.
_Avoid_: Docling JSON, parsed document

**Short Document**:
A document small enough that questions are answered from its chunks alone.
_Avoid_: Small doc

**Long Document**:
A document past the length threshold, which additionally gets sections and a knowledge graph.
_Avoid_: Big doc, large doc

**Chunk**:
A contiguous passage of a document, the smallest unit that can be retrieved and cited.
_Avoid_: Passage, block, segment

**Section**:
A node in a long document's outline, following its heading structure.
_Avoid_: Chapter, heading, node

**Document Language**:
The language a document is written in, which may differ from the language a question is asked in.

## Knowledge graph

**Knowledge Graph**:
The entities a long document mentions and the relationships between them.
_Avoid_: KG (in prose), graph (alone, ambiguous with the database)

**Graph Extraction**:
Building a document's knowledge graph, done automatically during ingest.
_Avoid_: Extraction (alone), entity extraction

## Asking

**Turn**:
One question and the answer given to it, with that answer's citations.
_Avoid_: Message, exchange

**Citation**:
A numbered reference from an answer to the chunk that supports it.
_Avoid_: Source, reference

**Table Calculation**:
A total, average, count, minimum, maximum, ranking or listing the backend computes over every row of
a spreadsheet's sheet, after the model picks the operation; cited first, with the rows it used.
_Avoid_: Aggregation (alone), table query, SQL

**Highlight**:
The visible mark over the cited passage: on a page of the Original for a PDF or a picture, on the
Converted Document's text for every other format.
_Avoid_: Annotation, selection

**Region**:
One bounding box on one page of the Original that a chunk came from; a citation's regions are what
get marked as Highlights.
_Avoid_: Box, bbox, span
