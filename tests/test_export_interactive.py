"""Tests for scripts/export_interactive.py (the web's interactive-map data).

The heavy path reads EMS gpkgs and the 3 GB hazard rasters, which CI does not
have, so it is exercised by hand. Here we check the pure, offline parts: the
depth palette is internally consistent and the class-index arithmetic lines up
with the legend the browser uses to read a click back to a depth class.
"""
from __future__ import annotations

import numpy as np

from scripts import export_interactive as X


def test_depth_palette_is_internally_consistent():
    """One label and one colour per class, so the legend and the PNG agree."""
    assert len(X.DEPTH_BREAKS) == len(X.DEPTH_LABELS) == len(X.DEPTH_COLOURS)
    assert all(a < b for a, b in zip(X.DEPTH_BREAKS, X.DEPTH_BREAKS[1:]))  # strictly rising
    assert all(len(c) == 3 and all(0 <= v <= 255 for v in c) for c in X.DEPTH_COLOURS)


def test_digitize_maps_depths_to_the_expected_class_index():
    """`np.digitize` on the breaks: 0 is dry, then one index per class, as the
    export and the browser's legend both assume (class i uses colour i-1)."""
    depths = np.array([0.0, 0.05, 0.1, 0.3, 0.7, 1.5, 3.0, 6.0, 12.0])
    classes = np.digitize(depths, X.DEPTH_BREAKS)
    # < 0.1 m -> 0 (dry/transparent); 0.1-0.5 -> 1; ... >= 8 -> 6
    assert list(classes) == [0, 0, 1, 1, 2, 3, 4, 5, 6]
    assert classes.max() == len(X.DEPTH_COLOURS)  # deepest class has a colour
