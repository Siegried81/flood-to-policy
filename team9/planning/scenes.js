/*
 * scenes.js - The four presentation scenes of flood_map.html and the fixed 400 m hexagon layers they use.
 *
 *   1 What happened?        observed EMS extent and traces, totals inside the mapped extent
 *   2 Who was exposed?      estimated exposed residents per fixed hexagon (the allocation demand origins, summed);
 *                           overview: circles labelled with the SUM of residents, from zoom HEX_ZOOM: shaded hexagons
 *   3 Where could they go?  candidate shelters + planning scenario (planning/ui.js, unchanged state)
 *   4 Where to start?       scenario-based planning priority of the same hexagons (planning/priority.js)
 *
 * A scene only switches layers, panels and legend defaults. It never touches the scenario inputs, Scenario A or the
 * demo view, and nothing here depends on the map view: rankings, denominators and P99 are fixed study-wide values.
 * Needs window.SCENE_DATA, window.SCENE_APP, ScenarioUI, AreaPriority and (optionally) AssetContext.
 */
(function () {
  var D = window.SCENE_DATA, APP = window.SCENE_APP, map = APP.map, SU = window.ScenarioUI, AP = window.AreaPriority;
  var AC = window.AssetContext || null, HEX_ZOOM = D.hexZoom;
  var H = D.hex, n = H.id.length;
  var fmt = function (v) { return Math.round(v).toLocaleString('en'); };
  var approx = function (v) { return v < 0.5 ? (v > 0 ? '< 1' : '0') : '≈ ' + fmt(v >= 100 ? Math.round(v / 10) * 10 : v); };
  var pct = SU.pct;
  var CN = {BEL: 'Belgium', DEU: 'Germany', NLD: 'Netherlands'}, CC = {BEL: 'BE', DEU: 'DE', NLD: 'NL'};
  var $ = function (id) { return document.getElementById(id); };
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]; }); }
  function classColor(colors, breaks, v) {
    if (v == null || isNaN(v)) return null;
    var i = 0; while (i < breaks.length - 1 && v >= breaks[i + 1]) i++;
    return colors[i];
  }
  var place = function (i) { return H.cc[i] ? CN[H.cc[i]] : 'country not attributed'; };

  // ---------------------------------------------------------------- fixed study-wide references (never view-dependent)
  // P per hexagon is re-summed from the allocation's own origins (not the rounded copy in SCENE_DATA), so U <= P holds
  // exactly and G = 100 when nothing is assigned. The rounded build-time values must agree (checked once here).
  var originHex = D.originHex, Pex = new Float64Array(n);
  SU.get().origins.forEach(function (o, j) { Pex[originHex[j]] += o.demand; });
  for (var i = 0; i < n; i++) {
    if (Math.abs(Pex[i] - H.P[i]) > 1e-6) throw new Error('hexagon ' + H.id[i] + ': origins do not reproduce the build-time total');
    H.P[i] = Pex[i];
  }
  var total = 0; for (i = 0; i < n; i++) total += H.P[i];
  var byP = []; for (i = 0; i < n; i++) byP.push(i);
  byP.sort(function (a, b) { return (H.P[b] - H.P[a]) || (a - b); });
  var rankP = new Int32Array(n); byP.forEach(function (h, k) { rankP[h] = k + 1; });
  var hexes = H.P.map(function (P) { return {P: P}; });

  // ---------------------------------------------------------------- layers
  map.createPane('hexes').style.zIndex = 410;
  map.createPane('hexHi').style.zIndex = 615; map.getPane('hexHi').style.pointerEvents = 'none';
  var rend = L.canvas({pane: 'hexes', tolerance: 2});
  function polys(style, popup) {
    return H.ring.map(function (ring, i) {
      var p = L.polygon(ring, Object.assign({renderer: rend, weight: 0.6, color: '#ffffff', fillOpacity: 0.75}, style(i)));
      p.on('click', function (e) { L.DomEvent.stopPropagation(e); openPopup(i, popup); });
      return p;
    });
  }
  // A composite layer: overview children below HEX_ZOOM, hexagon polygons from HEX_ZOOM (zoom changes display only)
  function zoomLayer(overview, detail) {
    var g = L.layerGroup();
    g.sync = function () {
      if (!map.hasLayer(g)) return;
      var want = map.getZoom() >= HEX_ZOOM ? detail : overview, other = want === detail ? overview : detail;
      if (g.hasLayer(other)) g.removeLayer(other);
      if (!g.hasLayer(want)) g.addLayer(want);
    };
    g.on('add', function () { setTimeout(g.sync, 0); });
    g.on('remove', function () { g.clearLayers(); });
    return g;
  }

  // Scene 2: exposed residents
  var expoPolys = polys(function (i) { return {fillColor: classColor(D.expoColors, D.expoBreaks, H.P[i])}; }, 'expo');
  function sumIcon(sum, count) {
    var size = sum < 10 ? 30 : sum < 100 ? 36 : sum < 1000 ? 44 : sum < 5000 ? 52 : 60;
    var tip = approx(sum) + ' estimated exposed residents (sum of ' + count + ' hexagon' + (count > 1 ? 's' : '') + ')';
    return L.divIcon({className: 'ecl-ic', iconSize: [size, size],
      html: '<div class="ecl" title="' + tip + '" data-sum="' + sum + '">' + approx(sum).replace('≈ ', '') + '</div>'});
  }
  var expoCluster = L.markerClusterGroup({maxClusterRadius: 70, showCoverageOnHover: false, spiderfyOnMaxZoom: false,
    disableClusteringAtZoom: HEX_ZOOM,   // no chunkedLoading: a scene switch could remove the layer mid-load
    iconCreateFunction: function (c) {
      var ms = c.getAllChildMarkers(), s = 0;
      ms.forEach(function (m) { s += m.options.res; });
      return sumIcon(s, ms.length);
    }});
  H.lat.forEach(function (lat, i) {
    var mk = L.marker([lat, H.lon[i]], {icon: sumIcon(H.P[i], 1), res: H.P[i], hex: i});
    mk.on('click', function () { openPopup(i, 'expo'); });
    expoCluster.addLayer(mk);
  });
  var expoLayer = zoomLayer(expoCluster, L.featureGroup(expoPolys));

  // Scene 4: area priority (overview: one dot per hexagon, coloured by score, highest on top)
  var prioPolys = polys(function () { return {}; }, 'prio');
  var prioDots = H.lat.map(function (lat, i) {
    var c = L.circleMarker([lat, H.lon[i]], {renderer: rend, radius: 5, weight: 1, color: '#ffffff', fillOpacity: 0.95});
    c.on('click', function (e) { L.DomEvent.stopPropagation(e); openPopup(i, 'prio'); });
    return c;
  });
  var prioDotGroup = L.featureGroup(), prioLayer = zoomLayer(prioDotGroup, L.featureGroup(prioPolys));
  map.on('zoomend', function () { expoLayer.sync(); prioLayer.sync(); });
  APP.layerControl.addOverlay(expoLayer, 'Exposed residents (fixed 400 m hexagons)');
  APP.layerControl.addOverlay(prioLayer, 'Scenario-based planning priority (areas)');
  if (AC) {
    APP.layerControl.addOverlay(AC.layers.people, 'Vulnerable facilities (OSM, context)');
    APP.layerControl.addOverlay(AC.layers.infra, 'Critical infrastructure (OSM, context)');
  }

  var hi = L.layerGroup().addTo(map);
  function highlight(i) {
    hi.clearLayers();
    L.polygon(H.ring[i], {pane: 'hexHi', fill: false, color: '#111827', weight: 3.5, interactive: false}).addTo(hi);
    L.polygon(H.ring[i], {pane: 'hexHi', fill: false, color: '#facc15', weight: 1.5, interactive: false}).addTo(hi);
  }
  function goTo(i, kind) {
    highlight(i);
    map.once('moveend', function () { openPopup(i, kind); });
    map.flyTo([H.lat[i], H.lon[i]], 15, {duration: 0.8});
  }

  // ---------------------------------------------------------------- area priority (recomputed on every scenario change)
  var W = {E: D.weights.E, G: D.weights.G}, P = null, U = new Float64Array(n), reasonU = [];
  function recompute() {
    var g = SU.get(), r = g.result;
    U = new Float64Array(n); reasonU = [];
    for (var k = 0; k < n; k++) reasonU.push({});
    g.origins.forEach(function (o, j) {
      var left = Math.max(0, o.demand - r.byOrigin[j]), h = originHex[j];
      U[h] += left;
      if (r.gaps[j] && left > 0) reasonU[h][r.gaps[j]] = (reasonU[h][r.gaps[j]] || 0) + left;
    });
    P = AP.score(hexes, U, D.p99, W.E, W.G);
    P.rank = new Int32Array(n); P.order.forEach(function (h, k) { P.rank[h] = k + 1; });
    var col = function (h) { var s = P.rows[h] && P.rows[h].S; return s == null ? '#c9ced6' : classColor(D.prioColors, D.prioBreaks, s); };
    prioPolys.forEach(function (p, h) { p.setStyle({fillColor: col(h)}); });
    prioDotGroup.clearLayers();
    var drawOrder = P.order.length ? P.order.slice().reverse() : byP.slice().reverse();   // highest drawn last (on top)
    drawOrder.forEach(function (h) { prioDots[h].setStyle({fillColor: col(h)}); prioDotGroup.addLayer(prioDots[h]); });
    if (scene === 4) renderScene4();
    if (popupKind === 'prio' && map._popup && map._popup.isOpen()) openPopup(popupHex, 'prio');
  }

  // ---------------------------------------------------------------- popups
  var popupHex = null, popupKind = null;
  var GAP_TXT = {
    capacity_unknown: 'only candidates with <b>unknown capacity</b> within the distance: missing data, not a verified shortage',
    no_candidate: 'no candidate facility of our OSM inventory within the distance',
    unavailable: 'only candidates marked unavailable or excluded within the distance',
    capacity_full: 'all entered places within the distance are used under the stated assumptions'};
  function notes(i) {
    var out = [];
    if (H.cc[i] === 'BEL') out.push('Belgium: flooding incompletely observed (no flood traces, towns such as Verviers and Pepinster mostly not delineated): exposure here is likely underestimated.');
    if (!H.cc[i]) out.push('Country not attributed: no OBAT building in this hexagon.');
    if (H.nfb[i]) out.push(H.nfb[i] + ' of its ' + H.no[i] + ' origin(s) come from flood polygons without residential buildings (area-share estimate).');
    return out;
  }
  function openPopup(i, kind) {
    popupHex = i; popupKind = kind; highlight(i);
    var head = '<b>Hexagon ' + esc(H.id[i]) + '</b> <span class="muted">(fixed 400 m grid · ' + esc(place(i)) + ')</span>';
    var est = '<div class="muted" style="margin-top:4px">' + esc(D.reference) + '. An estimate, not a count. ' +
      '400 m is the aggregation grid, not the accuracy of the population estimate.</div>';
    var html;
    if (kind === 'expo') {
      html = head + '<div style="margin-top:4px"><b>' + approx(H.P[i]) + '</b> estimated exposed residents <span class="k k-hist">2020 est.</span></div>' +
        '<div>Rank ' + rankP[i] + ' of ' + fmt(n) + ' hexagons by exposed residents · ' + pct(H.P[i], total) + ' of ' + approx(total) + '</div>' +
        notes(i).map(function (t) { return '<div class="muted">' + t + '</div>'; }).join('') + est;
    } else {
      var r = P.rows[i], why = Object.keys(reasonU[i]).sort(function (a, b) { return reasonU[i][b] - reasonU[i][a]; });
      html = head + '<div class="muted" style="margin:2px 0 4px">Scenario-based planning priority: not a flood probability or a validated vulnerability index.</div>' +
        '<table class="scn-t">' +
        '<tr><td>Estimated exposed residents (P)</td><td>' + approx(H.P[i]) + '</td></tr>' +
        '<tr><td>Assigned in the current scenario</td><td>' + approx(H.P[i] - r.U) + '</td></tr>' +
        '<tr><td>Unassigned (U)</td><td>' + approx(r.U) + ' <span class="pc">(' + pct(r.U, H.P[i]) + ')</span></td></tr>' +
        '<tr><td>Exposure E = 100·min(1, ln(1+P)/ln(1+P99))</td><td>' + r.E.toFixed(1) + '</td></tr>' +
        '<tr><td>Scenario gap G = 100·U/P</td><td>' + r.G.toFixed(1) + '</td></tr>' +
        '<tr class="hl"><td>S = ' + Math.round(100 * P.w.E) + ' % E + ' + Math.round(100 * P.w.G) + ' % G</td><td>' + (r.S == null ? '—' : r.S.toFixed(1)) + '</td></tr>' +
        '</table>' + (P.rank[i] ? '<div>Rank ' + P.rank[i] + ' of ' + fmt(P.order.length) + ' hexagons with exposed residents</div>' : '<div>No score: both weights are 0.</div>') +
        (why.length ? '<div class="muted" style="margin-top:4px"><b>Why residents remain unassigned:</b> ' +
          why.map(function (k) { return approx(reasonU[i][k]) + ' — ' + GAP_TXT[k]; }).join('; ') + '.</div>' : '') +
        notes(i).map(function (t) { return '<div class="muted">' + t + '</div>'; }).join('') + est;
    }
    L.popup({className: 'shel-pop', maxWidth: 330, autoPanPaddingTopLeft: L.point(340, 20)})
      .setLatLng([H.lat[i], H.lon[i]]).setContent(html).openOn(map);
  }
  map.on('popupclose', function (e) { if (popupKind && e.popup.getContent && /Hexagon /.test(e.popup.getContent())) { popupKind = null; hi.clearLayers(); } });

  // ---------------------------------------------------------------- scene panels
  function contextBoxes(keys) {
    var lab = {bldg: 'Buildings: <b>all</b> GHS-OBAT buildings per 400 m hexagon (context, not flooded buildings)',
               people: 'Vulnerable facilities (OSM): hospitals, care homes, schools… Presence does not establish occupancy or individual vulnerability',
               infra: 'Critical infrastructure (OSM): bridges, power, water, emergency services'};
    return '<div class="scn-sub">Context layers (optional)</div>' + keys.filter(function (k) { return k === 'bldg' || AC; }).map(function (k) {
      return '<label class="scn-chk"><input type="checkbox" data-ctx="' + k + '"> <span>' + lab[k] + '</span></label>';
    }).join('');
  }
  var CTX = function (k) { return k === 'bldg' ? APP.layers.bldg : AC.layers[k]; };
  function bindContext(el) {
    el.querySelectorAll('[data-ctx]').forEach(function (cb) {
      cb.checked = map.hasLayer(CTX(cb.dataset.ctx));
      cb.onchange = function () { if (cb.checked) CTX(cb.dataset.ctx).addTo(map); else map.removeLayer(CTX(cb.dataset.ctx)); };
    });
  }
  map.on('layeradd layerremove', function () {
    document.querySelectorAll('[data-ctx]').forEach(function (cb) { cb.checked = map.hasLayer(CTX(cb.dataset.ctx)); });
  });

  function top10Share() {
    var s = 0; byP.slice(0, 10).forEach(function (h) { s += H.P[h]; }); return s;
  }
  function renderScene2() {
    var el = $('scene-2'), s10 = top10Share();
    el.innerHTML = '<h3>2 · Who was exposed? <span class="k k-hist">2020 estimate</span></h3>' +
      '<div class="big-n">' + approx(total) + '</div><div>estimated residents inside the mapped observed flood extent, in <b>' + fmt(n) +
      '</b> fixed 400 m hexagons. The same residents are the demand of the shelter scenario (scene 3).</div>' +
      '<div class="scn-sub">Top 10 exposed hexagons</div>' +
      '<table class="scn-t top10"><tr><th>#</th><th>hexagon</th><th>residents</th><th>share</th></tr>' +
      byP.slice(0, 10).map(function (h, k) {
        return '<tr data-hex="' + h + '"><td>' + (k + 1) + '</td><td>' + esc(H.id[h]) + ' <span class="pc">' + (CC[H.cc[h]] || '–') + '</span></td><td>' +
          approx(H.P[h]) + '</td><td>' + pct(H.P[h], total) + '</td></tr>';
      }).join('') + '</table>' +
      '<div class="scn-diff">Top 10 hold <b>' + pct(s10, total) + '</b> of the estimated exposed residents (' + approx(s10) + ' of ' + approx(total) +
      ' in all ' + fmt(n) + ' hexagons).</div>' +
      '<div class="note" style="max-width:none">Ranked by fixed hexagon, never by the circles on screen. Overview circles show the <b>sum of estimated residents</b> ' +
      'of the hexagons they group (they regroup with zoom; the sum stays the same); from zoom ' + HEX_ZOOM + ' each hexagon is shaded. ' +
      '400 m is the aggregation grid, not the accuracy of the estimate. Country = majority of the hexagon’s OBAT buildings; municipality not available. ' +
      'Reference: ' + esc(D.reference) + '.</div>' +
      contextBoxes(['bldg', 'people']) +
      '<div class="note" style="max-width:none">Counts are never added across layers: a school can be both a vulnerable facility and a candidate shelter.</div>';
    el.querySelectorAll('tr[data-hex]').forEach(function (tr) { tr.onclick = function () { goTo(+tr.dataset.hex, 'expo'); }; });
    bindContext(el);
  }

  var assetBox = null;
  function renderScene4() {
    var el = $('scene-4'), g = SU.get(), r = g.result, st = g.state, assigned = r.total, un = total - assigned;
    var open = {}; el.querySelectorAll('details[data-k]').forEach(function (d) { open[d.dataset.k] = d.open; });
    var det = function (k, title, body) { return '<details data-k="' + k + '"' + (open[k] ? ' open' : '') + '><summary>' + title + '</summary>' + body + '</details>'; };
    var status;
    if (P.w.zero) status = '<div class="scn-flag">Both weights are 0: no priority score can be calculated. Set at least one weight above 0.</div>';
    else if (!(r.placesEntered > 0)) status = '<div class="scn-flag">No usable capacity entered: G = 100 everywhere, so this is the <b>exposure ranking</b> ' +
      '(no capacity-based differentiation). Our inventory contains no documented shelter-capacity baseline.</div>';
    else if (P.gConstant) status = '<div class="scn-flag">G is the same (' + P.gValue.toFixed(0) + ') in every area: the scenario gap does not change the ranking.</div>';
    else status = '';
    var top = P.order.slice(0, 10), p10 = 0, u10 = 0;
    top.forEach(function (h) { p10 += H.P[h]; u10 += P.rows[h].U; });
    var gt = r.gapTotals, wE = Math.round(100 * P.w.E), wG = Math.round(100 * P.w.G);
    var miss = ['<li><b>Unknown capacity</b>: ' + approx(gt.capacity_unknown) + ' unassigned residents have only candidates with unknown capacity in range. Missing data, not zero capacity and not a verified shortage.</li>',
      '<li><b>No candidate in range</b>: ' + approx(gt.no_candidate) + ' (within ' + st.km + ' km straight line, in our OSM inventory).</li>',
      '<li><b>Observation gaps</b>: EMS missed water between buildings and observed Belgium incompletely, so exposure is underestimated there; countries are not fairly comparable.</li>',
      '<li><b>Not modelled</b>: age, health, mobility, occupancy, real routes and travel times.</li>'].join('');
    el.innerHTML = '<h3>4 · Where to start? <span class="k k-res">Calculated</span></h3>' +
      '<div class="scn-head">Scenario-based planning priority <span>illustrative weights</span></div>' +
      '<div class="scn-warn">Not a flood probability, a validated vulnerability index or a definitive ranking of actual need.</div>' +
      '<div class="scn-scope"><span class="k k-asm">Scenario</span> ' + st.km + ' km · exploratory ' + (st.exploratory ? 'on' : 'off') + ' · ' +
      fmt(r.counts.places) + ' facilities with ' + fmt(r.placesEntered) + ' places <button class="linkbtn" data-goscene="3">edit in scene 3</button></div>' +
      status +
      '<div class="scn-sub">Top 10 areas (fixed hexagons, whole mapped study coverage)</div>' +
      (top.length ? '<table class="scn-t top10 prio"><tr><th>#</th><th>hexagon</th><th>P</th><th>U</th><th>E</th><th>G</th><th>S</th></tr>' +
        top.map(function (h, k) {
          var x = P.rows[h];
          return '<tr data-hex="' + h + '"><td>' + (k + 1) + '</td><td>' + esc(H.id[h]) + ' <span class="pc">' + (CC[H.cc[h]] || '–') + '</span></td><td>' + approx(H.P[h]).replace('≈ ', '') +
            '</td><td>' + approx(x.U).replace('≈ ', '') + '</td><td>' + x.E.toFixed(0) + '</td><td>' + x.G.toFixed(0) + '</td><td><b>' + x.S.toFixed(1) + '</b></td></tr>';
        }).join('') + '</table>' +
        '<div class="scn-cnt">P exposed, U unassigned residents; E is capped at 100 from P99 (≈ ' + fmt(D.p99) + ' residents); ties ordered by P. Top 10: ' + approx(p10) + ' of ' + approx(total) + ' exposed (' + pct(p10, total) + ') and ' + approx(u10) + ' of ' +
        approx(un) + ' unassigned (' + pct(u10, un || 1) + '); ' + fmt(P.order.length) + ' hexagons scored.</div>' : '') +
      '<table class="scn-t"><tr><td>Estimated exposed residents <span class="k k-hist">2020 est.</span></td><td>' + approx(total) + '</td></tr>' +
      '<tr><td>Assigned in this scenario</td><td>' + approx(assigned) + ' <span class="pc">(' + pct(assigned, total) + ')</span></td></tr>' +
      '<tr><td>Unassigned</td><td>' + approx(un) + ' <span class="pc">(' + pct(un, total) + ')</span></td></tr></table>' +
      (g.A ? '<div class="scn-cnt">Scenario A: ' + approx(g.A.sum.assigned) + ' assigned → now ' + approx(assigned) + ' (A/B details in scene 3).</div>' : '') +
      '<div class="scn-sub"><span class="k k-asm">Weights</span> S = ' + wE + ' % E + ' + wG + ' % G</div>' +
      '<label class="scn-in">Exposure E <b>' + (P.w.zero ? '—' : wE + ' %') + '</b><input type="range" id="w-E" min="0" max="100" step="5" value="' + W.E + '"></label>' +
      '<label class="scn-in">Scenario gap G <b>' + (P.w.zero ? '—' : wG + ' %') + '</b><input type="range" id="w-G" min="0" max="100" step="5" value="' + W.G + '"></label>' +
      '<div class="btns scn-btns"><button id="w-reset">Reset to 50 / 50</button></div>' +
      '<div class="note" style="max-width:none">50 / 50 is an illustrative starting assumption, not a validated choice.</div>' +
      det('miss', 'Missing information (not part of the score)', '<ul class="scn-ch">' + miss + '</ul>') +
      det('how', 'How the score works', '<div class="note" style="max-width:none">For each fixed hexagon with exposed residents P &gt; 0 ' +
        '(hexagons without exposed residents are excluded): E = 100 × min(1, ln(1+P) / ln(1+P99)), with P99 = ' + D.p99.toFixed(1) +
        ' residents, the 99th percentile over all ' + fmt(n) + ' hexagons (fixed: zoom never changes it). G = 100 × U / P, U = residents left unassigned by the ' +
        'current scenario. S = wE·E + wG·G with weights normalised to sum to 1. Ties: more exposed residents first. Uncertainty is not a score component. ' +
        '<b>Caution:</b> the allocation maximises the total assigned; which areas receive the places is one of several equally valid answers, so U and G of a single area are not unique.</div>') +
      (AC ? det('ctx', 'Context: infrastructure and facilities (separate asset scores)',
        contextBoxes(['infra', 'people']) + '<div class="note" style="max-width:none">Asset screening scores rank individual assets within their own group. ' +
        'They are not area priorities and are never ranked together with the hexagons above.</div><div id="asset-host"></div>') : '');
    el.querySelectorAll('tr[data-hex]').forEach(function (tr) { tr.onclick = function () { goTo(+tr.dataset.hex, 'prio'); }; });
    ['E', 'G'].forEach(function (k) {
      var s = $('w-' + k);
      s.onchange = function () { W[k] = +s.value; recompute(); };
    });
    $('w-reset').onclick = function () { W = {E: D.weights.E, G: D.weights.G}; recompute(); };
    el.querySelectorAll('[data-goscene]').forEach(function (b) { b.onclick = function () { setScene(+b.dataset.goscene); }; });
    bindContext(el);
    if (AC) {   // keep one asset list instance across re-renders (its tab and weights stay)
      if (!assetBox) { assetBox = document.createElement('div'); AC.mount(assetBox); }
      $('asset-host').appendChild(assetBox);
    }
    APP.layout();
  }

  // ---------------------------------------------------------------- scene switching
  var L_ = APP.layers;
  var SCENES = {
    1: [L_.flooded, L_.trace, L_.aoi, L_.water],
    2: [L_.flooded, L_.trace, L_.aoi, L_.water, expoLayer],
    3: [L_.flooded, L_.trace, L_.aoi, L_.water, L_.shel, SU.layers.gaps],
    4: [L_.flooded, L_.trace, L_.aoi, L_.water, prioLayer]};
  var MANAGED = [L_.flooded, L_.trace, L_.aoi, L_.water, L_.bldg, L_.pop, L_.shel, SU.layers.gaps, SU.layers.lines, expoLayer, prioLayer]
    .concat(AC ? [AC.layers.people, AC.layers.infra] : []).filter(Boolean);
  var scene = 0;
  function setScene(k) {
    scene = k;
    var on = SCENES[k].filter(Boolean);
    MANAGED.forEach(function (l) { if (on.indexOf(l) < 0 && map.hasLayer(l)) map.removeLayer(l); });
    on.forEach(function (l) { if (!map.hasLayer(l)) l.addTo(map); });
    APP.efasOff();
    APP.setFloodLight(k === 2 || k === 4);
    hi.clearLayers(); map.closePopup();
    document.querySelectorAll('.scene-panel').forEach(function (p) { p.hidden = +p.dataset.scene !== k; });
    document.querySelectorAll('button[data-scene]').forEach(function (b) { b.classList.toggle('on', +b.dataset.scene === k); });
    if (k === 2) renderScene2();
    if (k === 4) renderScene4();
    APP.layout();
  }
  document.querySelectorAll('button[data-scene]').forEach(function (b) { b.onclick = function () { setScene(+b.dataset.scene); }; });

  // legend blocks follow the layers
  APP.legendGroups['leg-expo'] = [expoLayer];
  APP.legendGroups['leg-prio'] = [prioLayer];
  if (AC) { APP.legendGroups['leg-people'] = [AC.layers.people]; APP.legendGroups['leg-infra'] = [AC.layers.infra]; }

  APP.onRecalc.push(recompute);
  recompute();
  setScene(1);
  window.Scenes = {set: setScene, current: function () { return scene; }, hex: H, total: total, byP: byP, originHex: originHex,   // also used by tests
                   priority: function () { return P; }, U: function () { return U; }, weights: function (e, g) { W = {E: e, G: g}; recompute(); },
                   layers: {expo: expoLayer, prio: prioLayer, cluster: expoCluster}};
})();
