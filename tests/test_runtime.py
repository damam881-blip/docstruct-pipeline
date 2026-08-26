from __future__ import annotations

import random

import numpy as np

from pipeline.runtime import configure_runtime_determinism


def test_project_seed_is_operational():
    config = {"project": {"deterministic": True, "random_seed": 12345}}

    first_status = configure_runtime_determinism(config)
    first_python = random.random()
    first_numpy = float(np.random.random())

    second_status = configure_runtime_determinism(config)
    second_python = random.random()
    second_numpy = float(np.random.random())

    assert first_status["python_seeded"] is True
    assert first_status["numpy_seeded"] is True
    assert second_status["random_seed"] == 12345
    assert first_python == second_python
    assert first_numpy == second_numpy


def test_deterministic_false_does_not_claim_to_seed():
    status = configure_runtime_determinism(
        {"project": {"deterministic": False, "random_seed": 123}}
    )
    assert status["deterministic"] is False
    assert status["python_seeded"] is False
    assert status["numpy_seeded"] is False
