# 1. Read a chunk again off-greedy when the model runs away

Date: 2026-09-18

## Status

Accepted

## Context

A Table Extraction over a 25-chunk document failed with:

```
Could not parse response content as the length limit was reached -
CompletionUsage(completion_tokens=16060, prompt_tokens=324, total_tokens=16384)
```

Two of the 25 chunks made Qwen3.5-4B on vLLM emit ~16k tokens of repeated rows and hit the context
window, every single time. One failing chunk fails the whole run, so a document with one awkward
passage produced no table at all.

Measured on the failing chunk, one variable at a time:

| Change | Result |
| --- | --- |
| none (temperature 0) | fails, 15968 completion tokens, 110s |
| `temperature=0.7` | succeeds, 11 rows |
| drop the `Unit` column | succeeds |
| empty column descriptions | succeeds |
| "return at most 20 rows" in the prompt | fails |
| `max_tokens=800` | fails in 7s instead of 110s |

So the cause is degenerate repetition under greedy decoding, not a prompt the model misunderstands:
the same prompt reads cleanly as soon as decoding is not greedy. A column the passage has no values
for (`Unit`) is what invites the repetition, and no prompt wording stops it once it starts.

## Decision

`extract_one` reads each chunk with an output cap (`EXTRACT_MAX_TOKENS`), and reads it once more at
`RETRY_TEMPERATURE` if the first, greedy read raises. A chunk that fails both reads still fails the
whole run.

Temperature and the cap are set when the client is built, not bound onto it afterwards:
`with_structured_output()` drops a kwarg passed to `.bind()`, which silently left an intended cap
with no effect at all.

## Consequences

- A runaway chunk costs one wasted capped read (~20s) instead of failing the run.
- Retried chunks are read at a non-zero temperature, so their rows are not reproducible the way the
  rest of the table is. The run stays correct; it is no longer bit-for-bit repeatable.
- The cap bounds every chunk's output. A chunk whose honest table really is longer than
  `EXTRACT_MAX_TOKENS` would be truncated and retried needlessly; at `CHUNK_MAX_TOKENS` per chunk
  that is not a shape a real chunk reaches.
- Prompt-only mitigations were tried and rejected: they do not survive greedy decoding.
