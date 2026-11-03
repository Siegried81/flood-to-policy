"""
scoring.py - Normalisation, weights, priority scores, missing-data treatment, evidence quality, sensitivity.

    S = 100 × M × (Wp·P + Wb·B + Wf·F) / (sum of the weights of the AVAILABLE indicators)

P, B, F in [0, 1] (normalised exposure), M in [0.5, 1] (facility or infrastructure factor; M = 1 for areas).
A missing indicator (NaN) is excluded and the remaining weights are renormalised; the bounded range
[missing = 0, missing = 1] is reported alongside. The browser (priority/map.js) implements the same formula.
"""
import itertools

import numpy as np
import pandas as pd

DEFAULT_WEIGHTS = {"P": 0.4, "B": 0.3, "F": 0.3}   # illustrative starting point, not an optimum
REF_QUANTILE = 0.99
TOP_N = 25                                         # sensitivity: share of weight scenarios in the top N
F_STATUS = {
    "flooded": "Asset inside the observed flooded area (water on image)",
    "trace": "Asset inside an observed flood trace (water already receded)",
    "near": "Not flooded at the asset; flooding observed in its ~1 km² neighbourhood",
    "dry": "Mapped by EMS, no flooding detected in the neighbourhood",
    "unmapped": "Outside EMS mapping coverage: historical flooding unknown (not 'safe')",
}


# --------------------------------------------------------------------------- normalisation
def reference(values, q=REF_QUANTILE):
    """Upper reference = q-quantile of the positive values (study-wide, fixed: filters do not change it)."""
    v = np.asarray(values, float)
    v = v[np.isfinite(v) & (v > 0)]
    return float(np.quantile(v, q)) if len(v) else 1.0


def norm_log(x, ref):
    """log(1 + x) / log(1 + ref), capped at 1. For heavy-tailed counts (residents, buildings). NaN stays NaN."""
    x = np.asarray(x, float)
    return np.minimum(1.0, np.log1p(np.maximum(x, 0)) / np.log1p(ref))


def norm_linear(x, ref):
    """x / ref, capped at 1. For the flooded share (a bounded proportion). NaN stays NaN."""
    x = np.asarray(x, float)
    return np.minimum(1.0, np.maximum(x, 0) / ref)


def normalize_weights(w):
    """Weights scaled to sum to 1. Negative values are invalid; all-zero falls back to equal weights."""
    w = np.asarray([w["P"], w["B"], w["F"]] if isinstance(w, dict) else w, float)
    if (w < 0).any() or not np.isfinite(w).all():
        raise ValueError(f"weights must be finite and >= 0, got {w}")
    return w / w.sum() if w.sum() > 0 else np.full(3, 1 / 3)


# --------------------------------------------------------------------------- scores
def score(X, w, M=1.0):
    """X: (n, 3) array of P, B, F with NaN for missing. Returns dict of arrays:
    score (renormalised over available indicators), lo / hi (missing set to 0 / 1), contributions c_P, c_B, c_F
    (points of the score; they add up to `score`). Rows with no available indicator get NaN."""
    X = np.atleast_2d(np.asarray(X, float))
    w = normalize_weights(w)
    M = np.broadcast_to(np.asarray(M, float), X.shape[:1])
    avail = np.isfinite(X)
    wa = np.where(avail, w, 0.0)
    wsum = wa.sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        contrib = 100 * M[:, None] * wa * np.nan_to_num(X) / wsum[:, None]
    s = np.where(wsum > 0, contrib.sum(axis=1), np.nan)
    lo = 100 * M * (w * np.where(avail, X, 0.0)).sum(axis=1)
    hi = 100 * M * (w * np.where(avail, X, 1.0)).sum(axis=1)
    out = {"score": s, "lo": lo, "hi": hi}
    for k, name in enumerate("PBF"):
        out[f"c_{name}"] = np.where((wsum > 0) & avail[:, k], contrib[:, k], np.nan)   # missing: NaN, not 0
    return out


def type_factor(importance):
    """M = 0.5 + 0.5 × I: the type can at most halve the exposure score, never create priority without exposure."""
    return 0.5 + 0.5 * np.asarray(importance, float)


def facility_importance(dependency, overnight):
    """I = (D + O) / 2; unknown components take the mid value 0.5 (flagged as assumed)."""
    d = pd.Series(dependency, dtype=float).fillna(0.5).to_numpy()
    o = pd.Series(overnight, dtype=float).fillna(0.5).to_numpy()
    return (d + o) / 2


# --------------------------------------------------------------------------- indicators -> P, B, F
def hex_PBF(hx, refs):
    """Normalised indicators of hexagon neighbourhoods; B missing where OBAT has a gap, F missing outside coverage."""
    P = norm_log(hx["n_pop"], refs["pop"])
    B = np.where(hx["b_gap"], np.nan, norm_log(hx["n_bldg"], refs["bldg"]))
    F = norm_linear(hx["flood_share"], refs["flood_share"])
    return np.column_stack([P, B, F])


def asset_PBF(a, refs):
    """As hex_PBF, but F is measured at the asset first: 1 if its geometry touches the observed extent,
    otherwise the neighbourhood flooded share (over the mapped part); missing if the asset lies outside coverage."""
    P = norm_log(a["n_pop"], refs["pop"])
    B = np.where(a["b_gap"].fillna(False).astype(bool), np.nan, norm_log(a["n_bldg"], refs["bldg"]))
    hit = a["hit_flooded"] | a["hit_trace"]
    near = norm_linear(a["flood_share_mapped"], refs["flood_share"])
    F = np.where(hit, 1.0, np.where(a["in_mapped"], np.nan_to_num(near), np.nan))
    status = np.select([a["hit_flooded"], a["hit_trace"], ~a["in_mapped"], np.nan_to_num(near) > 0],
                       ["flooded", "trace", "unmapped", "near"], "dry")
    return np.column_stack([P, B, F]), status


def quality(a, status):
    """Evidence-quality flags and level (kept separate from the score). Returns (list of flag lists, level array)."""
    flags = []
    for i, row in enumerate(a.itertuples()):
        f = []
        if status[i] == "unmapped":
            f.append("F_unmapped")
        if bool(row.b_gap):
            f.append("B_gap")
        if row.country == "BEL" and status[i] in ("dry", "near"):
            f.append("BE_detection")
        if getattr(row, "assumed", False) is True:
            f.append("type_assumed")
        if row.post_2021:
            f.append("post_2021")
        flags.append(f)
    severe = {"F_unmapped", "B_gap"}
    level = np.array(["Low" if (severe & set(f)) or len(f) >= 2 else "Medium" if f else "High" for f in flags])
    return flags, level


def weight_grid(step=0.1, minimum=0.1):
    """All weight triples on the simplex with the given step and a minimum per weight (36 scenarios by default)."""
    k = int(round(1 / step))
    m = int(round(minimum / step))
    return np.array([(i / k, j / k, (k - i - j) / k) for i, j in itertools.product(range(m, k + 1), repeat=2)
                     if k - i - j >= m])


def ranked(X):
    """Items eligible for ranking: historical flooding (F) known. Without F a renormalised score is not comparable
    (a dense city outside EMS coverage would reach 100 on P and B alone), so these get 'insufficient evidence'."""
    return np.isfinite(np.atleast_2d(np.asarray(X, float))[:, 2])


def sensitivity(X, M, top_n=TOP_N, grid=None):
    """Rank the eligible items under each weight scenario. Returns best rank, worst rank and the share of
    scenarios in which the item is in the top N (1 = robust whatever the weights); NaN for non-eligible items."""
    grid = weight_grid() if grid is None else grid
    X = np.atleast_2d(np.asarray(X, float))
    ok = ranked(X)
    out = [np.full(len(X), np.nan) for _ in range(3)]
    if ok.any():
        M = np.broadcast_to(np.asarray(M, float), X.shape[:1])[ok]
        S = np.column_stack([score(X[ok], w, M)["score"] for w in grid])
        S = np.nan_to_num(S, nan=-1)
        ranks = (-S).argsort(axis=0, kind="stable").argsort(axis=0, kind="stable") + 1
        out[0][ok], out[1][ok], out[2][ok] = ranks.min(axis=1), ranks.max(axis=1), (ranks <= top_n).mean(axis=1)
    return tuple(out)
