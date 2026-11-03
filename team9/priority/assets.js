/*
 * assets.js - Optional context layers of flood_map.html: vulnerable facilities and critical infrastructure (OSM),
 * with their ASSET screening scores (ported from the retired priority_map.html; same formula as priority/scoring.py):
 *   S = 100 × M × Σ w·X / Σ w over the AVAILABLE indicators X = P (residents), B (buildings), F (July 2021 flooding).
 * These scores rank individual assets within one group. They are not the area planning priority (planning/priority.js)
 * and the two are never combined, ranked together or compared numerically.
 * Needs window.ASSET_DATA (cache/priority/assets.json + colours) and window.ASSET_APP = {map}.
 */
(function () {
  var D = window.ASSET_DATA, map = window.ASSET_APP.map;
  var KEYS = ['P', 'B', 'F'];
  var CN = {BEL: 'Belgium', DEU: 'Germany', NLD: 'Netherlands'};
  var esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]; }); };
  var fmt = function (x) { return x == null ? '—' : Math.round(x).toLocaleString('en'); };
  var pct = function (x) { return Math.round(100 * x) + ' %'; };

  // ------------------------------------------------------------------ scoring (mirror of scoring.score)
  var raw;
  function resetWeights() { raw = {P: 100 * D.weights.P, B: 100 * D.weights.B, F: 100 * D.weights.F}; }
  resetWeights();
  function weights() {
    var s = raw.P + raw.B + raw.F;
    return s > 0 ? {P: raw.P / s, B: raw.B / s, F: raw.F / s} : {P: 1 / 3, B: 1 / 3, F: 1 / 3};
  }
  function score(o, w) {
    var M = o.M == null ? 1 : o.M, num = 0, den = 0, lo = 0, hi = 0, c = {}, missing = [];
    KEYS.forEach(function (k) {
      var x = o[k];
      if (x == null) { hi += w[k]; missing.push(k); }
      else { num += w[k] * x; den += w[k]; lo += w[k] * x; hi += w[k] * x; }
    });
    KEYS.forEach(function (k) { c[k] = (o[k] == null || den === 0) ? null : 100 * M * w[k] * o[k] / den; });
    return {s: den > 0 ? 100 * M * num / den : null, lo: 100 * M * lo, hi: 100 * M * hi, c: c, missing: missing};
  }
  var BREAKS = [0, 20, 35, 50, 65, 80];
  function ramp(colors, s) {
    if (s == null || isNaN(s)) return null;
    var i = 0; while (i < BREAKS.length - 1 && s >= BREAKS[i + 1]) i++;
    return colors[i];
  }

  // ------------------------------------------------------------------ layers
  map.createPane('assetLines').style.zIndex = 590;
  map.createPane('assets').style.zIndex = 610;
  var assetRenderer = L.canvas({pane: 'assets', tolerance: 4}), lineRenderer = L.canvas({pane: 'assetLines', tolerance: 4});
  var GROUP = {people: {data: D.people, colors: D.colors.people, stroke: '#ffffff', name: 'Vulnerable facility'},
               infra: {data: D.infra, colors: D.colors.infra, stroke: '#1f2933', name: 'Critical infrastructure'}};
  var layers = {people: L.layerGroup(), infra: L.layerGroup()}, infraLines = L.layerGroup();
  Object.keys(GROUP).forEach(function (g) {
    GROUP[g].data.forEach(function (o) {
      o.group = g;
      o.marker = L.circleMarker([o.lat, o.lon], {renderer: assetRenderer, weight: g === 'infra' ? 1.2 : 1, color: GROUP[g].stroke,
                                                 fillOpacity: 0.95, bubblingMouseEvents: false});
      o.marker.on('click', function () { openAsset(o); });
      if (o.line) {
        o.poly = L.polyline(o.line, {renderer: lineRenderer, weight: 5, opacity: 0.9, bubblingMouseEvents: false});
        o.poly.on('click', function () { openAsset(o); });
      }
    });
  });
  function lines() {   // bridge / tunnel lines only at street scale
    var on = map.getZoom() >= 13 && map.hasLayer(layers.infra);
    if (on && !map.hasLayer(infraLines)) infraLines.addTo(map); else if (!on && map.hasLayer(infraLines)) map.removeLayer(infraLines);
  }
  map.on('zoomend overlayadd overlayremove layeradd layerremove', lines);

  // Historical flooding unknown (outside EMS coverage): drawn hollow, never ranked
  var unknownF = function (o) { return o.fs === 'unmapped'; };
  function refresh() {
    var w = weights();
    Object.keys(GROUP).forEach(function (g) {
      var arr = GROUP[g].data, layer = layers[g];
      arr.forEach(function (o) { o.cur = score(o, w); });
      arr.sort(function (a, b) { return (unknownF(a) - unknownF(b)) || ((b.cur.s || 0) - (a.cur.s || 0)); });
      var n = 0; arr.forEach(function (o) { o.rank = unknownF(o) ? null : ++n; });
      GROUP[g].nRanked = n;
      layer.clearLayers(); if (g === 'infra') infraLines.clearLayers();
      for (var i = arr.length - 1; i >= 0; i--) {   // lowest first, so the highest scores are drawn on top
        var o = arr[i]; if (o.cur.s == null) continue;
        var col = ramp(GROUP[g].colors, o.cur.s);
        o.marker.setStyle(unknownF(o) ? {fillColor: '#ffffff', color: col, weight: 2, radius: 3 + 5 * o.cur.s / 100}
                                      : {fillColor: col, color: GROUP[g].stroke, weight: g === 'infra' ? 1.2 : 1, radius: 3 + 5 * o.cur.s / 100});
        layer.addLayer(o.marker);
        if (o.poly) { o.poly.setStyle({color: col}); infraLines.addLayer(o.poly); }
      }
    });
    renderLists();
  }

  // ------------------------------------------------------------------ popups
  var FLAG = {
    F_unmapped: 'Outside EMS mapping coverage: July 2021 flooding is unknown here (not "safe"). F is excluded and the range shows F = 0 to F = 1.',
    B_gap: 'Residents but no OBAT building in the neighbourhood: building data treated as missing (likely gap), not as zero.',
    BE_detection: 'Belgium: EMS products have no flood traces and missed water between buildings (e.g. Pepinster, Verviers): "no flooding detected" is weak evidence.',
    type_assumed: 'Sub-type unknown in OSM: the type factor uses an assumed mid value.',
    post_2021: 'OSM start_date suggests this asset may not have existed (in this form) in July 2021.'
  };
  var NAMES = {P: 'Population', B: 'Buildings', F: 'Flooding July 2021'}, QDOT = {High: 'q-high', Medium: 'q-med', Low: 'q-low'};
  function openAsset(o) {
    var w = weights(), r = o.cur || score(o, w), isP = o.group === 'people';
    var rawText = {P: '≈ ' + fmt(o.pop) + ' residents within ~1 km²', B: fmt(o.bldg) + ' OBAT buildings within ~1 km²',
                   F: esc(D.factStatus[o.fs]) + (o.share != null && (o.fs === 'near' || o.fs === 'dry') ? ' (' + pct(o.share) + ' of mapped neighbourhood flooded)' : '')};
    var factor = isP
      ? 'Type factor M = <b>×' + o.M.toFixed(2) + '</b> (expert assumption) from dependency on help to evacuate = ' + (o.D == null ? 'unknown (0.5 assumed)' : o.D) +
        ', overnight occupancy = ' + (o.O == null ? 'unknown (0.5 assumed)' : (o.O ? 'yes' : 'no')) + '.'
      : 'Type factor M = <b>×' + o.M.toFixed(2) + '</b> (expert assumption): function importance ' + o.I.toFixed(2) +
        (o.carried ? ', carries ' + esc(o.carried) + (o.water ? ', crosses mapped water' : ', does not cross mapped water (×0.8)') : '') +
        (o.n_ways > 1 ? '; ' + o.n_ways + ' OSM ways merged into one structure' : '') + '. Network role and dependencies not assessed.';
    var bd = '<table class="bd"><tr><th></th><th>indicator</th><th>weight</th><th>points</th></tr>' + KEYS.map(function (k) {
      return '<tr><td>' + NAMES[k] + '<div class="muted">' + rawText[k] + '</div></td><td>' + (o[k] == null ? '<i>Data unavailable</i>' : o[k].toFixed(2)) +
        '</td><td>' + pct(w[k]) + '</td><td>' + (r.c[k] == null ? '—' : '+' + r.c[k].toFixed(1)) + '</td></tr>';
    }).join('') + '</table>';
    var cap = isP ? '<tr><th>Capacity / occupancy</th><td>' + (o.cap ? esc(o.cap) + ' (OSM tag, unverified, not used in the score)' : 'Unknown (not in OSM)') + '</td></tr>' +
      (o.who ? '<tr><th>Serves</th><td>' + esc(o.who) + '</td></tr>' : '') : (o.volt ? '<tr><th>Voltage</th><td>' + esc(o.volt) + '</td></tr>' : '') +
      '<tr><th>Condition / dependencies</th><td>Data unavailable</td></tr>';
    var flags = o.flags.length ? '<ul class="flags">' + o.flags.map(function (f) { return '<li>' + FLAG[f] + '</li>'; }).join('') + '</ul>' : '';
    var html = '<div class="pop"><h4>' + esc(o.name || 'Unnamed ' + o.label.toLowerCase()) + '</h4>' +
      '<div class="muted">' + esc(o.label) + ' · ' + esc(o.place ? o.place + ', ' : '') + esc(CN[o.country] || '—') + '</div>' +
      '<div class="big">' + (r.s == null ? '—' : Math.round(r.s)) + '<span>/100</span></div>' +
      '<div class="muted"><b>Asset screening score</b> (' + GROUP[o.group].name.toLowerCase() + '; not the area planning priority, not comparable with it)' +
      (o.rank ? ' · rank ' + o.rank + ' of ' + GROUP[o.group].nRanked + ' in this group' : ' · <b>not ranked: insufficient historical evidence</b>') + '</div>' +
      (r.missing.length ? '<div class="muted">Range if the missing data were 0 or maximal: <b>' + Math.round(r.lo) + '–' + Math.round(r.hi) + '</b></div>' : '') +
      bd + '<div class="note">' + factor + '</div>' +
      (isP ? '<div class="note">Presence of a facility does not establish its occupancy today or the vulnerability of individual people.</div>' : '') +
      '<div class="ql">Evidence quality: <span class="qd ' + QDOT[o.q] + '"></span> <b>' + o.q + '</b> (separate from the score)</div>' + flags +
      (o.rk ? '<div class="note">Weight sensitivity (36 weight sets): rank ' + o.rk[0] + ' to ' + o.rk[1] + ', in the top ' + D.topN + ' in ' + pct(o.top) + ' of them.</div>' : '') +
      '<table class="meta">' + cap + '<tr><th>Operator</th><td>' + (o.op ? esc(o.op) : 'Unknown') + '</td></tr>' +
      '<tr><th>Asset data</th><td>OpenStreetMap, present-day (not July 2021)' + (o.start ? '; start_date ' + esc(o.start) : '') +
      ' · <a href="https://www.openstreetmap.org/' + esc(o.id) + '" target="_blank" rel="noopener">' + esc(o.id) + '</a></td></tr></table></div>';
    L.popup({maxWidth: 360, className: 'prio-pop', autoPanPaddingTopLeft: [360, 10]}).setLatLng([o.lat, o.lon]).setContent(html).openOn(map);
  }

  // ------------------------------------------------------------------ separate asset lists (one per group, never mixed with areas)
  var hosts = [];   // [{el, group}]
  function listHtml(g) {
    var rows = GROUP[g].data.filter(function (o) { return o.rank; }).slice(0, 15);
    return '<ol class="asset-rank">' + rows.map(function (o) {
      return '<li data-g="' + g + '" data-id="' + esc(o.id) + '"><span class="rk">' + o.rank + '</span><span class="nm"><b>' +
        esc(o.name || 'Unnamed ' + o.label.toLowerCase()) + '</b><br><span class="muted">' + esc(o.label) + ' · ' + esc(o.place || CN[o.country] || '') +
        '</span></span><span class="sc" style="background:' + ramp(GROUP[g].colors, o.cur.s) + '">' + Math.round(o.cur.s) + '</span>' +
        '<span class="qd ' + QDOT[o.q] + '" title="Evidence quality: ' + o.q + '"></span></li>';
    }).join('') + '</ol><div class="note" style="max-width:none">Top 15 of ' + GROUP[g].nRanked.toLocaleString('en') + ' ranked ' +
      (g === 'people' ? 'vulnerable facilities' : 'infrastructure assets') + ' (all countries, assets outside EMS coverage not ranked). ' +
      'Asset scores (0–100) compare assets within this list only.</div>';
  }
  function renderLists() {
    var w = weights();
    hosts.forEach(function (h) {
      h.el.querySelector('.asset-list').innerHTML = listHtml(h.group());
      KEYS.forEach(function (k) {
        h.el.querySelector('[data-w=' + k + ']').value = raw[k];
        h.el.querySelector('[data-weff=' + k + ']').textContent = pct(w[k]);
      });
      h.el.querySelectorAll('.asset-rank li').forEach(function (li) {
        li.onclick = function () {
          var o = GROUP[li.dataset.g].data.find(function (x) { return x.id === li.dataset.id; });
          if (!map.hasLayer(layers[o.group])) layers[o.group].addTo(map);
          map.flyTo([o.lat, o.lon], 15, {duration: 0.8}); openAsset(o);
        };
      });
    });
  }
  // Mount the asset weights + list into a container (HTML built here so both scenes share one implementation)
  function mount(el) {
    var group = 'infra';
    el.innerHTML = '<div class="asset-tabs"><button data-ag="infra" class="on">Critical infrastructure</button><button data-ag="people">Vulnerable facilities</button></div>' +
      '<div class="asset-list"></div>' +
      '<details><summary>Asset score weights (illustrative 40/30/30)</summary>' +
      KEYS.map(function (k) { return '<label class="scn-in">' + NAMES[k] + ' <b data-weff="' + k + '"></b><input type="range" min="0" max="100" step="5" data-w="' + k + '"></label>'; }).join('') +
      '<div class="btns"><button data-areset>Reset asset weights</button></div>' +
      '<div class="note" style="max-width:none">Asset score = 100 × type factor × weighted mean of P (residents), B (buildings) and F (observed July 2021 flooding) ' +
      'within ~1 km² of the asset, against fixed study-wide references. Weights change these asset scores only, never the area planning priority.</div></details>';
    var h = {el: el, group: function () { return group; }};
    el.querySelectorAll('[data-ag]').forEach(function (b) {
      b.onclick = function () {
        group = b.dataset.ag;
        el.querySelectorAll('[data-ag]').forEach(function (x) { x.classList.toggle('on', x === b); });
        renderLists();
      };
    });
    el.querySelectorAll('[data-w]').forEach(function (s) { s.oninput = function () { raw[s.dataset.w] = +s.value; schedule(); }; });
    el.querySelector('[data-areset]').onclick = function () { resetWeights(); refresh(); };
    hosts.push(h);
    renderLists();
  }
  var pending = null;
  function schedule() { if (!pending) pending = setTimeout(function () { pending = null; refresh(); }, 120); }

  refresh();
  window.AssetContext = {layers: layers, mount: mount, score: score, weights: weights, GROUP: GROUP, colors: D.colors, BREAKS: BREAKS,
                         setWeights: function (p, b, f) { raw = {P: p, B: b, F: f}; refresh(); }};   // also used by tests
})();
