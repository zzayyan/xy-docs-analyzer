# 2. Merge only the rows that do not contradict each other

Date: 2026-09-18

## Status

Deprecated: Table Extraction was removed on 2026-10-23.

## Context

A Table Extraction ends with one model pass that groups the rows describing the same item, so the
table has no duplicates (#6). Measured against Qwen3.5-4B:

- On five synthetic rows with two planted duplicates and one look-alike ("laporan bulanan" vs
  "laporan tahunan"), the model found both duplicates and kept the look-alike apart, three runs out
  of three.
- On a real 25-chunk document (99 rows), it returned 45 groups covering 53 rows, the same answer every
  run, and nearly every group joined different items: `prev_overlap` with `next_overlap`, `db` with
  `user_id`, `EMBEDDING_CHUNK_TOKEN_BUDGET` with `_section_max_tokens()`. Several groups paired row
  `i` with row `i + 12`, a positional pattern rather than a reading.

Merging those rows would put one item's values and citations under another's name, which corrupts
the table silently. The merge pass cannot be trusted as-is on a table of real size.

Word overlap of the whole row does not separate right groups from wrong ones: distinct parameters
sharing filler values ("Konfigurasi request", "Tidak disebutkan") scored 0.67, and `prev_overlap` /
`next_overlap` scored 0.87, above either of the true synthetic duplicates (0.45, 0.64).

## Decision

The model proposes groups, and `merge_rows` admits a row into a group only if it contradicts no row
already in it. Two values of a column are compatible when one is empty, when one's words are all
contained in the other's, or when they share more than `SAME_VALUE_OVERLAP` of their words. Any
incompatible column keeps the rows apart, whatever the model said.

The threshold sits deliberately above one half. "menyerahkan laporan bulanan" and "menyerahkan
laporan tahunan" share exactly half their words and are different obligations; the paraphrase
"menyediakan tenaga ahli" / "Disediakan tenaga ahli" also shares exactly half and is the same one. No
word-overlap rule can tell those two cases apart, so it errs on keeping rows apart.

## Consequences

- On the real document, every one of the 45 model groups is vetoed and the table keeps its 99 rows:
  no merge, and no wrong merge.
- On the synthetic rows, the verbatim restatement merges and the paraphrased one does not.
- A missed duplicate is one extra row the user can see and delete; a wrong merge hides an item inside
  another. The rule trades the first for the second on purpose.
- The model's grouping is still what finds candidates, so a stronger model merges more without a code
  change. A smarter compatibility check (stemming, a second model call per group) is the upgrade if
  paraphrased duplicates turn out to matter.
