from __future__ import annotations

import os

import pytest

from config import ConfigResolver
from pipeline.pipeline import UniversalPDFPipeline


CASES = [
    ("PDF_TEST_FILE_1", [1]),
    ("PDF_TEST_FILE_2", [1]),
    ("PDF_TEST_FILE_3", [1, 2, 3]),
    ("PDF_TEST_FILE_4", [1, 2, 10]),
    ("PDF_TEST_FILE_5", [1, 2, 3, 4]),
]


@pytest.mark.parametrize("env_name,pages", CASES)
def test_e2e_representative_pages_with_same_generic_config(tmp_path, env_name, pages):
    input_path = os.environ.get(env_name)
    if not input_path:
        pytest.skip(f"{env_name} not configured")
    resolver = ConfigResolver("configs/default.yaml")
    output = tmp_path / f"{env_name}.xlsx"
    pipeline = UniversalPDFPipeline(resolver, debug=False)
    results = pipeline.extract(
        input_path,
        output,
        pages=pages,
        debug_root=tmp_path / "debug",
    )
    if pipeline.last_output_summary["excel_enabled"]:
        assert output.exists()
    else:
        assert not output.exists()
        assert pipeline.last_output_summary["artifact_directory"]
    assert len(results) == len(pages)
    assert all(result.analysis.page_number in pages for result in results)
