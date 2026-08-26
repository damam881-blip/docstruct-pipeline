# Phase A — Safe Minimal Patch

This patch is built from the live `BorderlessTableDetector` methods extracted from the validated project.

It intentionally changes only two methods inside `pipeline/borderless_table_detector.py`:

1. `detect()` now names and preserves `physical_rows` separately from `logical_rows`.
2. `_merge_continuations()` copies row lists before merging so the physical row source is not mutated in-place.

Column inference intentionally remains on `logical_rows` in Phase A. This preserves current extraction behavior while making the physical geometry available for later phases.

The patch does **not** replace or modify:

- `pipeline/pipeline.py`
- `config.py`
- `configs/default.yaml`
- any existing test file

It creates a new regression test only:

`tests/test_borderless_physical_logical_rows.py`

The patcher refuses to modify the source if the exact live methods it was built against are not present.
