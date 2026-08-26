# Phase A — Borderless Core Fix

This patch separates physical OCR rows from logical multiline rows in `BorderlessTableDetector`.

## What changed

1. `_cluster_rows()` output is preserved as `physical_rows`.
2. `_merge_continuations()` produces independent `logical_rows` and no longer mutates the physical rows in place.
3. Column anchors are inferred from `physical_rows`, not merged logical rows.
4. Output rows are built from `logical_rows`.
5. Diagnostics now include:
   - `physical_row_count`
   - `logical_row_count`
   - `column_inference_source = physical_rows`
   - existing `row_count` remains as a backward-compatible alias.
6. Added a regression test proving column topology does not change when multiline row merging changes the logical-row count.

## Validation

`pytest`: 28 passed, 5 skipped.
The 5 skipped tests are the existing E2E uploaded-file tests because their environment variables were not configured in the validation container.

## Important

This is Phase A only. It does NOT yet add automatic anchor-zone discovery or automatic table ROI isolation.
Do not promote the experimental Rajhi-specific JSON values into `configs/default.yaml`.
