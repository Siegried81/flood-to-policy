/*
 * ui.js - "Planning scenario" tab of the candidate-shelter panel (needs alloc.js and the shelter layer of map.py).
 *
 * Scenario inputs are ASSUMPTIONS entered by the user (assumed places, available yes/no, distance, exploratory
 * option). They are kept apart from the inventory facts (documented capacity, screening), are never saved
 * automatically, and can be saved as versioned JSON (complete) or CSV (compatible with earlier exports) and restored:
 * a restore replaces the scenario. Scenario A is an independent snapshot for the A/B comparison.
 */
(function () {
  var A = window.ShelterAlloc, APP = window.SHELTER_APP, D = window.SCENARIO_DATA;
  var map = APP.map, markers = APP.markers;
  var DEFAULT_KM = D.defaultKm;
  var S;                                        // scenario state
  function reset() { S = {km: DEFAULT_KM, exploratory: false, assumed: {}, unavailable: {}}; }
  reset();
  var origins = D.origins.map(function (a) { return {id: a[0], x: a[1], y: a[2], lat: a[4], lon: a[3], demand: a[5], cc: a[6]}; });
  var byId = {}; markers.forEach(function (m) { byId[m.r.id] = m; });
  var demandTotal = origins.reduce(function (t, o) { return t + o.demand; }, 0);   // same values as allocated
  var last = null;                              // last result
  var fmt = function (v) { v = Math.round(v); return v.toLocaleString('en'); };
  var approx = function (v) { return v < 0.5 ? '0' : '≈ ' + fmt(v >= 100 ? Math.round(v / 10) * 10 : v); };
  function pct(v, tot) {   // small positive shares keep a visible precision (78 of 29,130 -> 0.27 %, never 0 %)
    var p = 100 * v / tot;
    return p <= 0 ? '0 %' : p < 0.1 ? '< 0.1 %' : p < 1 ? p.toFixed(2) + ' %' : p < 10 ? p.toFixed(1) + ' %' : Math.round(p) + ' %';
  }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]; }); }

  // ---------------------------------------------------------------- facility status (facts vs scenario inputs)
  function screening(r) {
    if (r.c === 'inside_observed' || r.c === 'boundary_unresolved') return 'excluded';
    if (r.c === 'outside_ems_coverage' && !S.exploratory) return 'excluded';
    return 'eligible';
  }
  function capacity(r) {   // scenario input first, then documented capacity, else unknown
    if (S.assumed[r.id] != null) return {v: S.assumed[r.id], kind: 'assumed'};
    if (r.dcap != null && r.dcap !== '') return {v: +r.dcap, kind: 'documented'};
    return {v: null, kind: 'unknown'};
  }
  function state(r) {
    if (screening(r) === 'excluded') return 'excluded';
    if (S.unavailable[r.id]) return 'unavailable';
    var c = capacity(r);
    return c.v == null ? 'unknown' : c.v > 0 ? 'places' : 'unavailable';   // 0 places entered = contributes nothing
  }

  // ---------------------------------------------------------------- map layers: gaps and straight-line assignments
  map.createPane('scenario'); map.getPane('scenario').style.zIndex = 420;
  var rend = L.canvas({pane: 'scenario'});
  var gapLayer = L.layerGroup(), lineLayer = L.layerGroup();
  APP.layerControl.addOverlay(gapLayer, 'Scenario: unassigned residents');
  APP.layerControl.addOverlay(lineLayer, 'Scenario: straight-line assignments');
  var GAP_STYLE = {
    capacity_full: {dashArray: null, weight: 2}, capacity_unknown: {dashArray: '5 4', weight: 2},
    unavailable: {dashArray: '1 4', weight: 2.5}, no_candidate: {dashArray: null, weight: 4}};
  var GAP_LABEL = {
    capacity_full: 'reachable entered places are all used',
    capacity_unknown: 'only candidates with unknown capacity in range',
    unavailable: 'only unavailable / excluded candidates in range',
    no_candidate: 'no candidate facility within the distance'};
  function swatch(k) {
    var s = GAP_STYLE[k];
    return '<svg width="18" height="18" viewBox="0 0 18 18"><circle cx="9" cy="9" r="6.5" fill="#facc15" fill-opacity=".4" stroke="#111827" stroke-width="' +
      Math.min(s.weight, 3) + '"' + (s.dashArray ? ' stroke-dasharray="' + s.dashArray.replace(' ', ',') + '"' : '') + '/></svg>';
  }

  // ---------------------------------------------------------------- recalculation
  function recalc() {
    var cands = [], facs = [], facRec = [];
    markers.forEach(function (m) {
      var st = state(m.r);
      cands.push({x: m.r.x, y: m.r.y, state: st});
      if (st === 'places') { facs.push({x: m.r.x, y: m.r.y, cap: capacity(m.r).v}); facRec.push(m.r); }
    });
    var res = A.run(origins, facs, cands, S.km * 1000);
    res.facRec = facRec;
    res.assignedById = {}; facRec.forEach(function (r, k) { res.assignedById[r.id] = res.byFacility[k]; });
    res.cross = res.flows.reduce(function (s, f) {
      var oc = origins[f.o].cc, fc = facRec[f.f].cc; return s + (oc && fc && oc !== fc ? f.amount : 0); }, 0);
    res.counts = {places: 0, unknown: 0, unavailable: 0, excluded_screen: 0, excluded_ems: 0};
    markers.forEach(function (m) {
      var st = state(m.r);
      if (st === 'excluded') res.counts[m.r.c === 'outside_ems_coverage' ? 'excluded_ems' : 'excluded_screen']++;
      else res.counts[st]++;
    });
    res.placesEntered = facs.reduce(function (s, f) { return s + f.cap; }, 0);
    last = res;
    draw(); renderPanel(); refreshIcons();
    (APP.onRecalc || []).forEach(function (f) { f(res); });   // scenes: area priority follows every change
  }

  function draw() {
    gapLayer.clearLayers(); lineLayer.clearLayers();
    origins.forEach(function (o, i) {
      var left = o.demand - last.byOrigin[i], k = last.gaps[i];
      if (!k || left < 0.5) return;
      L.circleMarker([o.lat, o.lon], Object.assign({renderer: rend, radius: Math.min(3 + Math.sqrt(left) * 0.5, 15),
        color: '#111827', fillColor: '#facc15', fillOpacity: 0.4, opacity: 0.8}, GAP_STYLE[k]))
        .bindTooltip(approx(left) + ' estimated residents unassigned (of ' + approx(o.demand) + ')<br>' + GAP_LABEL[k], {className: 'tt'})
        .addTo(gapLayer);
    });
    last.flows.forEach(function (f) {
      if (f.amount < 0.5) return;
      var o = origins[f.o], r = last.facRec[f.f];
      L.polyline([[o.lat, o.lon], [r.lat, r.lon]], {renderer: rend, color: '#374151', weight: 1 + Math.min(Math.sqrt(f.amount) / 4, 3),
        opacity: 0.7, dashArray: '2 4'})
        .bindTooltip(approx(f.amount) + ' estimated residents → ' + esc(r.name || 'unnamed facility') + '<br>' +
          (f.dist / 1000).toFixed(1) + ' km straight line (not a route or travel time)', {className: 'tt', sticky: true})
        .addTo(lineLayer);
    });
  }

  function refreshIcons() {
    markers.forEach(function (m) {
      var key = (capacity(m.r).kind === 'unknown' ? '' : capacity(m.r).v) + '|' + state(m.r);
      if (m._scnKey === key) return;
      m._scnKey = key; m.setIcon(APP.icon(m.r));
    });
    // no refreshClusters(): cluster icons do not depend on capacity, and re-adding markers would close an open popup
  }

  // ---------------------------------------------------------------- scenario snapshots (A/B comparison, save / restore)
  function cloneState(s) {   // independent copy: later edits of the current scenario cannot change it
    return {km: s.km, exploratory: s.exploratory, assumed: Object.assign({}, s.assumed), unavailable: Object.assign({}, s.unavailable)};
  }
  function summary(r) {
    return {demand: demandTotal, nFac: r.counts.places, places: r.placesEntered, assigned: r.total, unassigned: demandTotal - r.total};
  }
  var scenA = null;                             // {state, sum, build, at}
  function capture() {
    scenA = {state: cloneState(S), sum: summary(last), build: D.build, at: new Date().toTimeString().slice(0, 5)};
    renderPanel(); msg('Scenario A captured. Change assumptions to build the current Scenario B.');
  }
  function restoreA() {
    if (!scenA) return;
    S = cloneState(scenA.state); recalc();
    var d = Math.abs(last.total - scenA.sum.assigned);
    msg(d < 1e-6 ? 'Scenario A restored and recalculated: same result (' + approx(last.total) + ' assigned).'
                 : 'Scenario A restored, but the recalculated result differs by ' + d.toFixed(3) + ' residents.');
  }
  function facName(id) { var m = byId[id]; return m ? (m.r.name || '(no name) ' + id) : id; }
  function changes(a, b) {   // assumption differences A -> B, as readable lines
    var out = [];
    if (a.km !== b.km) out.push('Max. distance: ' + a.km + ' km → ' + b.km + ' km');
    if (a.exploratory !== b.exploratory) out.push('Exploratory option: ' + (a.exploratory ? 'on' : 'off') + ' → ' + (b.exploratory ? 'on' : 'off'));
    var ids = {}; [a.assumed, b.assumed, a.unavailable, b.unavailable].forEach(function (o) { Object.keys(o).forEach(function (k) { ids[k] = 1; }); });
    Object.keys(ids).sort().forEach(function (id) {
      var ca = a.assumed[id], cb = b.assumed[id];
      if (ca !== cb) out.push(esc(facName(id)) + ': capacity ' + (ca == null ? 'unknown' : fmt(ca)) + ' → ' + (cb == null ? 'unknown' : fmt(cb)));
      if (!!a.unavailable[id] !== !!b.unavailable[id]) out.push(esc(facName(id)) + ': ' + (a.unavailable[id] ? 'unavailable → available' : 'available → unavailable'));
    });
    return out;
  }

  // ---------------------------------------------------------------- panel
  var box = document.getElementById('scn-tab');
  function sign(v) { return (v > 0 ? '+' : v < 0 ? '−' : '±') + (Math.abs(v) < 0.5 ? '0' : fmt(Math.abs(v))); }
  function compareHtml() {
    if (!scenA) return '<div class="btns scn-btns"><button id="scn-capA">Capture as Scenario A</button></div>';
    var a = scenA.sum, b = summary(last), ch = changes(scenA.state, S);
    var row = function (lab, va, vb, f, diff) { return '<tr><td>' + lab + '</td><td>' + f(va) + '</td><td>' + f(vb) + '</td><td>' + (diff ? sign(vb - va) : '') + '</td></tr>'; };
    var same = Math.abs(a.demand - b.demand) < 1e-6 && scenA.build === D.build;
    return '<div class="scn-cmp"><table class="scn-t">' +
      '<tr><th></th><th>A</th><th>B (now)</th><th>B − A</th></tr>' +
      row('Distance · exploratory', scenA.state, S, function (v) { return v.km + ' km · ' + (v.exploratory ? 'on' : 'off'); }) +
      row('Est. exposed residents', a.demand, b.demand, approx, true) +
      row('Facilities with places', a.nFac, b.nFac, fmt, true) +
      row('Places at those facilities', a.places, b.places, fmt, true) +
      '<tr class="hl">' + row('Assigned', a.assigned, b.assigned, approx, true).slice(4) +
      row('Unassigned', a.unassigned, b.unassigned, approx, true) +
      '</table>' +
      '<div class="scn-diff">Additional residents assigned under these assumptions (B − A): <b>' + sign(b.assigned - a.assigned) + '</b></div>' +
      (same ? '<div class="note" style="max-width:none">Same demand data and coverage in A and B (build ' + esc(D.build) + ').</div>'
            : '<div class="scn-flag">A and B use different demand data: the difference is not comparable.</div>') +
      '<div class="scn-chh">Assumptions changed A → B (' + ch.length + ')</div>' +
      (ch.length ? '<ul class="scn-ch">' + ch.map(function (c) { return '<li>' + c + '</li>'; }).join('') + '</ul>' : '<div class="muted">None: B has the same assumptions as A.</div>') +
      (ch.length > 1 ? '<div class="scn-flag">Several assumptions changed: the difference cannot be attributed to any one of them.</div>' : '') +
      '<div class="btns scn-btns"><button id="scn-resA">Restore A</button><button id="scn-capA">Capture B as new A</button><button id="scn-clrA">Clear comparison</button></div>' +
      '<div class="note" style="max-width:none">A captured at ' + esc(scenA.at) + '; it is not changed by later edits.</div></div>';
  }
  function renderPanel() {
    var open = {}; box.querySelectorAll('details[data-k]').forEach(function (d) { open[d.dataset.k] = d.open; });   // keep open sections
    var r = last, tot = demandTotal, un = tot - r.total, c = r.counts;
    var gapRows = A.GAP.map(function (k) {
      return '<tr><td class="g">' + swatch(k) + (k === 'no_candidate' ? 'no candidate within ' + S.km + ' km' : GAP_LABEL[k]) + '</td><td>' + approx(r.gapTotals[k]) + '</td></tr>';
    }).join('');
    var list = r.facRec.map(function (f) {
      return '<tr><td title="' + esc(f.name || '') + '">' + esc((f.name || '(no name)').slice(0, 26)) + '</td><td>' + fmt(capacity(f).v) +
        '</td><td>' + approx(r.assignedById[f.id]) + '</td><td><button class="x" data-zoom="' + esc(f.id) + '" title="Show on map">map</button>' +
        '<button class="x" data-remove="' + esc(f.id) + '" title="Remove from the scenario (clears the assumed capacity)">✕</button></td></tr>';
    }).join('');
    var nUnav = Object.keys(S.unavailable).length, nZero = Object.keys(S.assumed).filter(function (k) { return S.assumed[k] === 0; }).length;
    var det = function (k, title, body, dflt) {
      var o = k in open ? open[k] : dflt;
      return '<details data-k="' + k + '"' + (o ? ' open' : '') + '><summary>' + title + '</summary>' + body + '</details>';
    };
    var exploratory = S.exploratory ? '<div class="scn-flag">Exploratory scenario: includes candidates outside EMS coverage, where 2021 flooding was not mapped.</div>' : '';
    box.innerHTML =
      '<div class="scn-head">Shelter planning scenario <span>requires verification</span></div>' +
      (D.nDocumented ? '' : '<div class="scn-base">Our inventory contains no documented shelter-capacity baseline.</div>') +
      '<div class="scn-warn">Straight-line connections are not verified routes. Entered capacity is an assumption unless a documented source supports it.</div>' +
      '<div class="scn-scope">Scope: whole analysis area (all EMS mapped areas + 1 km). Map zoom and the candidate filters change the display only, not these results.</div>' +
      '<div class="scn-sub"><span class="k k-asm">User-entered</span> Scenario assumptions</div>' +
      '<label class="scn-in">Max. straight-line distance <b id="scn-km-v">' + S.km + ' km</b>' +
      '<input type="range" id="scn-km" min="1" max="25" step="1" value="' + S.km + '"></label>' +
      '<label class="scn-chk"><input type="checkbox" id="scn-expl"' + (S.exploratory ? ' checked' : '') + '> Exploratory: also use candidates outside EMS coverage</label>' +
      exploratory +
      '<div class="scn-cnt">' + Object.keys(S.assumed).length + ' capacities entered' + (nZero ? ' (' + nZero + ' of them 0)' : '') + ' · ' + nUnav + ' marked unavailable</div>' +
      '<div class="scn-sub"><span class="k k-res">Calculated</span> Result under these assumptions</div>' +
      '<table class="scn-t">' +
      '<tr><td>Estimated exposed residents <span class="k k-hist">2020 est.</span><sup>1</sup></td><td>' + approx(tot) + '</td></tr>' +
      '<tr class="hl"><td>Assigned a place in this scenario</td><td><span id="scn-assigned">' + approx(r.total) + '</span> <span class="pc">(' + pct(r.total, tot) + ')</span></td></tr>' +
      '<tr class="hl"><td>Remaining unassigned</td><td id="scn-unassigned">' + approx(un) + ' <span class="pc">(' + pct(un, tot) + ')</span></td></tr>' +
      '<tr><td>Facilities with places / places entered</td><td><span id="scn-nfac">' + fmt(c.places) + '</span> / ' + fmt(r.placesEntered) + '</td></tr>' +
      (r.cross >= 0.5 ? '<tr><td>of the assigned: across a national border</td><td>' + approx(r.cross) + '</td></tr>' : '') +
      '</table>' +
      '<div class="scn-sub">A/B comparison with a baseline</div>' + compareHtml() +
      det('gaps', 'Why residents remain unassigned', '<table class="scn-t">' + gapRows + '</table>', false) +
      det('fac', 'Facility inputs (' + r.facRec.length + ' with places' + (nUnav ? ', ' + nUnav + ' unavailable' : '') + ')',
        (list ? '<div class="scn-list"><table class="scn-t"><tr><th>facility</th><th>places</th><th>assigned</th><th></th></tr>' + list + '</table></div>'
              : '<div class="scn-empty">No places entered. Open a facility’s popup on the map and enter an assumed number of places. Nothing is assigned until you do.</div>'), false) +
      det('data', 'Data behind this scenario', '<table class="scn-t">' +
        '<tr><th colspan="2"><span class="k k-cand">Candidate facilities (OSM' + (D.osmDate ? ', ' + esc(D.osmDate) : '') + ')</span></th></tr>' +
        '<tr><td>Eligible, places entered</td><td>' + fmt(c.places) + '</td></tr>' +
        '<tr><td>Eligible, capacity unknown<sup>2</sup></td><td id="scn-nunknown">' + fmt(c.unknown) + '</td></tr>' +
        '<tr><td>Marked unavailable or 0 places</td><td>' + fmt(c.unavailable) + '</td></tr>' +
        '<tr><td>Excluded: inside 2021 extent / unresolved</td><td>' + fmt(c.excluded_screen) + '</td></tr>' +
        '<tr><td>' + (S.exploratory ? 'Outside EMS coverage (excluded unless exploratory)' : 'Not used: outside EMS coverage') + '</td><td>' + fmt(c.excluded_ems) + '</td></tr>' +
        '<tr><td>Documented capacity (with source)</td><td>' + fmt(D.nDocumented) + ' of ' + fmt(markers.length) + '</td></tr>' +
        '</table>' +
        '<div class="note" style="max-width:none"><span class="k k-hist">Historical estimate</span> <sup>1</sup> ' + esc(D.reference) +
        ', inside the observed July 2021 flood extent (Copernicus EMS): a 2020 estimate, not today’s population. EMS mapped only the requested areas ' +
        '(not mapped ≠ not flooded) and misses water between buildings, so it is a lower bound in towns, especially in Belgium. ' +
        '<sup>2</sup> Unknown capacity contributes no places: missing data, not zero real capacity and not a shortage.</div>', false) +
      det('method', 'Method and limits', '<div class="note" style="max-width:none">Maximum flow: the total assigned is the largest possible under the ' +
        'stated assumptions (each origin’s residents, each facility’s places, the distance limit); which origin uses which facility is one of several ' +
        'equally valid answers. Distances are straight lines, not routes, travel times or proof of access. Facilities inside the 2021 extent or with ' +
        'unresolved screening never take part. Data build ' + esc(D.build) + '.</div>', false) +
      '<div class="scn-sub">Save / restore</div>' +
      '<div class="btns scn-btns"><button id="scn-save">Save scenario (JSON)</button><button id="scn-imp">Restore from file</button>' +
      '<button id="scn-exp-in">Export inputs (CSV)</button><button id="scn-exp-out">Export results (CSV)</button><button id="scn-reset">Reset</button>' +
      '<input type="file" id="scn-file" accept=".json,.csv,application/json,text/csv" hidden></div>' +
      '<div id="scn-msg" class="note scn-msg">' + esc(lastMsg) + '</div>';
    bind();
  }

  function bind() {
    var km = document.getElementById('scn-km');
    km.oninput = function () { document.getElementById('scn-km-v').textContent = km.value + ' km'; };
    km.onchange = function () { S.km = +km.value; recalc(); };
    document.getElementById('scn-expl').onchange = function (e) { S.exploratory = e.target.checked; recalc(); };
    document.getElementById('scn-reset').onclick = function () { reset(); recalc(); msg('Scenario reset: no assumptions entered, default settings.'); };
    document.getElementById('scn-save').onclick = saveJson;
    document.getElementById('scn-exp-in').onclick = exportInputs;
    document.getElementById('scn-exp-out').onclick = exportResults;
    document.getElementById('scn-imp').onclick = function () { document.getElementById('scn-file').click(); };
    document.getElementById('scn-file').onchange = importFile;
    document.getElementById('scn-capA').onclick = capture;
    var ra = document.getElementById('scn-resA'); if (ra) ra.onclick = restoreA;
    var ca = document.getElementById('scn-clrA'); if (ca) ca.onclick = function () { scenA = null; renderPanel(); msg('Comparison cleared.'); };
    box.querySelectorAll('[data-remove]').forEach(function (b) {
      b.onclick = function () { delete S.assumed[b.dataset.remove]; delete S.unavailable[b.dataset.remove]; recalc(); };
    });
    box.querySelectorAll('[data-zoom]').forEach(function (b) {
      b.onclick = function () { var m = byId[b.dataset.zoom]; APP.cluster.zoomToShowLayer(m, function () { m.openPopup(); }); };
    });
  }
  var lastMsg = '';
  function msg(t) { lastMsg = t; var e = document.getElementById('scn-msg'); if (e) e.textContent = t; }

  // ---------------------------------------------------------------- popup section (scenario inputs per facility)
  function popupHtml(r) {
    var c = capacity(r), sc = screening(r), doc = r.dcap != null && r.dcap !== '';
    var h = '<div class="scn-pop"><b>Planning scenario (assumptions, not verified)</b><br>' +
      '<span class="muted">Documented capacity: ' + (doc ? esc(r.dcap) + ' places (' + esc(r.dsrc) + ', ' + esc(r.ddate) + ')' : 'none in our sources') + '</span>';
    if (r.c === 'inside_observed' || r.c === 'boundary_unresolved')
      return h + '<br>Not used in the scenario: ' + (r.c === 'inside_observed' ? 'inside the observed 2021 flood extent.' : 'unresolved flood screening.') + '</div>';
    if (sc === 'excluded') h += '<br><span class="muted">Outside EMS coverage: used only if the exploratory option is on.</span>';
    else h += '<br><span class="muted">Outside the mapped 2021 extent: this does not establish safety or availability. It takes part only if you enter places.</span>';
    h += '<div class="scn-row">Assumed capacity <input type="number" min="0" step="1" class="scn-cap" data-id="' + esc(r.id) + '" value="' +
      (S.assumed[r.id] != null ? S.assumed[r.id] : '') + '" placeholder="unknown"> places ' +
      '<button class="scn-set" data-id="' + esc(r.id) + '">Set</button>' +
      (S.assumed[r.id] != null ? '<button class="scn-clear" data-id="' + esc(r.id) + '">Clear</button>' : '') + '</div>' +
      '<label class="scn-row"><input type="checkbox" class="scn-av" data-id="' + esc(r.id) + '"' + (S.unavailable[r.id] ? '' : ' checked') + '> Available in this scenario</label>';
    if (c.v != null && last && state(r) === 'places')
      h += '<div>In this scenario: ' + approx(last.assignedById[r.id] || 0) + ' of ' + fmt(c.v) + ' places assigned.</div>';
    else if (c.v == null) h += '<div class="muted">Capacity unknown: contributes no places (not the same as zero real capacity).</div>';
    return h + '</div>';
  }
  function wire(popup) {   // popup content is a function of the marker, so update() re-renders it with the new state
    var el = popup.getElement(); if (!el) return;
    var inp = el.querySelector('.scn-cap'); if (!inp) return;
    // the re-render replaces the clicked button: stop the click reaching the map (it would close the popup) and
    // re-render only after the event has finished
    L.DomEvent.disableClickPropagation(el.querySelector('.scn-pop'));
    var id = inp.dataset.id, again = function () { setTimeout(function () { recalc(); popup.update(); wire(popup); }, 0); };
    function set() {
      var v = inp.value.trim();
      if (v === '') { delete S.assumed[id]; again(); return; }
      if (!/^\d+$/.test(v)) { inp.style.borderColor = '#dc2626'; inp.title = 'Enter a whole number of places (0 or more)'; return; }
      S.assumed[id] = parseInt(v, 10); again();
    }
    el.querySelector('.scn-set').onclick = set;
    inp.onkeydown = function (ev) { if (ev.key === 'Enter') set(); };
    var cl = el.querySelector('.scn-clear'); if (cl) cl.onclick = function () { delete S.assumed[id]; again(); };
    el.querySelector('.scn-av').onchange = function (ev) { if (ev.target.checked) delete S.unavailable[id]; else S.unavailable[id] = true; again(); };
  }
  map.on('popupopen', function (e) { wire(e.popup); });

  // ---------------------------------------------------------------- export / import
  function csv(rows) {
    return rows.map(function (r) { return r.map(function (v) {
      v = v == null ? '' : String(v); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }).join(','); }).join('\n') + '\n';
  }
  function download(name, text, type) {
    var a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text], {type: type || 'text/csv'}));
    a.download = name; document.body.appendChild(a); a.click(); a.remove();
  }
  var stamp = function () { return new Date().toISOString().slice(0, 10); };
  function params() { return [S.km * 1000, S.exploratory ? 'yes' : 'no']; }
  var INPUT_COLS = ['candidate_id', 'name', 'facility_type', 'screen_category', 'documented_capacity', 'documented_capacity_source',
                    'assumed_capacity', 'available', 'scenario_state', 'assigned_residents_estimate', 'max_distance_m', 'exploratory_outside_ems', 'note'];
  function exportInputs() {
    var rows = [INPUT_COLS];
    markers.forEach(function (m) {
      var r = m.r;
      if (S.assumed[r.id] == null && !S.unavailable[r.id] && (r.dcap == null || r.dcap === '')) return;
      rows.push([r.id, r.name, r.t, r.c, r.dcap, r.dsrc, S.assumed[r.id], S.unavailable[r.id] ? 'no' : 'yes', state(r),
                 last.assignedById[r.id] != null ? last.assignedById[r.id].toFixed(1) : '', ].concat(params(),
                 ['assumed_capacity and available are scenario assumptions, not verified facts']));
    });
    var n = rows.length - 1;
    if (!n) rows.push(['', '', '', '', '', '', '', '', 'settings_only', ''].concat(params(), ['scenario settings only: no facility inputs entered']));
    download('shelter_scenario_inputs_' + stamp() + '.csv', csv(rows));
    msg('Exported ' + n + ' facility rows with scenario inputs' + (n ? '' : ' (one settings row keeps the distance and exploratory option)') + '.');
  }
  function exportResults() {
    var rows = [['row_type', 'origin_id', 'country', 'lon', 'lat', 'estimated_residents', 'assigned', 'unassigned', 'gap_reason',
                 'candidate_id', 'facility_name', 'straight_line_km', 'max_distance_m', 'exploratory_outside_ems']];
    origins.forEach(function (o, i) {
      rows.push(['origin', o.id, o.cc, o.lon, o.lat, o.demand.toFixed(2), last.byOrigin[i].toFixed(2),
                 Math.max(0, o.demand - last.byOrigin[i]).toFixed(2), last.gaps[i] || '', '', '', ''].concat(params()));
    });
    last.flows.forEach(function (f) {
      var o = origins[f.o], r = last.facRec[f.f];
      rows.push(['assignment', o.id, o.cc, o.lon, o.lat, '', f.amount.toFixed(2), '', '', r.id, r.name, (f.dist / 1000).toFixed(2)].concat(params()));
    });
    download('shelter_scenario_results_' + stamp() + '.csv', csv(rows));
    msg('Exported ' + origins.length + ' origins and ' + last.flows.length + ' assignments (estimates under the stated assumptions).');
  }
  var FORMAT = 'floodmap-shelter-scenario', VERSION = 1;
  function scenarioJson() {
    var ids = {}; Object.keys(S.assumed).concat(Object.keys(S.unavailable)).forEach(function (k) { ids[k] = 1; });
    return {format: FORMAT, version: VERSION, saved_at: new Date().toISOString(), data_build: D.build,
            demand_total: +demandTotal.toFixed(3), n_origins: origins.length, n_candidates: markers.length,
            settings: {max_distance_m: S.km * 1000, exploratory_outside_ems: S.exploratory},
            facilities: Object.keys(ids).sort().map(function (id) {
              return {candidate_id: id, name: facName(id), assumed_capacity: S.assumed[id] != null ? S.assumed[id] : null, available: !S.unavailable[id]}; }),
            result_assigned: +last.total.toFixed(3),
            note: 'assumed_capacity and available are scenario assumptions entered by the user, not verified facts'};
  }
  function saveJson() {
    var j = scenarioJson();
    download('shelter_scenario_' + stamp() + '.json', JSON.stringify(j, null, 2), 'application/json');
    msg('Saved the complete scenario: ' + j.facilities.length + ' facility inputs, ' + S.km + ' km, exploratory ' + (S.exploratory ? 'on' : 'off') + '.');
  }
  function parseCsv(t) {
    var rows = [], row = [], f = '', q = false;
    for (var i = 0; i < t.length; i++) {
      var ch = t[i];
      if (q) { if (ch === '"') { if (t[i + 1] === '"') { f += '"'; i++; } else q = false; } else f += ch; }
      else if (ch === '"') q = true;
      else if (ch === ',') { row.push(f); f = ''; }
      else if (ch === '\n' || ch === '\r') { if (ch === '\r' && t[i + 1] === '\n') i++; row.push(f); rows.push(row); row = []; f = ''; }
      else f += ch;
    }
    if (f !== '' || row.length) { row.push(f); rows.push(row); }
    return rows.filter(function (r) { return r.some(function (v) { return v !== ''; }); });
  }

  // Restore = parse and validate everything first, then REPLACE the scenario (never merge). Invalid values or conflicting
  // settings abort without touching the current scenario; unknown / ineligible candidate ids are skipped and reported.
  function km(v) {   // metres -> slider km, or null if invalid
    var n = Number(v);
    return /^\s*\d+(\.0+)?\s*$/.test(String(v)) && n >= 1000 && n <= 25000 && n % 1000 === 0 ? n / 1000 : null;
  }
  var YES = ['yes', 'true', '1'], NO = ['no', 'false', '0'];
  function parseScenario(text, name) {
    var p = {entries: {}, km: undefined, exploratory: undefined, errors: [], unknown: [], ineligible: [], warnings: [], legacy: [], kind: ''};
    function entry(id, cap, avail, where) {
      if (!id) { p.errors.push(where + ': empty candidate_id'); return; }
      var e = {cap: cap, available: avail}, old = p.entries[id];
      if (old && (old.cap !== cap || old.available !== avail)) { p.errors.push(where + ': ' + id + ' appears twice with different values'); return; }
      p.entries[id] = e;
    }
    function setting(key, v, where) {
      if (p[key] !== undefined && p[key] !== v) p.errors.push(where + ': conflicting ' + (key === 'km' ? 'max_distance_m' : 'exploratory_outside_ems') + ' (' + p[key] + ' vs ' + v + ')');
      else p[key] = v;
    }
    var t = text.replace(/^﻿/, '');
    if (/^\s*\{/.test(t)) {
      p.kind = 'JSON';
      var j; try { j = JSON.parse(t); } catch (e) { p.errors.push('not valid JSON (' + e.message + ')'); return p; }
      if (j.format !== FORMAT) { p.errors.push('not a saved shelter scenario (format "' + j.format + '")'); return p; }
      if (j.version !== VERSION) { p.errors.push('unsupported version ' + j.version + ' (this map reads version ' + VERSION + ')'); return p; }
      var s = j.settings || {};
      var k = km(s.max_distance_m);
      if (k == null) p.errors.push('settings: max_distance_m must be 1000–25000 in steps of 1000 (got ' + JSON.stringify(s.max_distance_m) + ')'); else p.km = k;
      if (typeof s.exploratory_outside_ems !== 'boolean') p.errors.push('settings: exploratory_outside_ems must be true or false'); else p.exploratory = s.exploratory_outside_ems;
      if (j.data_build !== D.build) p.warnings.push('saved with data build ' + j.data_build + ', this map is ' + D.build + ': the demand or inventory differ, so results may not match');
      else if (j.demand_total != null && Math.abs(j.demand_total - demandTotal) > 0.01) p.warnings.push('saved demand total differs from this map');
      if (!Array.isArray(j.facilities)) { p.errors.push('facilities must be a list'); return p; }
      j.facilities.forEach(function (f, i) {
        var where = 'facility ' + (i + 1), cap = f.assumed_capacity;
        if (cap != null && !(Number.isInteger(cap) && cap >= 0)) { p.errors.push(where + ' (' + f.candidate_id + '): assumed_capacity must be a whole number ≥ 0 or null'); return; }
        if (typeof f.available !== 'boolean') { p.errors.push(where + ' (' + f.candidate_id + '): available must be true or false'); return; }
        entry(f.candidate_id, cap == null ? null : cap, f.available, where);
      });
      p.expect = j.result_assigned;
      return p;
    }
    p.kind = 'CSV';
    var rows = parseCsv(t), h = (rows.shift() || []).map(function (x) { return x.trim(); });
    var col = function (n) { return h.indexOf(n); };
    var iid = col('candidate_id'), icap = col('assumed_capacity'), iav = col('available'), ikm = col('max_distance_m'), iex = col('exploratory_outside_ems'), ist = col('scenario_state');
    if (iid < 0 || (icap < 0 && iav < 0)) { p.errors.push('the file needs candidate_id and assumed_capacity and/or available columns'); return p; }
    rows.forEach(function (r, n) {
      var where = 'row ' + (n + 2), get = function (i) { return i < 0 ? '' : (r[i] || '').trim(); };
      if (ikm >= 0 && get(ikm) !== '') { var k = km(get(ikm)); if (k == null) p.errors.push(where + ': invalid max_distance_m "' + get(ikm) + '"'); else setting('km', k, where); }
      if (iex >= 0 && get(iex) !== '') { var x = get(iex).toLowerCase();
        if (YES.indexOf(x) >= 0) setting('exploratory', true, where); else if (NO.indexOf(x) >= 0) setting('exploratory', false, where);
        else p.errors.push(where + ': invalid exploratory_outside_ems "' + get(iex) + '"'); }
      if (get(ist) === 'settings_only' && get(iid) === '') return;
      var cap = get(icap), av = get(iav).toLowerCase();
      if (cap !== '' && !/^\d+$/.test(cap)) { p.errors.push(where + ' (' + get(iid) + '): invalid assumed_capacity "' + cap + '"'); return; }
      if (av !== '' && YES.indexOf(av) < 0 && NO.indexOf(av) < 0) { p.errors.push(where + ' (' + get(iid) + '): invalid available "' + get(iav) + '"'); return; }
      entry(get(iid), cap === '' ? null : parseInt(cap, 10), NO.indexOf(av) < 0, where);
    });
    if (p.km === undefined) p.legacy.push('max. distance');
    if (p.exploratory === undefined) p.legacy.push('exploratory option');
    return p;
  }
  function restoreScenario(text, name) {
    var p = parseScenario(text, name);
    if (p.errors.length) {
      msg('Restore aborted, current scenario unchanged. ' + p.errors.length + ' problem' + (p.errors.length > 1 ? 's' : '') + ' in ' + name + ':\n• ' +
          p.errors.slice(0, 8).join('\n• ') + (p.errors.length > 8 ? '\n• … and ' + (p.errors.length - 8) + ' more' : ''));
      return p;
    }
    var next = {km: p.km !== undefined ? p.km : DEFAULT_KM, exploratory: p.exploratory !== undefined ? p.exploratory : false, assumed: {}, unavailable: {}};
    Object.keys(p.entries).forEach(function (id) {
      var m = byId[id], e = p.entries[id];
      if (!m) { p.unknown.push(id); return; }
      if (m.r.c === 'inside_observed' || m.r.c === 'boundary_unresolved') { p.ineligible.push(id); return; }
      if (e.cap != null) next.assumed[id] = e.cap;
      if (!e.available) next.unavailable[id] = true;
    });
    S = next; recalc();
    var nz = Object.keys(S.assumed).filter(function (k) { return S.assumed[k] === 0; }).length;
    var lines = ['Restored from ' + name + ' (' + p.kind + '); the previous scenario was replaced: ' + S.km + ' km, exploratory ' + (S.exploratory ? 'on' : 'off') + ', ' +
                 Object.keys(S.assumed).length + ' capacities' + (nz ? ' (' + nz + ' zero)' : '') + ', ' + Object.keys(S.unavailable).length + ' unavailable. ' +
                 'Recalculated: ' + approx(last.total) + ' assigned.'];
    if (p.legacy.length) lines.push('Not in this file (older export), set to defaults instead: ' + p.legacy.join(' and ') + ' (' + DEFAULT_KM + ' km, off).');
    if (p.unknown.length) lines.push('Partial restore: ' + p.unknown.length + ' candidate id(s) not in this map’s inventory were skipped: ' + p.unknown.slice(0, 5).join(', ') + (p.unknown.length > 5 ? ', …' : '') + '.');
    if (p.ineligible.length) lines.push(p.ineligible.length + ' candidate(s) inside the 2021 extent / unresolved were skipped (never used in the scenario): ' + p.ineligible.slice(0, 5).join(', ') + '.');
    p.warnings.forEach(function (w) { lines.push('Warning: ' + w + '.'); });
    if (p.expect != null && !p.unknown.length && !p.ineligible.length && !p.warnings.length && Math.abs(p.expect - last.total) > 0.01)
      lines.push('Warning: the saved result was ' + approx(p.expect) + ' assigned.');
    msg(lines.join('\n'));
    return p;
  }
  function importFile(ev) {
    var file = ev.target.files[0]; if (!file) return;
    file.text().then(function (t) { restoreScenario(t, file.name); ev.target.value = ''; });
  }

  // ---------------------------------------------------------------- tabs
  document.querySelectorAll('.shel-tabs button').forEach(function (b) {
    b.onclick = function () {
      document.querySelectorAll('.shel-tabs button').forEach(function (x) { x.classList.toggle('on', x === b); });
      var scn = b.dataset.tab === 'scenario';
      document.getElementById('cand-tab').hidden = scn; box.hidden = !scn;
      window.dispatchEvent(new Event('resize'));
    };
  });

  window.ScenarioUI = {popupHtml: popupHtml, capacity: capacity, state: state, recalc: recalc, pct: pct,
                       restore: restoreScenario, json: scenarioJson, capture: capture, restoreA: restoreA, layers: {gaps: gapLayer, lines: lineLayer},
                       get: function () { return {state: S, result: last, origins: origins, demandTotal: demandTotal, A: scenA}; }};   // also used by tests
  recalc();
})();
