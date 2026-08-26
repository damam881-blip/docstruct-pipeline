from __future__ import annotations

import numpy as np
from sklearn.cluster import DBSCAN

from models import WordBox


def detect_column_anchors(words: list[WordBox], x_tolerance: float = 15.0) -> list[float]:
    if not words:
        return []
    x = np.array([[w.bbox.center[0]] for w in words], dtype=np.float32)
    labels = DBSCAN(eps=x_tolerance, min_samples=1).fit_predict(x)
    return sorted(float(np.median(x[labels == label])) for label in set(labels) if label >= 0)
