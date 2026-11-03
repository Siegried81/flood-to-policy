/*
 * alloc.js - Shelter planning scenario: assign estimated residents to facility places (pure functions, no DOM).
 *
 * allocate(origins, facilities, maxDist) solves a maximum flow:
 *   source -> origin (estimated residents) -> facility (if straight-line distance <= maxDist) -> sink (places)
 * with Dinic's algorithm on real-valued capacities. The total assigned is the largest possible under the three
 * constraints (origin residents, facility places, distance); nothing is counted twice because every origin can
 * send at most its own residents. Among equally large solutions, nearer facilities are tried first (edges are
 * sorted by distance), but the result is NOT guaranteed to minimise distances.
 *
 * gapReasons(...) explains, per origin, why residents remain unassigned (see GAP).
 * Coordinates are metres in EPSG:3035 (equal-area; straight-line distances are accurate to < 0.1 % here).
 */
(function (root) {
  var EPS = 1e-9;

  // Uniform grid over points for "everything within d" queries
  function grid(points, cell) {
    var g = {};
    points.forEach(function (p, i) {
      var k = Math.floor(p.x / cell) + ':' + Math.floor(p.y / cell);
      (g[k] = g[k] || []).push(i);
    });
    return {
      near: function (x, y, d) {
        var out = [], cx = Math.floor(x / cell), cy = Math.floor(y / cell), r = Math.ceil(d / cell);
        for (var i = cx - r; i <= cx + r; i++) for (var j = cy - r; j <= cy + r; j++) {
          var b = g[i + ':' + j]; if (!b) continue;
          for (var n = 0; n < b.length; n++) {
            var p = points[b[n]], dd = Math.hypot(p.x - x, p.y - y);
            if (dd <= d) out.push([b[n], dd]);
          }
        }
        return out;
      }
    };
  }

  function allocate(origins, facilities, maxDist) {
    // nodes: 0 = source, 1 = sink, 2.. origins, then facilities
    var nO = origins.length, nF = facilities.length, N = 2 + nO + nF;
    var head = new Array(N).fill(-1), to = [], cap = [], next = [], dist = [];
    function edge(u, v, c, d) {
      to.push(v); cap.push(c); next.push(head[u]); dist.push(d); head[u] = to.length - 1;
      to.push(u); cap.push(0); next.push(head[v]); dist.push(d); head[v] = to.length - 1;
    }
    // facility -> sink first (so head order does not matter for them)
    facilities.forEach(function (f, k) { if (f.cap > EPS) edge(2 + nO + k, 1, f.cap, 0); });
    var g = grid(facilities, Math.max(maxDist, 1));
    origins.forEach(function (o, i) {
      if (!(o.demand > EPS)) return;
      edge(0, 2 + i, o.demand, 0);
      // adjacency lists are LIFO: insert farthest first so the nearest facility is tried first
      g.near(o.x, o.y, maxDist).filter(function (e) { return facilities[e[0]].cap > EPS; })
        .sort(function (a, b) { return b[1] - a[1] || b[0] - a[0]; })
        .forEach(function (e) { edge(2 + i, 2 + nO + e[0], Infinity, e[1]); });
    });

    var level = new Int32Array(N), it = new Int32Array(N);
    function bfs() {
      level.fill(-1); level[0] = 0;
      var q = [0];
      for (var h = 0; h < q.length; h++) {
        for (var e = head[q[h]]; e !== -1; e = next[e]) {
          if (cap[e] > EPS && level[to[e]] < 0) { level[to[e]] = level[q[h]] + 1; q.push(to[e]); }
        }
      }
      return level[1] >= 0;
    }
    function dfs(u, f) {
      if (u === 1) return f;
      for (; it[u] !== -1; it[u] = next[it[u]]) {
        var e = it[u], v = to[e];
        if (cap[e] > EPS && level[v] === level[u] + 1) {
          var d = dfs(v, Math.min(f, cap[e]));
          if (d > EPS) { cap[e] -= d; cap[e ^ 1] += d; return d; }
        }
      }
      return 0;
    }
    var total = 0;
    while (bfs()) {
      for (var n = 0; n < N; n++) it[n] = head[n];
      var f;
      while ((f = dfs(0, Infinity)) > EPS) total += f;
    }

    // read back the flows on origin -> facility edges (their reverse edge holds the flow)
    var flows = [], byOrigin = new Float64Array(nO), byFacility = new Float64Array(nF);
    for (var i = 0; i < nO; i++) {
      for (var e = head[2 + i]; e !== -1; e = next[e]) {
        var v = to[e];
        if ((e & 1) === 0 && v >= 2 + nO && cap[e ^ 1] > EPS) {
          var k = v - 2 - nO, amt = cap[e ^ 1];
          flows.push({o: i, f: k, amount: amt, dist: dist[e]});
          byOrigin[i] += amt; byFacility[k] += amt;
        }
      }
    }
    return {total: total, flows: flows, byOrigin: byOrigin, byFacility: byFacility};
  }

  /*
   * Why residents of an origin remain unassigned, checked in this order:
   *   capacity_full     a facility with entered places is within reach, but all reachable places are used
   *                     (in a maximum flow, any reachable place left over would have been used)
   *   capacity_unknown  no facility with places within reach, but an eligible candidate with unknown capacity is
   *   unavailable       within reach there are only candidates marked unavailable or excluded (2021 flood screening,
   *                     or outside EMS coverage when the exploratory option is off)
   *   no_candidate      no candidate facility at all within the distance
   * `cands`: every candidate {x, y, state} with state in 'places' | 'unknown' | 'unavailable' | 'excluded'.
   */
  var GAP = ['capacity_full', 'capacity_unknown', 'unavailable', 'no_candidate'];
  function gapReasons(origins, result, cands, maxDist) {
    var reachable = new Uint8Array(origins.length);
    result.reach.forEach(function (r, i) { reachable[i] = r; });
    var g = grid(cands, Math.max(maxDist, 1));
    return origins.map(function (o, i) {
      var left = o.demand - result.byOrigin[i];
      if (left <= 1e-6) return null;
      if (reachable[i]) return 'capacity_full';
      var st = {};
      g.near(o.x, o.y, maxDist).forEach(function (e) { st[cands[e[0]].state] = true; });
      return st.places ? 'capacity_full' : st.unknown ? 'capacity_unknown' : (st.unavailable || st.excluded) ? 'unavailable' : 'no_candidate';
    });
  }

  // reach[i] = 1 if origin i has at least one facility with places within maxDist
  function reach(origins, facilities, maxDist) {
    var withCap = facilities.filter(function (f) { return f.cap > EPS; });
    var g = grid(withCap, Math.max(maxDist, 1));
    return origins.map(function (o) { return g.near(o.x, o.y, maxDist).length > 0 ? 1 : 0; });
  }

  function run(origins, facilities, cands, maxDist) {
    var res = allocate(origins, facilities, maxDist);
    res.reach = reach(origins, facilities, maxDist);
    res.gaps = gapReasons(origins, res, cands, maxDist);
    res.gapTotals = {};
    GAP.forEach(function (k) { res.gapTotals[k] = 0; });
    res.gaps.forEach(function (k, i) { if (k) res.gapTotals[k] += origins[i].demand - res.byOrigin[i]; });
    return res;
  }

  var api = {allocate: allocate, gapReasons: gapReasons, reach: reach, run: run, GAP: GAP};
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.ShelterAlloc = api;
})(typeof window !== "undefined" ? window : this);
