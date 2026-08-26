# Phase A.1 — Safety Correction

The first Phase A experiment inferred column topology from raw physical OCR lines.
That exposed a semantic mismatch in the existing column-support heuristic: its
`minimum_column_support_ratio` denominator was designed around logical rows.
Using physical lines inflated the denominator and removed legitimate sparse
columns (Rajhi verification: 25 rows, 3 columns).

Phase A.1 keeps the safe part of the refactor:

- physical OCR row groups are preserved and never mutated;
- logical multiline rows are reconstructed on copies;
- diagnostics expose physical vs logical row counts;
- column inference temporarily remains on logical rows to preserve current
  behavior until a later topology/ROI phase replaces the support heuristic.

This is deliberately a safety correction, not the final column-topology fix.

## Debug visibility

`pipeline/pipeline.py` now writes detector measurements under
`page_report.json -> structure_diagnostics.borderless`, including:

- `physical_row_count`
- `logical_row_count`
- `column_count`
- `column_inference_source`
