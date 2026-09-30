# docs-analyzer

A document analyzer: people upload a document, ask it questions, and pull structured tables
out of it, with every answer and every row traceable back to the place in the document it
came from. Built as both a public open-source repo and the company's client demo.

## Documents

**Document**:
One uploaded file, together with everything derived from it: its chunks, sections, graph,
turns and table extractions.
_Avoid_: File, upload, doc

**Original**:
The uploaded file exactly as received, kept so a citation can open the real page.
_Avoid_: Source file, raw file

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
A numbered reference from an answer or a row to the chunk that supports it.
_Avoid_: Source, reference

**Highlight**:
The visible mark over the cited passage on a page of the original.
_Avoid_: Annotation, selection

**Region**:
One bounding box on one page of the Original that a chunk came from; a citation's regions are what
get marked as Highlights.
_Avoid_: Box, bbox, span

## Table Extraction

**Table Extraction**:
A user-requested pass over a whole document that produces a table of every matching item.
_Avoid_: Extraction (alone), structured extraction, data extraction

**Suggested Table**:
A table the model proposes from the document alone, before the user has described one: a title and
its columns, offered as a starting point to edit.
_Avoid_: Template, preset

**Column**:
One field a table extraction collects, defined by a name and a description; proposed by the
model from the user's request and edited by the user before the run.
_Avoid_: Field, attribute

**Row**:
One item found by a table extraction, with a value per column and its citations.
_Avoid_: Record, entry
