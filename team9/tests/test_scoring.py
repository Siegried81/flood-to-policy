"""Scoring: normalisation, weights, bounds, missing data, the hand-computed synthetic example, sensitivity."""
import numpy as np
import pandas as pd
import pytest

from priority import scoring as sc

NAN = np.nan


# --------------------------------------------------------------------------- weights
def test_weights_are_normalised():
    assert np.allclose(sc.normalize_weights({"P": 40, "B": 30, "F": 30}), [0.4, 0.3, 0.3])
    assert np.allclose(sc.normalize_weights([2, 1, 1]), [0.5, 0.25, 0.25])
    assert np.allclose(sc.normalize_weights([0, 0, 0]), [1 / 3] * 3)
    assert sc.normalize_weights([0.2, 0.7, 0.9]).sum() == pytest.approx(1)


def test_negative_weight_rejected():
    with pytest.raises(ValueError):
        sc.normalize_weights([-1, 1, 1])


def test_default_weights_sum_to_one():
    assert sum(sc.DEFAULT_WEIGHTS.values()) == pytest.approx(1)


# --------------------------------------------------------------------------- normalisation
def test_norm_log_bounds_and_cap():
    x = np.array([0, 1, 99, 1000, 5000, NAN])
    n = sc.norm_log(x, ref=1000)
    assert n[0] == 0 and n[3] == pytest.approx(1) and n[4] == 1  # capped above the reference
    assert np.all(np.diff(n[:4]) > 0)                            # monotonic
    assert np.isnan(n[5])                                        # missing stays missing, never 0


def test_norm_linear():
    n = sc.norm_linear([0, 0.2, 0.4, 0.9, NAN], ref=0.4)
    assert np.allclose(n[:4], [0, 0.5, 1, 1]) and np.isnan(n[4])


def test_reference_ignores_zeros_and_nan():
    v = np.r_[np.zeros(1000), np.arange(1, 101), [NAN] * 10]
    assert sc.reference(v, q=0.99) == pytest.approx(np.quantile(np.arange(1, 101), 0.99))


def test_outlier_does_not_dominate():
    """One extreme value changes the reference only through the 99th percentile; others keep their spread."""
    base = np.arange(1, 1001, dtype=float)
    ref1, ref2 = sc.reference(base), sc.reference(np.r_[base, 1e7])
    assert ref2 / ref1 < 1.01
    assert sc.norm_log(500, ref2) == pytest.approx(sc.norm_log(500, ref1), rel=0.01)


# --------------------------------------------------------------------------- scores
def test_score_bounds_and_contributions():
    rng = np.random.default_rng(0)
    X = rng.random((500, 3))
    X[rng.random((500, 3)) < 0.2] = NAN
    for _ in range(20):
        w, M = rng.random(3), 0.5 + 0.5 * rng.random(500)
        r = sc.score(X, w, M)
        ok = np.isfinite(r["score"])
        assert np.all((r["score"][ok] >= 0) & (r["score"][ok] <= 100))
        assert np.all(r["lo"][ok] <= r["score"][ok] + 1e-9) and np.all(r["score"][ok] <= r["hi"][ok] + 1e-9)
        parts = np.nansum(np.column_stack([r["c_P"], r["c_B"], r["c_F"]]), axis=1)
        assert np.allclose(parts[ok], r["score"][ok])


def test_extremes():
    assert sc.score([[1, 1, 1]], [1, 1, 1])["score"][0] == pytest.approx(100)
    assert sc.score([[0, 0, 0]], [1, 1, 1])["score"][0] == 0
    assert np.isnan(sc.score([[NAN, NAN, NAN]], [1, 1, 1])["score"][0])


# --------------------------------------------------------------------------- synthetic example (computed by hand)
A = [0.9, 0.5, 0.8]    # high population, moderate buildings, strong historical flooding
B = [0.5, 0.9, 0.1]    # moderate population, high buildings, limited observed flooding
C = [0.9, 0.5, NAN]    # like A but outside EMS coverage: flooding unknown


@pytest.mark.parametrize("w, sA, sB", [
    ([0.4, 0.3, 0.3], 75.0, 50.0),          # 100·(.4·.9 + .3·.5 + .3·.8) = 75 ; 100·(.4·.5 + .3·.9 + .3·.1) = 50
    ([1, 1, 1], 220 / 3, 50.0),             # equal weights: (0.9+0.5+0.8)/3, (0.5+0.9+0.1)/3
    ([0.1, 0.8, 0.1], 57.0, 78.0),          # buildings-led: 9+40+8 = 57 ; 5+72+1 = 78  -> B overtakes A
])
def test_synthetic_ranking_changes_with_weights(w, sA, sB):
    s = sc.score([A, B], w)["score"]
    assert s == pytest.approx([sA, sB])


def test_unknown_flooding_is_not_safe():
    r = sc.score([C], [0.4, 0.3, 0.3])
    assert r["score"][0] == pytest.approx(100 * (0.36 + 0.15) / 0.7)   # 72.86: renormalised over P and B
    assert r["lo"][0] == pytest.approx(51) and r["hi"][0] == pytest.approx(81)  # F = 0 ... F = 1
    assert r["c_F"][0] != 0 and np.isnan(r["c_F"][0])                  # no zero contribution invented
    assert not sc.ranked([C])[0]                                        # status: insufficient evidence
    safe = sc.score([[0.9, 0.5, 0.0]], [0.4, 0.3, 0.3])["score"][0]    # what "unmapped = 0" would have given
    assert r["score"][0] > safe


def test_type_factor():
    assert sc.type_factor(1) == 1 and sc.type_factor(0) == 0.5
    I = sc.facility_importance([1.0, 0.5, None], [1, 0, None])          # hospital, school, unknown sub-type
    assert np.allclose(I, [1.0, 0.25, 0.5])
    assert np.allclose(sc.type_factor(I), [1.0, 0.625, 0.75])
    # the factor scales but never creates priority: zero exposure stays zero
    assert sc.score([[0, 0, 0]], [1, 1, 1], M=1.0)["score"][0] == 0


# --------------------------------------------------------------------------- sensitivity and reproducibility
def test_weight_grid():
    g = sc.weight_grid()
    assert len(g) == 36 and np.allclose(g.sum(axis=1), 1) and g.min() >= 0.1 - 1e-12
    assert len(np.unique(g.round(6), axis=0)) == 36


def test_sensitivity():
    X = np.array([[1, 1, 1], A, B, [0.1, 0.1, 0.1], C])
    best, worst, top = sc.sensitivity(X, np.ones(5), top_n=1)
    assert best[0] == worst[0] == 1 and top[0] == 1          # dominates under every weight set
    assert best[3] == worst[3] == 4                           # dominated under every weight set
    assert best[1] == 2 and best[2] == 2 and worst[1] == 3    # A and B swap places with the weights
    assert np.isnan(best[4]) and np.isnan(top[4])             # unknown F: not ranked


def test_reproducible():
    rng = np.random.default_rng(1)
    X = rng.random((200, 3))
    r1, r2 = sc.sensitivity(X, 1.0), sc.sensitivity(X, 1.0)
    for a, b in zip(r1, r2):
        assert np.array_equal(a, b)
    assert np.array_equal(sc.score(X, [1, 2, 3])["score"], sc.score(X, [1, 2, 3])["score"])


def test_quality_flags():
    a = pd.DataFrame({"b_gap": [False, True, False, False], "country": ["DEU", "DEU", "BEL", "DEU"],
                      "assumed": [False, False, False, True], "post_2021": [False, False, False, True]})
    flags, level = sc.quality(a, np.array(["flooded", "unmapped", "dry", "near"]))
    assert flags[0] == [] and level[0] == "High"
    assert set(flags[1]) == {"F_unmapped", "B_gap"} and level[1] == "Low"
    assert flags[2] == ["BE_detection"] and level[2] == "Medium"
    assert level[3] == "Low"   # two flags
