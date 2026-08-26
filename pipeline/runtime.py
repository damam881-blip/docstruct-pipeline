from __future__ import annotations

import random
from typing import Any

import numpy as np


def configure_runtime_determinism(config: dict[str, Any]) -> dict[str, Any]:
    """Apply best-effort reproducibility controls for one pipeline process.

    ``project.deterministic`` and ``project.random_seed`` used to be metadata
    only. They now seed Python/NumPy and, when available, PyTorch. In
    deterministic mode cuDNN benchmarking is disabled and deterministic
    algorithms are requested with ``warn_only=True`` so unsupported operations
    are surfaced without making the PDF pipeline unusable.

    This is best-effort rather than a mathematical guarantee: OCR libraries,
    hardware drivers, and some OpenCV/PyTorch kernels can still vary slightly
    across platforms or dependency versions.
    """

    project_cfg = config.get("project", {})
    deterministic = bool(project_cfg.get("deterministic", True))
    seed = int(project_cfg.get("random_seed", 42))

    status: dict[str, Any] = {
        "deterministic": deterministic,
        "random_seed": seed,
        "python_seeded": False,
        "numpy_seeded": False,
        "torch_seeded": False,
        "torch_deterministic_algorithms": False,
    }

    if not deterministic:
        return status

    random.seed(seed)
    status["python_seeded"] = True

    # NumPy's legacy global RNG accepts a 32-bit unsigned seed.
    np.random.seed(seed % (2**32))
    status["numpy_seeded"] = True

    try:
        import torch
    except Exception:
        return status

    torch.manual_seed(seed)
    status["torch_seeded"] = True

    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

    cudnn = getattr(getattr(torch, "backends", None), "cudnn", None)
    if cudnn is not None:
        cudnn.benchmark = False
        cudnn.deterministic = True

    use_deterministic_algorithms = getattr(torch, "use_deterministic_algorithms", None)
    if callable(use_deterministic_algorithms):
        try:
            use_deterministic_algorithms(True, warn_only=True)
            status["torch_deterministic_algorithms"] = True
        except TypeError:
            # Older supported torch builds may not expose warn_only.
            try:
                use_deterministic_algorithms(True)
                status["torch_deterministic_algorithms"] = True
            except Exception:
                pass
        except Exception:
            pass

    return status
