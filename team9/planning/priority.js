/*
 * priority.js - Scenario-based planning priority of the fixed 400 m hexagons (pure functions, no DOM).
 *
 * For each hexagon i with estimated exposed residents P_i > 0 and U_i of them unassigned in the current scenario:
 *   E_i = 100 × min(1, log(1 + P_i) / log(1 + P99))     exposure; P99 fixed over the whole study area
 *   G_i = 100 × U_i / P_i                                scenario gap
 *   S_i = wE × E_i + wG × G_i                            weights >= 0, normalised to sum to 1
 * Hexagons without exposed residents are excluded. All-zero weights give NO score (explicit state, no fallback).
 * Uncertainty is not a score component: missing information is reported separately by the page.
 */
(function (root) {
  function weights(wE, wG) {
    if (!(wE >= 0) || !(wG >= 0) || !isFinite(wE) || !isFinite(wG)) throw new Error('weights must be finite and >= 0');
    var s = wE + wG;
    return s > 0 ? {E: wE / s, G: wG / s, zero: false} : {E: 0, G: 0, zero: true};
  }

  function exposure(P, p99) { return P > 0 ? 100 * Math.min(1, Math.log1p(P) / Math.log1p(p99)) : null; }

  // hexes: [{P}], unassigned: U per hexagon (same order). Returns per hexagon {E, G, S} (null if excluded),
  // the order of the scored hexagons (S desc, then P desc, then index) and whether G differentiates at all.
  function score(hexes, unassigned, p99, wE, wG) {
    var w = weights(wE, wG), rows = [], gMin = Infinity, gMax = -Infinity;
    hexes.forEach(function (h, i) {
      if (!(h.P > 0)) { rows.push(null); return; }
      var U = Math.min(Math.max(unassigned[i], 0), h.P);   // guard rounding: 0 <= U <= P
      var E = exposure(h.P, p99), G = 100 * U / h.P;
      gMin = Math.min(gMin, G); gMax = Math.max(gMax, G);
      rows.push({E: E, G: G, U: U, S: w.zero ? null : w.E * E + w.G * G});
    });
    var order = [];
    rows.forEach(function (r, i) { if (r) order.push(i); });
    if (!w.zero) order.sort(function (a, b) { return (rows[b].S - rows[a].S) || (hexes[b].P - hexes[a].P) || (a - b); });
    else order = [];
    return {rows: rows, order: order, w: w, gConstant: gMax - gMin < 1e-9, gValue: gMin};
  }

  var api = {weights: weights, exposure: exposure, score: score};
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.AreaPriority = api;
})(typeof window !== "undefined" ? window : this);
