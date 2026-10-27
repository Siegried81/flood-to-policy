"""Write the Power BI report of `bi/FloodPolicyKit.pbip` as PBIR files.

The report is a story: a cover that states the seven findings and links to
the page behind each, seven story pages (the headline, behind the defences,
where, downstream of someone else, what is at stake, who, declared vs
exposed), a drillthrough page for one region and a tooltip page that shows a
place's mini-profile on hover. PBIR is the documented, schema-validated text
format Power BI Desktop reads (one `visual.json` per visual). The layout is
generated rather than typed because a hundred-odd files sharing one grid, one
navigation bar, one palette and one way of naming a field are only consistent
if one function writes them all.

Run it once to (re)build the layout; then `scripts/validate_bi_report.py`
checks every file against Microsoft's schemas. Once the report has been edited
and saved in Power BI Desktop, the saved files are the source: running this
again overwrites `bi/FloodPolicyKit.Report/definition/` and the theme.

Every field is named here as (table, column or measure) and
`tests/test_export_bi.py` checks each one against the TMDL model, so a rename
on either side fails a test instead of opening as a grey box.
"""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "bi" / "FloodPolicyKit.Report"
DEFINITION = REPORT / "definition"
THEME_NAME = "FloodPolicyKit.json"
THEME_PATH = REPORT / "StaticResources" / "RegisteredResources" / THEME_NAME

SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"
#: The newest versions Microsoft publishes at the time of writing. Desktop
#: 2.159 (October 2026) saves visual.json as 2.14.0, which is not published, so
#: visuals are written at 2.13.0: Desktop reads older versions and upgrades them.
VERSIONS = {"report": "3.3.0", "page": "2.1.0", "visualContainer": "2.13.0",
            "pagesMetadata": "1.1.0", "versionMetadata": "1.0.0"}

W, H = 1280, 720          # 16:9 canvas
M, G = 24, 16             # outer margin, gutter
CW = W - 2 * M            # content width
#: The vertical grid every story page shares: navigation bar, title, the
#: "what to look at" line, then the content band down to the source line.
NAV_Y, NAV_H = 10, 30
TITLE_Y, SUB_Y = 48, 84
TOP, BOTTOM = 124, 676
FOOT_Y = 684
TIP_W, TIP_H = 320, 240   # Power BI's default tooltip page size

INK, MUTED, LINE = "#1B1F27", "#5D6675", "#E1E4EA"
PAGE_BG, CARD_BG = "#F6F7F9", "#FFFFFF"
#: ColorBrewer BuPu, light blue to purple: sequential, colourblind-safe and
#: readable in greyscale like the YlOrBr of the Streamlit map, but read as
#: water rather than fire - the owner's choice for the report.
RAMP = ("#EDF8FB", "#BFD3E6", "#9EBCDA", "#8C96C6", "#8856A7", "#810F7C")
EXPOSURE = RAMP[4]
RESIDUAL = RAMP[5]        # what the defences do not hold: the darkest step
HELD = RAMP[1]            # what they hold: a light step, so the residual reads first
ACCENT = "#1B9E77"        # the one accent (cross-border argument): sea green, distinct from the ramp
NEUTRAL = "#9AA0A6"
SHADOW = INK

CREDIT = "© EuroGeographics for the administrative boundaries"
EXPLORE = "Hover a bar or dot for the place's card; right-click a region > Drill through > Region detail."

#: The story pages in reading order, with the label of their button in the
#: navigation bar. The drillthrough and tooltip pages are reached from the
#: data, never from the bar.
STORY = (("overview", "Overview"), ("headline", "1  Headline"), ("defences", "2  Defences"),
         ("where", "3  Where"), ("downstream", "4  Cross-border"), ("at_stake", "5  At stake"),
         ("who", "6  Who"), ("declared", "7  Declared"), ("rivers", "8  Rivers"))
TOOLTIP_PAGE = "region_tooltip"


# --- field references ---------------------------------------------------------

def col(table: str, name: str) -> dict:
    return {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}}


def measure(name: str) -> dict:
    """Every measure lives on the Exposure table."""
    return {"Measure": {"Expression": {"SourceRef": {"Entity": "Exposure"}}, "Property": name}}


def level(name: str) -> dict:
    """A level of the Regions[Geography] hierarchy (Country, Region)."""
    return {"HierarchyLevel": {
        "Expression": {"Hierarchy": {"Expression": {"SourceRef": {"Entity": "Regions"}},
                                     "Hierarchy": "Geography"}},
        "Level": name}}


def ref(field: dict) -> str:
    """The queryRef Power BI itself writes: Table.Field or Table.Hierarchy.Level."""
    if "HierarchyLevel" in field:
        return f"Regions.Geography.{field['HierarchyLevel']['Level']}"
    kind = "Column" if "Column" in field else "Measure"
    return f"{field[kind]['Expression']['SourceRef']['Entity']}.{field[kind]['Property']}"


def proj(field: dict, display: str | None = None, active: bool | None = None) -> dict:
    out = {"field": field, "queryRef": ref(field)}
    if display:
        out["displayName"] = display
    if active is not None:
        out["active"] = active
    return out


# --- formatting values --------------------------------------------------------

def lit(value) -> dict:
    """A literal in Power BI's query syntax: 'text', 12D, 3L, true."""
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, int):
        text = f"{value}L"
    elif isinstance(value, float):
        text = f"{int(value)}D" if value.is_integer() else f"{value}D"
    else:
        text = "'" + str(value).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": text}}}


def color(hex_: str) -> dict:
    return {"solid": {"color": lit(hex_)}}


def _props(properties: dict) -> dict:
    return {k: v if isinstance(v, dict) else lit(v) for k, v in properties.items()}


def obj(**properties) -> list:
    """One formatting object with no selector: [{"properties": {...}}]."""
    return [{"properties": _props(properties)}]


def state(selector_id: str = "default", **properties) -> dict:
    """One state of a button (default, hover): the selector Desktop writes for it."""
    return {"properties": _props(properties), "selector": {"id": selector_id}}


def container(title: str | None = None, subtitle: str | None = None, frame: bool = True,
              pad_top: float = 8.0, header: bool = True) -> dict:
    """Title, subtitle and the white card every data visual sits on.

    The card has rounded corners and a faint drop shadow, so a page reads as
    a set of tiles on the grey page rather than as boxes drawn on it. Text
    boxes and buttons go frameless and without the hover header: its icons
    (focus mode, more options) mean nothing on a label.
    """
    out: dict = {}
    if title:
        out["title"] = obj(show=True, text=title, fontColor=color(INK), fontSize=12.0, bold=True)
    else:
        out["title"] = obj(show=False)
    if subtitle:
        out["subTitle"] = obj(show=True, text=subtitle, fontColor=color(MUTED), fontSize=9.0)
    if frame:
        out["background"] = obj(show=True, color=color(CARD_BG), transparency=0.0)
        out["border"] = obj(show=True, color=color(LINE), radius=10.0, width=1.0)
        out["dropShadow"] = obj(show=True, color=color(SHADOW), transparency=88.0,
                                position="Outer", preset="Bottom")
        out["padding"] = obj(top=pad_top, bottom=8.0, left=12.0, right=12.0)
    else:
        out["background"] = obj(show=False)
        out["border"] = obj(show=False)
    if not header:
        out["visualHeader"] = obj(show=False)
    return out


def gradient(field: dict, low: str = RAMP[1], high: str = RAMP[5]) -> dict:
    """Bar or cell colour on a sequential ramp, driven by `field`."""
    return {"solid": {"color": {"expr": {"FillRule": {
        "Input": field,
        "FillRule": {"linearGradient2": {
            "min": {"color": {"Literal": {"Value": f"'{low}'"}}},
            "max": {"color": {"Literal": {"Value": f"'{high}'"}}},
            "nullColoringStrategy": {"strategy": {"Literal": {"Value": "'asZero'"}}},
        }},
    }}}}}


def series_colours(colours: dict) -> list:
    """One fill per measure of a multi-measure chart, selected by its queryRef."""
    return [{"properties": {"fill": color(hex_)}, "selector": {"metadata": ref(field)}}
            for field, hex_ in colours]


def sort_desc(field: dict) -> dict:
    return {"sort": [{"field": field, "direction": "Descending"}], "isDefaultSort": False}


def region_tooltip() -> dict:
    """Hovering a data point shows the tooltip page instead of the default box."""
    return {"visualTooltip": obj(show=True, type="Canvas", section=TOOLTIP_PAGE)}


# --- visuals ------------------------------------------------------------------

def visual(name: str, box: tuple, kind: str, *, roles: dict | None = None, sort: dict | None = None,
           objects: dict | None = None, frame: dict | None = None, z: int = 0,
           sync: str | None = None, how: str | None = None) -> dict:
    x, y, w, h = box
    body: dict = {"visualType": kind}
    if roles:
        body["query"] = {"queryState": {role: {"projections": p} for role, p in roles.items()}}
        if sort:
            body["query"]["sortDefinition"] = sort
    if objects:
        body["objects"] = objects
    body["visualContainerObjects"] = frame if frame is not None else container()
    if sync:
        body["syncGroup"] = {"groupName": sync, "fieldChanges": True, "filterChanges": True}
    body["drillFilterOtherVisuals"] = True
    out = {"$schema": f"{SCHEMA}/visualContainer/{VERSIONS['visualContainer']}/schema.json",
           "name": name,
           "position": {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": z},
           "visual": body}
    if how:
        out["howCreated"] = how
    return out


def text(name: str, box: tuple, paragraphs: list, frame: dict | None = None, z: int = 0,
         align: str | None = None) -> dict:
    """A text box. `paragraphs` is a list of (text, size_pt, colour, bold) runs, one per paragraph."""
    paras = []
    for t, size, colour, bold in paragraphs:
        para: dict = {"textRuns": [{"value": t, "textStyle": {
            "fontSize": f"{size}pt", "color": colour, "fontWeight": "bold" if bold else "normal",
            "fontFamily": "Segoe UI"}}]}
        if align:
            para["horizontalTextAlignment"] = align
        paras.append(para)
    return visual(name, box, "textbox", objects={"general": [{"properties": {"paragraphs": paras}}]},
                  frame=frame if frame is not None else container(frame=False, header=False), z=z)


def button(name: str, box: tuple, label: str, target: str, *, active: bool = False,
           size: float = 10.0) -> dict:
    """A page-navigation button: a pill with a label, filled when it is the page on screen."""
    fg, bg, hover = (CARD_BG, RESIDUAL, RESIDUAL) if active else (INK, CARD_BG, RAMP[0])
    # `show` also goes in an entry with no selector: Desktop reads a button's
    # text and fill as on or off from there, and a blank button starts with its
    # text off, so a `show` inside the default state alone leaves the pill empty.
    return visual(name, box, "actionButton",
                  objects={"icon": [state(show=False)],
                           "text": [*obj(show=True),
                                    state(show=True, text=label, fontColor=color(fg), fontSize=size,
                                          bold=active, horizontalAlignment="center")],
                           "fill": [*obj(show=True),
                                    state(show=True, fillColor=color(bg), transparency=0.0),
                                    state("hover", show=True, fillColor=color(hover), transparency=0.0)],
                           "outline": [state(show=True, lineColor=color(RESIDUAL if active else LINE),
                                             weight=1.0)],
                           "shape": obj(tileShape="pill")},
                  frame={**container(frame=False, header=False),
                         "visualLink": obj(show=True, type="PageNavigation", navigationSection=target,
                                           tooltip=f"Go to: {dict(STORY).get(target, target).strip()}")},
                  how="InsertVisualButton")


def nav_bar(page: str) -> list:
    """The same bar on every story page: the kit's name, then one button per page."""
    brand = text(f"{page}_brand", (M, NAV_Y + 4, 176, NAV_H), [("FLOOD POLICY KIT  ·  EU-27", 9, RESIDUAL, True)])
    x0, gap = M + 184, 6
    bw = (CW - 184 - gap * (len(STORY) - 1)) // len(STORY)
    return [brand] + [button(f"{page}_nav_{target}", (x0 + i * (bw + gap), NAV_Y, bw, NAV_H), label, target,
                             active=target == page)
                      for i, (target, label) in enumerate(STORY)]


def header(page: str, title: str, subtitle: str) -> list:
    return nav_bar(page) + [
        text(f"{page}_title", (M, TITLE_Y, CW, 36), [(title, 16, INK, True)]),
        text(f"{page}_subtitle", (M, SUB_Y, CW, 38), [(subtitle, 10.5, MUTED, False)]),
    ]


def footer(page: str, sources: str, credit: bool = False) -> list:
    """The source line every page carries, ending with the boundary credit
    (the regions are GISCO NUTS 2024 on every page, mapped or not)."""
    out = [text(f"{page}_source", (M, FOOT_Y, CW, 28), [(f"Sources: {sources}  ·  {CREDIT}", 8, MUTED, False)])]
    if credit:
        out.append(text(f"{page}_credit", (M + 616, 646, CW - 616, 26), [(CREDIT, 9, MUTED, False)]))
    return out


def card(name: str, box: tuple, field: dict, label: str, *, units: int = 0, decimals: int | None = None,
         value_size: float = 26.0, value_colour: str = INK, show_label: bool = True,
         frame: dict | None = None) -> dict:
    labels = {"color": color(value_colour), "fontSize": value_size, "labelDisplayUnits": float(units)}
    if decimals is not None:
        labels["labelPrecision"] = decimals
    return visual(name, box, "card", roles={"Values": [proj(field, label)]},
                  objects={"labels": obj(**labels),
                           "categoryLabels": obj(show=show_label, color=color(MUTED), fontSize=10.0)},
                  frame=frame)


def rp_slicer(name: str, box: tuple) -> dict:
    """Return period as tiles, one at a time, synced on every page that has one."""
    return visual(name, box, "slicer", roles={"Values": [proj(col("Exposure", "return_period"),
                                                              "Return period", active=True)]},
                  objects={"data": obj(mode="HorizontalList"),
                           "selection": obj(singleSelect=True, strictSingleSelect=False),
                           "header": obj(show=True, text="Return period - 1 in ... years (none = 100)",
                                         fontColor=color(MUTED), textSize=10.0),
                           "items": obj(fontColor=color(INK), textSize=11.0, background=color(CARD_BG))},
                  frame=container(), sync="ReturnPeriod")


def _axes(objects: dict, units: int, decimals: int, label_size: float = 9.0) -> dict:
    """Data labels on, value axis and gridlines off: the label carries the number."""
    objects["labels"] = obj(show=True, color=color(INK), fontSize=label_size,
                            labelDisplayUnits=float(units), labelPrecision=decimals)
    objects["categoryAxis"] = obj(show=True, fontSize=9.0, labelColor=color(INK),
                                  showAxisTitle=False, axisType="Categorical")
    objects["valueAxis"] = obj(show=False, gridlineShow=False)
    return objects


def bars(name: str, box: tuple, kind: str, category: list, value: dict, title: str, subtitle: str,
         *, fill: dict, units: int = 1000000, decimals: int = 1, display: str | None = None,
         tooltips: list | None = None, sort: bool = True, tooltip_page: bool = False) -> dict:
    roles = {"Category": category, "Y": [proj(value, display)]}
    if tooltips:
        roles["Tooltips"] = [proj(t, d) for t, d in tooltips]
    frame = container(title, subtitle)
    if tooltip_page:
        frame.update(region_tooltip())
    return visual(name, box, kind, roles=roles, sort=sort_desc(value) if sort else None,
                  objects=_axes({
                      # A rule-driven colour applies per data point, hence the wildcard selector.
                      "dataPoint": [{"properties": {"fill": fill},
                                     "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}]}}]
                      if "FillRule" in fill["solid"]["color"].get("expr", {}) else obj(fill=fill),
                  }, units, decimals),
                  frame=frame)


def series_chart(name: str, box: tuple, kind: str, category: list | None, series: list, title: str,
                 subtitle: str, *, units: int = 1000000, decimals: int = 1, sort_by: dict | None = None,
                 tooltips: list | None = None, tooltip_page: bool = False, legend: bool = True) -> dict:
    """A chart of several measures side by side or stacked, one colour per measure.

    `series` is a list of (measure, display name, colour). With no category the
    measures stand as bars of their own, which is how a decomposition of one
    total (undefended, held, residual) reads without a table to slice it by.
    """
    roles: dict = {"Y": [proj(f, d) for f, d, _ in series]}
    if category:
        roles = {"Category": category, **roles}
    if tooltips:
        roles["Tooltips"] = [proj(t, d) for t, d in tooltips]
    objects = _axes({"dataPoint": series_colours([(f, c) for f, _, c in series])}, units, decimals)
    if not category:
        objects["categoryAxis"] = obj(show=False)
    objects["legend"] = obj(show=legend, position="Top", fontSize=9.0, labelColor=color(INK),
                            showTitle=False)
    frame = container(title, subtitle)
    if tooltip_page:
        frame.update(region_tooltip())
    return visual(name, box, kind, roles=roles, sort=sort_desc(sort_by) if sort_by else None,
                  objects=objects, frame=frame)


def table(name: str, box: tuple, columns: list, title: str, subtitle: str, sort_by: dict,
          shade: dict | None = None) -> dict:
    objects = {"columnHeaders": obj(fontColor=color(INK), bold=True, fontSize=9.0,
                                    backColor=color(PAGE_BG)),
               "values": obj(fontSize=9.0, fontColorPrimary=color(INK), backColorPrimary=color(CARD_BG),
                             backColorSecondary=color(PAGE_BG)),
               "grid": obj(gridHorizontal=False, gridVertical=False, rowPadding=3.0)}
    if shade:
        objects["values"].append({"properties": {"backColor": gradient(shade, RAMP[0], RAMP[3])},
                                  "selector": {"metadata": ref(shade)}})
    return visual(name, box, "tableEx", roles={"Values": columns}, sort=sort_desc(sort_by),
                  objects=objects, frame=container(title, subtitle))


def matrix(name: str, box: tuple, rows: list, values: list, title: str, subtitle: str,
           sort_by: dict, shade: dict | None = None) -> dict:
    """A matrix whose rows are a hierarchy, with the expand/collapse buttons shown.

    The plainest drill-down Power BI has: a +/- beside every country or basin,
    always visible, where a bar chart's drill arrows only appear on hover and
    were missed. Stepped layout keeps the regions indented under their parent.
    """
    objects = {"rowHeaders": obj(showExpandCollapseButtons=True, fontSize=9.0, fontColor=color(INK),
                                 expandCollapseButtonsColor=color(EXPOSURE), stepped=True),
               "columnHeaders": obj(fontColor=color(INK), bold=True, fontSize=9.0,
                                    backColor=color(PAGE_BG)),
               "values": obj(fontSize=9.0, fontColorPrimary=color(INK), backColorPrimary=color(CARD_BG),
                             backColorSecondary=color(PAGE_BG)),
               "grid": obj(gridHorizontal=False, gridVertical=False, rowPadding=3.0)}
    if shade:
        objects["values"].append({"properties": {"backColor": gradient(shade, RAMP[0], RAMP[3])},
                                  "selector": {"metadata": ref(shade)}})
    return visual(name, box, "pivotTable", roles={"Rows": rows, "Values": values},
                  sort=sort_desc(sort_by), objects=objects, frame=container(title, subtitle))


def decomposition(name: str, box: tuple, analyze: tuple, explain: list, title: str, subtitle: str,
                  colour: str) -> dict:
    """A decomposition tree: one total, split level by level in the order the
    reader picks with the + on each bar. No expansion is stored, so it opens on
    the total alone and every split is the reader's own click."""
    return visual(name, box, "decompositionTreeVisual",
                  roles={"Analyze": [proj(measure(analyze[0]), analyze[1])],
                         "ExplainBy": [proj(f, d) for f, d in explain]},
                  objects={"tree": obj(accentColor=color(colour), connectorDefaultColor=color(LINE)),
                           "dataBars": obj(positiveBarColor=color(colour), dataBarBackgroundColor=color(PAGE_BG)),
                           "dataLabels": obj(dataLabelFontColor=color(INK), dataLabelFontSize=9.0,
                                             dataLabelDisplayUnits=1000000.0, dataLabelPrecision=2),
                           "categoryLabels": obj(categoryLabelFontColor=color(INK), categoryLabelFontSize=9.0),
                           "levelHeader": obj(levelTitleFontColor=color(INK), levelSubtitleFontColor=color(MUTED))},
                  frame=container(title, subtitle))


def scatter(name: str, box: tuple, x: tuple, y: tuple, title: str, subtitle: str, colour: str) -> dict:
    return visual(name, box, "scatterChart",
                  roles={"Category": [proj(col("Regions", "region"), "Region")],
                         "X": [proj(measure(x[0]), x[1])],
                         "Y": [proj(measure(y[0]), y[1])],
                         "Size": [proj(measure("Exposed population"), "People exposed")]},
                  objects={"dataPoint": obj(defaultColor=color(colour)),
                           "bubbles": obj(bubbleSize=-10.0),
                           "categoryAxis": obj(show=True, showAxisTitle=True, fontSize=9.0,
                                               gridlineShow=False),
                           "valueAxis": obj(show=True, showAxisTitle=True, fontSize=9.0,
                                            gridlineShow=True, gridlineColor=color(LINE))},
                  frame={**container(title, subtitle), **region_tooltip()})


# --- pages --------------------------------------------------------------------

def eu27_filter(page: str) -> dict:
    """The brief quotes the EU-27: a page filter, visible and changeable in the Filters pane."""
    return {"filters": [{
        "name": f"{page}_eu27",
        "field": col("Regions", "is_eu27"),
        "type": "Categorical",
        "filter": {"Version": 2,
                   "From": [{"Name": "r", "Entity": "Regions", "Type": 0}],
                   "Where": [{"Condition": {"In": {
                       "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "r"}},
                                                   "Property": "is_eu27"}}],
                       "Values": [[{"Literal": {"Value": "true"}}]]}}}]},
        "howCreated": "User",
    }]}


def page_json(name: str, display: str, **extra) -> dict:
    return {"$schema": f"{SCHEMA}/page/{VERSIONS['page']}/schema.json",
            "name": name, "displayName": display, "displayOption": "FitToPage",
            "height": H, "width": W, **extra}


def columns(n: int, top: int, height: int, width: int = CW, x0: int = M) -> list:
    """`n` equal boxes side by side on the grid, gutter between them."""
    w = (width - (n - 1) * G) // n
    return [(x0 + i * (w + G), top, w, height) for i in range(n)]


def overview() -> tuple[dict, list]:
    """The cover: six findings as tiles, each with the button to its page."""
    p = "overview"
    visuals = nav_bar(p) + [
        text(f"{p}_title", (M, TITLE_Y - 6, CW, 42), [("Europe's flood exposure at a glance", 24, INK, True)]),
        text(f"{p}_subtitle", (M, SUB_Y + 2, CW, 34), [(
            "EU-27, the 1-in-100-year river flood. Six findings from the JRC hazard maps laid over where people "
            "live - each tile opens the page behind it.", 10.5, MUTED, False)]),
    ]
    tiles = [
        (measure("Exposed population"), 1000000, 1, EXPOSURE, "headline",
         "people live where the 1-in-100 river flood reaches",
         "5.8 % of EU-27 residents - if no dyke held (JRC undefended maps)"),
        (measure("Residual exposed"), 1000000, 2, RESIDUAL, "defences",
         "still do, behind the design standards of local defences",
         "Defences hold 99 % in NL, HU, AT and BE - 26 % in Poland, 24 % in Romania, 12 % in Spain"),
        (measure("Residual expected annual exposure"), 1, 0, RESIDUAL, "defences",
         "people a year behind the defences, weighted by probability - a lower bound",
         "The JRC's own estimate is about 160,000 a year: the same order, reached the other way round"),
        (measure("Share in shared basins"), 0, 1, ACCENT, "downstream",
         "of the exposed live in a river basin shared with another country",
         "Whoever lives downstream depends on a neighbour's plan as much as on their own"),
        (measure("Built-up added since 2010 (km²)"), 1, 0, EXPOSURE, "at_stake",
         "km² more built in the 1-in-100 floodplain since 2010",
         "+14.5 % from 2010 to 2025 (GHSL) - the pace of building everywhere else"),
        (measure("Footprint: farmland"), 0, 0, EXPOSURE, "at_stake",
         "of the land the flood reaches is farmland - room the river can take",
         "But 5,400 km² are homes and 2,000 km² industry and commerce (CORINE 2018)"),
    ]
    pages = dict(STORY)
    th = 176
    boxes = columns(3, TOP, th) + columns(3, TOP + th + G, th)
    for i, ((field, units, decimals, colour, target, label, context), (x, y, w, h)) in enumerate(zip(tiles, boxes)):
        visuals += [
            text(f"{p}_tile{i}", (x, y, w, h), [(label, 11, INK, True), (context, 9.5, MUTED, False)],
                 frame=container(pad_top=68.0, header=False), align="center"),
            card(f"{p}_tile{i}_value", (x + 12, y + 8, w - 24, 62), field, label, units=units,
                 decimals=decimals, value_size=30.0, value_colour=colour, show_label=False,
                 frame=container(frame=False, header=False)),
            button(f"{p}_tile{i}_open", (x + w - 168, y + h - 34, 156, 26),
                   f"Page {pages[target].replace('  ', ' · ')} →", target, size=9.0),
        ]
    low = TOP + 2 * (th + G)
    left, right = columns(2, low, BOTTOM - low)
    visuals += [
        series_chart(f"{p}_held", left, "clusteredBarChart", None, [
            (measure("Exposed population"), "No defences", RAMP[3]),
            (measure("Held by defences (people)"), "Held by the design standards", HELD),
            (measure("Residual exposed"), "Still exposed behind them", RESIDUAL)],
            "From 25.7 million to 7.3 million: what the defences hold",
            "People in the 1-in-100 footprint, EU-27 - most dykes are built for 50 to 100 years",
            decimals=2),
        text(f"{p}_more", right, [
            ("Also behind the pages", 12, INK, True),
            ("Liège: the floodplain is 47 % sealed, against 14 % for the arrondissement around it (page 5).",
             9.5, INK, False),
            ("July 2021: the Ahr at Ahrweiler passed its 1-in-500-year discharge; 44 of its 55 river cells went "
             "past 1-in-100 in the EFAS reanalysis (page 5).", 9.5, INK, False),
            ("Declared risk areas are not comparable: the median Belgian NUTS3 region declares 99.99 % of its area, "
             "the median Spanish one 0.004 %; Ireland is in no cycle of the EEA layer, "
             "Lithuania only in the 2010 one (page 7).", 9.5, INK, False),
            ("How to explore: " + EXPLORE + " The arrows on a chart open a country into its regions.",
             9, MUTED, False),
        ], frame=container()),
    ]
    visuals += footer(p, "JRC river-flood hazard maps and PESETA IV protection standards, GHSL population and "
                         "built-up, CORINE 2018, CLMS imperviousness 2018, EFAS reanalysis, EEA declared risk "
                         "areas, WFD river basin districts")
    return page_json(p, "Overview", filterConfig=eu27_filter(p)), visuals


def headline() -> tuple[dict, list]:
    p = "headline"
    visuals = header(p, "25.7 million people in the EU-27 live where a 1-in-100-year river flood reaches",
                     "What to look at: the four figures, then how the footprint grows from the 1-in-10 to "
                     "the 1-in-500 flood. Pick a return period above; none picked means 1-in-100.")
    cards = columns(4, TOP + 76, 108)
    visuals += [
        rp_slicer(f"{p}_rp", (M, TOP, 824, 60)),
        card(f"{p}_rp_label", (M + 840, TOP, CW - 840, 60), measure("Return period label"),
             "Figures shown for", value_size=14.0),
        card(f"{p}_exposed", cards[0], measure("Exposed population"), "People exposed",
             units=1000000, decimals=1, value_colour=EXPOSURE),
        card(f"{p}_share", cards[1], measure("Share exposed"), "Share of residents exposed"),
        card(f"{p}_shared", cards[2], measure("Share in shared basins"),
             "Of them, in a basin shared with another country", value_colour=ACCENT),
        card(f"{p}_eae", cards[3], measure("Expected annual exposure"),
             "Expected annual exposure (people a year, lower bound)", units=1000000, decimals=2),
        bars(f"{p}_by_rp", (M, TOP + 200, 808, BOTTOM - TOP - 200), "clusteredColumnChart",
             [proj(col("Exposure", "return_period"), "Return period (1 in ... years)")],
             measure("Exposed population"),
             "People in the flood footprint, by return period",
             "Each footprint contains the smaller ones: read the bars one at a time, never add them up",
             fill=gradient(measure("Exposed population"), RAMP[2], RAMP[5]), display="People exposed",
             sort=False),
        text(f"{p}_undefended", (M + 824, TOP + 200, CW - 824, BOTTOM - TOP - 200), [
            ("These are undefended figures", 13, INK, True),
            ("The JRC hazard maps model no dykes, walls or retention: they show where a river "
             "flood would go, not where defences let it go today - page 2 takes the defences out.", 10, INK, False),
            ("The JRC's own headline, about 160,000 people a year, is defended and weighted by "
             "probability. It answers a different question; it does not contradict this one.",
             10, INK, False),
            ("Expected annual exposure weights the nine return periods by their probability over "
             "the sampled band, 1-in-10 to 1-in-500. A lower bound, never an expected damage.",
             10, INK, False),
            ("EU-27 only: a page filter. Clear it in the Filters pane to see all 37 countries.",
             10, MUTED, False),
        ], frame=container()),
    ]
    visuals += footer(p, "JRC river-flood hazard maps (undefended), GHSL population, GISCO NUTS 2024")
    interactions = [{"source": f"{p}_rp", "target": f"{p}_by_rp", "type": "NoFilter"}]
    return page_json(p, "1. Headline", filterConfig=eu27_filter(p), visualInteractions=interactions), visuals


def defences() -> tuple[dict, list]:
    p = "defences"
    visuals = header(p, "Behind the dykes, 7.3 million still live where the 1-in-100 flood reaches",
                     "What to look at: undefended against residual by return period - most defences are built "
                     "for 50 to 100 years, so the rarer flood overtops them. Then which countries hold, and "
                     "where the 7.3 million sit.")
    cards = columns(5, TOP + 76, 100)
    charts = columns(3, TOP + 192, BOTTOM - TOP - 192)
    visuals += [
        rp_slicer(f"{p}_rp", (M, TOP, 824, 60)),
        card(f"{p}_held", (M + 840, TOP, CW - 840, 60), measure("Held by defences"),
             "Share held by the design standards", value_size=18.0, value_colour=ACCENT),
        card(f"{p}_undefended", cards[0], measure("Exposed population"),
             "People exposed, no defences", units=1000000, decimals=1),
        card(f"{p}_residual", cards[1], measure("Residual exposed"),
             "Still exposed behind the defences", units=1000000, decimals=2, value_colour=RESIDUAL),
        card(f"{p}_residual_eae", cards[2], measure("Residual expected annual exposure"),
             "A year behind the defences, lower bound (JRC: ~160,000)", units=1, value_colour=RESIDUAL),
        card(f"{p}_hospitals", cards[3], measure("Hospitals behind defences"),
             "Hospitals still in the RP100 footprint"),
        card(f"{p}_schools", cards[4], measure("Schools behind defences"),
             "Schools still in the RP100 footprint"),
        series_chart(f"{p}_by_rp", charts[0], "clusteredColumnChart",
                     [proj(col("Exposure", "return_period"), "Return period (1 in ... years)")],
                     [(measure("Exposed population"), "No defences", RAMP[3]),
                      (measure("Residual exposed"), "Behind the defences", RESIDUAL)],
                     "Undefended against residual, by return period",
                     "The gap is what the dykes hold; it closes for the rare floods"),
        bars(f"{p}_held_by_country", charts[1], "clusteredBarChart",
             [proj(level("Country"), active=True), proj(level("Region"), active=False)],
             measure("Held by defences"),
             "Share held by the defences, by country",
             "99 % in the Netherlands, Hungary, Austria, Belgium - 26 % Poland, 24 % Romania, 12 % Spain",
             fill=gradient(measure("Held by defences")), units=1, decimals=0, display="Share held",
             tooltips=[(measure("Residual exposed"), "Still exposed"),
                       (measure("Exposed population"), "People exposed, no defences")],
             tooltip_page=True),
        series_chart(f"{p}_by_country", charts[2], "barChart",
                     [proj(level("Country"), active=True), proj(level("Region"), active=False)],
                     [(measure("Residual exposed"), "Still exposed", RESIDUAL),
                      (measure("Held by defences (people)"), "Held by the design standards", HELD)],
                     "Where the 7.3 million sit - drill down to regions",
                     "Bar length: people exposed with no defences; dark: still exposed behind them",
                     sort_by=measure("Residual exposed"),
                     tooltips=[(measure("Held by defences"), "Share held")], tooltip_page=True),
    ]
    visuals += footer(p, "JRC river-flood hazard maps, JRC PESETA IV flood protection standards, GHSL "
                         "population, GISCO healthcare and education sites")
    return page_json(p, "2. Behind the defences", filterConfig=eu27_filter(p)), visuals


def where() -> tuple[dict, list]:
    p = "where"
    visuals = header(p, "Four countries hold three in five of the EU's exposed - the highest shares are elsewhere",
                     "What to look at: bars rank countries by people exposed and are coloured by the share "
                     "exposed. Drill down (arrow icons on the chart) to open a country into its regions; "
                     "the table sorts on any column.")
    visuals += [
        rp_slicer(f"{p}_rp", (M, TOP, 600, 60)),
        bars(f"{p}_by_country", (M, TOP + 76, 600, BOTTOM - TOP - 76), "clusteredBarChart",
             [proj(level("Country"), active=True), proj(level("Region"), active=False)],
             measure("Exposed population"),
             "People exposed, by country - drill down to regions",
             "Bar length: people. Colour: share of residents, light to dark.",
             fill=gradient(measure("Share exposed")), display="People exposed",
             tooltips=[(measure("Share exposed"), "Share exposed"), (measure("Population"), "Residents"),
                       (measure("Regions measured"), "Regions")],
             tooltip_page=True),
        matrix(f"{p}_regions", (M + 616, TOP, CW - 616, 368),
               [proj(level("Country"), "Country"), proj(level("Region"), "Region")],
               [proj(measure("Exposed population"), "People exposed"),
                proj(measure("Share exposed"), "Share exposed"),
                proj(measure("Population"), "Residents")],
               "Countries - click + to open a country into its regions",
               "Click a column header to sort; right-click a region > Drill through for its detail page",
               sort_by=measure("Exposed population"), shade=measure("Share exposed")),
        text(f"{p}_map_note", (M + 616, TOP + 384, CW - 616, 130), [
            ("Map to add by hand: Shape map", 11, INK, True),
            ("Insert a Shape map here. Location: Regions > nuts_id. Colour saturation: Share exposed. "
             "Format > Map settings > Custom map > bi/data/regions.topojson. Then delete this note. "
             "Not generated because the Shape map stores the TopoJSON inside the report, and the "
             "boundaries are not committed (GISCO terms). See docs/power_bi.md.", 9, MUTED, False),
        ], frame=container()),
    ]
    visuals += footer(p, "JRC river-flood hazard maps (undefended), GHSL population, GISCO NUTS 2024",
                      credit=True)
    return page_json(p, "3. Where", filterConfig=eu27_filter(p)), visuals


def downstream() -> tuple[dict, list]:
    p = "downstream"
    x0 = M + 416
    cards = columns(3, TOP, 84, width=CW - 416, x0=x0)
    low = TOP + 100
    visuals = header(p, "Nearly two in three of the EU's exposed live in a river basin shared with another country",
                     "What to look at: which basins carry them. Open the tree basin by basin; the table names "
                     "the partner countries. A floor: Switzerland, Serbia, Ukraine and Belarus do not report "
                     "basins under EU law.")
    visuals += [
        rp_slicer(f"{p}_rp", (M, TOP, 400, 84)),
        card(f"{p}_exposed", cards[0], measure("Exposed in shared basins"),
             "People exposed in a shared basin", units=1000000, decimals=1, value_colour=ACCENT),
        card(f"{p}_share", cards[1], measure("Share in shared basins"),
             "Share of all the exposed", value_colour=ACCENT),
        card(f"{p}_regions", cards[2], measure("Regions in shared basins"),
             "Regions with area in a shared basin"),
        bars(f"{p}_by_basin", (M, low, 400, BOTTOM - low), "clusteredBarChart",
             [proj(col("Regions", "main_shared_basin"), "Basin", active=True),
              proj(col("Regions", "region"), "Region", active=False)],
             measure("Exposed in shared basins"),
             "People exposed in a cross-border basin",
             "By the shared basin that covers most of each region - drill down to regions",
             fill=color(ACCENT), display="People exposed",
             tooltips=[(measure("Share exposed"), "Share exposed")], tooltip_page=True),
        decomposition(f"{p}_tree", (M + 416, low, 416, BOTTOM - low),
                      ("Exposed in shared basins", "People exposed in a shared basin"),
                      [(col("Regions", "main_shared_basin"), "Basin"),
                       (col("Regions", "country_name"), "Country"),
                       (col("Regions", "region"), "Region")],
                      "Split it yourself: basin, country, region",
                      "Click + on a bar and pick the next split; the order is yours", ACCENT),
        matrix(f"{p}_partners", (M + 848, low, CW - 848, BOTTOM - low),
               [proj(col("Regions", "main_shared_basin"), "Basin"), proj(col("Regions", "region"), "Region")],
               [proj(measure("Exposed in shared basins"), "People exposed"),
                proj(measure("Partner countries"), "Shares its rivers with")],
               "Basins - click + to open a basin",
               "Partner countries are ISO codes, shown once a region is open",
               sort_by=measure("Exposed in shared basins")),
    ]
    visuals += footer(p, "JRC river-flood hazard maps (undefended), GHSL population, WFD river basin "
                         "districts (EEA)")
    return page_json(p, "4. Downstream of someone else", filterConfig=eu27_filter(p)), visuals


def at_stake() -> tuple[dict, list]:
    p = "at_stake"
    cards = columns(5, TOP, 100)
    charts = columns(3, TOP + 116, BOTTOM - TOP - 116)
    visuals = header(p, "What the water covers - and 423 km² more built in the floodplain since 2010",
                     "What to look at: the land under the 1-in-100 footprint (CORINE 2018), where the floodplain "
                     "is sealed more densely than the region around it (CLMS 2018), and July 2021 measured "
                     "against the EFAS reanalysis.")
    visuals += [
        card(f"{p}_added", cards[0], measure("Built-up added since 2010 (km²)"),
             "Built-up added in the footprint since 2010, km²", value_colour=EXPOSURE),
        card(f"{p}_growth", cards[1], measure("Built-up growth since 2010"),
             "Growth of the built-up footprint, 2010-2025", value_colour=EXPOSURE),
        card(f"{p}_homes", cards[2], measure("Footprint under homes (km²)"),
             "Footprint under homes, km²"),
        card(f"{p}_industry", cards[3], measure("Footprint under industry (km²)"),
             "Under industry and commerce, km²"),
        card(f"{p}_area", cards[4], measure("Footprint area (km²)"),
             "Footprint area, km² (CORINE)"),
        series_chart(f"{p}_landcover", charts[0], "clusteredBarChart", None, [
            (measure("Footprint: farmland"), "Farmland", RAMP[3]),
            (measure("Footprint: natural land"), "Natural land", RAMP[2]),
            (measure("Footprint: homes"), "Homes", RESIDUAL),
            (measure("Footprint: water"), "Water", RAMP[1]),
            (measure("Footprint: industry and commerce"), "Industry and commerce", EXPOSURE),
            (measure("Footprint: other artificial"), "Other artificial", NEUTRAL),
            (measure("Footprint: transport"), "Transport", MUTED)],
            "What the 1-in-100 footprint covers",
            "Share of the footprint's area by land use - farmland is room the river can take",
            units=1, decimals=1),
        table(f"{p}_sealed", charts[1],
              [proj(col("Regions", "region"), "Region"),
               proj(measure("Footprint sealed share"), "Floodplain sealed"),
               proj(measure("Region sealed share"), "Whole region"),
               proj(measure("Floodplain sealed above region"), "Gap, points")],
              "Where the floodplain is sealed more than its region",
              "Liège: 47 % against 14 %. Small footprints rank high; read the gap with the region's size",
              sort_by=measure("Floodplain sealed above region"),
              shade=measure("Floodplain sealed above region")),
        table(f"{p}_july2021", charts[2],
              [proj(col("Regions", "region"), "Region"),
               proj(col("Regions", "efas_2021_max_rp_exceeded"), "Highest level passed (1 in ... yr)"),
               proj(col("Regions", "efas_2021_cells_over_rp100"), "Cells past 1-in-100"),
               proj(col("Regions", "efas_2021_river_cells"), "River cells")],
              "July 2021 in the EFAS reanalysis",
              "Ahrweiler: past 1-in-500, 44 of 55 cells past 1-in-100. Thresholds fitted on 1992-2022: a lower bound",
              sort_by=col("Regions", "efas_2021_cells_over_rp100")),
    ]
    visuals += footer(p, "CORINE Land Cover 2018, GHSL built-up 2010 and 2025, CLMS imperviousness 2018, "
                         "EFAS historical reanalysis (Meuse, Vesdre, Ahr box)")
    return page_json(p, "5. What is at stake", filterConfig=eu27_filter(p)), visuals


def who() -> tuple[dict, list]:
    p = "who"
    half = (CW - G) // 2
    height = BOTTOM - TOP - 72
    visuals = header(p, "Older and poorer regions are not more exposed - the link is weak, and if anything the other way",
                     "What to look at: the cloud has no upward slope. Each dot is a region, sized by the "
                     "people exposed; hover for its card, right-click to drill through to it.")
    visuals += [
        scatter(f"{p}_age", (M, TOP, half, height), ("Share over 65", "Residents aged 65+"),
                ("Share exposed", "Share of residents exposed"),
                "Share exposed against the share of residents aged 65 or over",
                "One dot per region, EU-27", EXPOSURE),
        scatter(f"{p}_poverty", (M + half + G, TOP, half, height), ("Poverty rate", "At-risk-of-poverty rate"),
                ("Share exposed", "Share of residents exposed"),
                "Share exposed against the at-risk-of-poverty rate",
                "One dot per region, EU-27; regions without a poverty figure are left out", EXPOSURE),
        text(f"{p}_caption", (M, TOP + height + 8, CW, 60), [
            ("How to read it: these are regional averages. A region's over-65 share or poverty rate says "
             "nothing about who, inside the region, lives in the footprint - that would need the "
             "population grid by age and income, which the kit does not have. So this page can rule out "
             "a strong regional pattern; it cannot say the exposed are younger or richer.", 9, MUTED, False),
        ]),
    ]
    visuals += footer(p, "JRC river-flood hazard maps, GHSL population, Eurostat age structure and "
                         "at-risk-of-poverty rate (NUTS2, ilc_li41)")
    return page_json(p, "6. Who is exposed", filterConfig=eu27_filter(p)), visuals


def declared() -> tuple[dict, list]:
    p = "declared"
    height = BOTTOM - TOP - 72
    visuals = header(p, "Declared areas do not follow exposure: Belgium declares almost all its land, Germany and Spain almost none",
                     "What to look at: the median region's declared share of area, by country, against the "
                     "share exposed. Mapping conventions differ, so countries do not rank.")
    visuals += [
        bars(f"{p}_by_country", (M, TOP, 600, height), "clusteredBarChart",
             [proj(level("Country"), active=True), proj(level("Region"), active=False)],
             measure("Median declared share"),
             "Declared share of area, median region - drill down to regions",
             "Blank is 'not reported' (Ireland, Lithuania), not zero",
             fill=gradient(measure("Median declared share")), units=1, display="Median declared share",
             tooltips=[(measure("Share exposed"), "Share exposed"),
                       (measure("Regions with a declared risk area"), "Regions with a declared area")],
             tooltip_page=True),
        scatter(f"{p}_scatter", (M + 616, TOP, CW - 616, height),
                ("Declared share of area", "Declared share of the region's area"),
                ("Share exposed", "Share of residents exposed"),
                "Each region: declared share against share exposed",
                "No slope: what is declared does not track who is exposed", EXPOSURE),
        text(f"{p}_caption", (M, TOP + height + 8, CW, 60), [
            ("Read with care: Germany reports river reaches as thin ribbons, Belgium whole zones, so a low "
             "share is a reporting style, not a safe region. No Member State is accused of under-declaring: "
             "the Directive lets a State assess an area and find the risk not significant. "
             "(EEA layer, 2018 cycle.)", 9, MUTED, False),
        ]),
    ]
    visuals += footer(p, "EEA Floods Directive Art. 5 areas (2018 cycle), JRC river-flood hazard maps, "
                         "GHSL population")
    return page_json(p, "7. Declared vs exposed", filterConfig=eu27_filter(p)), visuals


def rivers() -> tuple[dict, list]:
    """HERA 1991-2020: whether river peaks grow, move in the year, or come more often.

    The title states what the 30 years show; on a checkout without the HERA
    layer the figures are blank, which the caption says rather than showing
    zeros.
    """
    p = "rivers"
    cards = columns(5, TOP, 100)
    low = TOP + 116
    height = BOTTOM - low - 64
    visuals = header(p, "1991-2020: river peaks did not grow in most EU regions - they came later in the year",
                     "What to look at: the peak trend by country, then winter against summer - a region whose "
                     "flood season moves needs a different warning calendar even when the peaks stay the same size.")
    visuals += [
        card(f"{p}_trend", cards[0], measure("River peak trend per decade"),
             "Annual peak, % per decade (median region)", decimals=1, value_colour=EXPOSURE),
        card(f"{p}_rising", cards[1], measure("River cells with rising peaks"),
             "River cells with a significant rise"),
        card(f"{p}_winter", cards[2], measure("Winter peak share"),
             "Years peaking in October-March (median region)"),
        card(f"{p}_timing", cards[3], measure("Peak timing shift per decade"),
             "Peak date shift, days per decade (+ = later)", decimals=1),
        card(f"{p}_days", cards[4], measure("Flood days trend per decade"),
             "Days above bankfull, change per decade", decimals=1, value_colour=RESIDUAL),
        series_chart(f"{p}_seasons", (M, low, 600, height), "clusteredBarChart",
                     [proj(level("Country"), active=True), proj(level("Region"), active=False)],
                     [(measure("Winter peak trend per decade"), "Winter peak, % per decade", RAMP[3]),
                      (measure("Summer peak trend per decade"), "Summer peak, % per decade", RESIDUAL)],
                     "Winter against summer peaks, by country - drill down to regions",
                     "Median region; a bar left of zero is a peak that is shrinking",
                     units=1, decimals=1, sort_by=measure("Winter peak trend per decade"),
                     tooltip_page=True),
        matrix(f"{p}_regions", (M + 616, low, CW - 616, height),
               [proj(level("Country"), "Country"), proj(level("Region"), "Region")],
               [proj(measure("River peak trend per decade"), "Peak, %/decade"),
                proj(measure("River cells with rising peaks"), "Cells rising"),
                proj(measure("Winter peak share"), "Winter peaks"),
                proj(measure("Peak timing shift per decade"), "Timing, days/decade"),
                proj(measure("Flood days per year"), "Flood days/yr"),
                proj(measure("Flood days trend per decade"), "Flood days, /decade")],
               "Countries - click + to open a country into its regions",
               "Medians over each region's river cells (mean flow >= 1 m³/s)",
               sort_by=measure("River peak trend per decade"),
               shade=measure("River peak trend per decade")),
        text(f"{p}_caption", (M, low + height + 8, CW, 56), [
            ("How to read it: HERA is a model forced by a reanalysis, not gauged flow, and 30 years of floods "
             "carry the years that happen to be in them. Flood days count against the EFAS 1-in-2-year flow, "
             "fitted on another model run: read them as a trend, not a count. Blank means the HERA layer has "
             "not been computed on this machine, never zero.", 9, MUTED, False),
        ]),
    ]
    visuals += footer(p, "JRC HERA v2 river discharge reanalysis 1991-2020, EFAS v5.1 return levels")
    return page_json(p, "8. Rivers changing", filterConfig=eu27_filter(p)), visuals


def detail(level: str = "region") -> tuple[dict, list]:
    """The drillthrough page for one region, or for one country.

    Drill through is offered only where the source visual carries the bound
    column, so a bar at the Country level of `Geography` needs a page bound to
    `country_name`: without it the country bars of pages 2, 3, 7 and 8 offer
    nothing until drilled down. The country page swaps the region-only profile
    (NUTS3 code, declared share of one region, its basin partners) for figures
    that read over several regions.
    """
    p = f"{level}_detail"
    filter_name = f"{p}_drillthrough"
    title = f"{level.capitalize()} detail"
    cards = columns(5, 136, 96)
    visuals = [
        visual(f"{p}_back", (M, 18, 40, 40), "actionButton",
               objects={"icon": [{"properties": {"shapeType": lit("back"), "lineColor": color(INK)},
                                  "selector": {"id": "default"}}]},
               frame={**container(frame=False, header=False),
                      "visualLink": obj(show=True, type="Back", tooltip="Back to the page you came from")},
               how="InsertVisualButton"),
        text(f"{p}_title", (M + 52, 14, CW - 52, 44), [(title, 20, INK, True)]),
        card(f"{p}_name", (M + 52, 54, CW - 52, 44),
             measure("Region shown" if level == "region" else "Place shown"), level.capitalize(),
             value_size=14.0),
        text(f"{p}_subtitle", (M, 100, CW, 30), [(
            "What to look at: how fast the footprint grows as floods get rarer, and the profile beside it. "
            "The five figures are at 1-in-100" + ("." if level == "region" else ", for all of the country's regions."),
            11, MUTED, False)]),
        card(f"{p}_exposed", cards[0], measure("Exposed population"), "People exposed (1-in-100)",
             value_colour=EXPOSURE),
        card(f"{p}_residual", cards[1], measure("Residual exposed"), "Still exposed behind the defences",
             value_colour=RESIDUAL),
        card(f"{p}_share", cards[2], measure("Share exposed"), "Share of residents exposed"),
        card(f"{p}_pop", cards[3], measure("Population"), "Residents"),
        card(f"{p}_eae", cards[4], measure("Expected annual exposure"),
             "Expected annual exposure (lower bound)"),
        series_chart(f"{p}_by_rp", (M, 248, 608, 428), "clusteredColumnChart",
                     [proj(col("Exposure", "return_period"), "Return period (1 in ... years)")],
                     [(measure("Exposed population"), "No defences", RAMP[3]),
                      (measure("Residual exposed"), "Behind the defences", RESIDUAL)],
                     "People in the footprint, by return period",
                     "Nested footprints: never add the bars", units=0, decimals=0),
        visual(f"{p}_profile", (M + 624, 248, CW - 624, 206), "multiRowCard",
               roles={"Values": [proj(col("Regions", "nuts_id"), "NUTS3 code"),
                                 proj(col("Regions", "country_name"), "Country"),
                                 proj(measure("Share over 65"), "Residents aged 65+"),
                                 proj(measure("Poverty rate"), "At-risk-of-poverty rate"),
                                 proj(measure("Declared share of area"), "Declared risk area, share of area"),
                                 proj(col("Regions", "main_shared_basin"), "Main shared basin"),
                                 proj(col("Regions", "shared_with"), "Shares a basin with")]
                      if level == "region" else
                      [proj(measure("Regions measured"), "NUTS3 regions"),
                       proj(measure("Share over 65"), "Residents aged 65+"),
                       proj(measure("Poverty rate"), "At-risk-of-poverty rate"),
                       proj(measure("Median declared share"), "Declared risk area, median region"),
                       proj(measure("Share in shared basins"), "Exposed in a shared basin"),
                       proj(measure("Held by defences"), "Held by the design standards")]},
               frame=container("Profile", "Regional figures, not figures for the exposed" if level == "region"
                               else "Population-weighted over the country's regions, not figures for the exposed")),
        visual(f"{p}_climate", (M + 624, 470, CW - 624, 206), "multiRowCard",
               roles={"Values": [
                   proj(measure("Median change in discharge 2041-2070"), "Median change, %"),
                   proj(measure("Lower quartile change in discharge 2041-2070"), "Lower quartile, %"),
                   proj(measure("Upper quartile change in discharge 2041-2070"), "Upper quartile, %"),
                   proj(measure("Simulations agree on direction 2041-2070"), "80 % of simulations agree on direction")]},
               frame=container("Climate: change in reference discharge, 2041-2070",
                               "Ensemble of 16 members (eight bias-adjusted simulations, two hydrological "
                               "models): median and quartiles, never a mean")),
    ]
    visuals += footer(p, "JRC river-flood hazard maps and PESETA IV protection standards, GHSL population, "
                         "Eurostat, EEA declared risk areas, WFD basins, climate-change discharge ensemble")
    bound = col("Regions", "region" if level == "region" else "country_name")
    page = page_json(
        p, title, type="Drillthrough", visibility="HiddenInViewMode",
        filterConfig={"filters": [{"name": filter_name, "field": bound, "type": "Categorical",
                                   "howCreated": "Drillthrough"}]},
        pageBinding={"name": str(uuid.uuid5(uuid.NAMESPACE_URL, f"flood-policy-kit/{p}")),
                     "type": "Drillthrough", "referenceScope": "Default",
                     "acceptsFilterContext": "None",
                     "parameters": [{"name": str(uuid.uuid5(uuid.NAMESPACE_URL,
                                                            f"flood-policy-kit/{p}/{level}")),
                                     "boundFilter": filter_name, "fieldExpr": bound}]},
    )
    return page, visuals


def country_detail() -> tuple[dict, list]:
    """The drillthrough page for one country; see `detail`."""
    return detail("country")


def tooltip() -> tuple[dict, list]:
    """The card a hovered bar or dot shows: the place, then four figures.

    A Tooltip page takes the hovered point's filters (a country, a region, a
    basin) on top of the source page's, so the same small page serves every
    chart it is wired to; `Place shown` says which level it landed on.
    """
    p = TOOLTIP_PAGE
    pad = 8
    half = (TIP_W - 3 * pad) // 2
    small = {"value_size": 15.0}
    visuals = [
        card(f"{p}_place", (pad, 4, TIP_W - 2 * pad, 40), measure("Place shown"), "Place",
             value_size=12.0, value_colour=RESIDUAL, show_label=False, frame=container(frame=False, header=False)),
        card(f"{p}_exposed", (pad, 48, half, 78), measure("Exposed population"), "People exposed, no defences",
             value_colour=EXPOSURE, **small),
        card(f"{p}_share", (2 * pad + half, 48, half, 78), measure("Share exposed"), "Share of residents", **small),
        card(f"{p}_residual", (pad, 134, half, 78), measure("Residual exposed"), "Behind the defences",
             value_colour=RESIDUAL, **small),
        card(f"{p}_held", (2 * pad + half, 134, half, 78), measure("Held by defences"), "Held by the defences",
             value_colour=ACCENT, **small),
        text(f"{p}_hint", (pad, 214, TIP_W - 2 * pad, 24),
             [("Return period as picked on the page. Right-click a region > Drill through for more.",
               7, MUTED, False)]),
    ]
    page = page_json(p, "Tooltip: place", type="Tooltip", visibility="HiddenInViewMode",
                     pageBinding={"name": str(uuid.uuid5(uuid.NAMESPACE_URL, "flood-policy-kit/region_tooltip")),
                                  "type": "Tooltip", "referenceScope": "Default"})
    page.update(height=TIP_H, width=TIP_W)
    return page, visuals


PAGES = (overview, headline, defences, where, downstream, at_stake, who, declared, rivers, detail, country_detail,
         tooltip)


# --- theme and report ---------------------------------------------------------

def theme() -> dict:
    """The custom theme: page and card colours, the BuPu ramp, Segoe UI throughout."""
    return {
        "name": "FloodPolicyKit",
        "dataColors": [EXPOSURE, RESIDUAL, RAMP[2], RAMP[3], ACCENT, NEUTRAL, MUTED, RAMP[1]],
        "foreground": INK, "foregroundNeutralSecondary": MUTED, "foregroundNeutralTertiary": NEUTRAL,
        "background": CARD_BG, "backgroundLight": PAGE_BG, "backgroundNeutral": LINE,
        "tableAccent": EXPOSURE,
        "minimum": RAMP[1], "center": RAMP[3], "maximum": RAMP[5], "null": "#D9D9D9",
        "good": ACCENT, "neutral": NEUTRAL, "bad": RESIDUAL,
        "textClasses": {
            "callout": {"fontSize": 26, "fontFace": "Segoe UI Semibold", "color": INK},
            "title": {"fontSize": 12, "fontFace": "Segoe UI Semibold", "color": INK},
            "header": {"fontSize": 11, "fontFace": "Segoe UI Semibold", "color": INK},
            "label": {"fontSize": 10, "fontFace": "Segoe UI", "color": INK},
        },
        "visualStyles": {
            "page": {"*": {"background": [{"color": {"solid": {"color": PAGE_BG}}, "transparency": 0}]}},
            "*": {"*": {
                "background": [{"show": True, "color": {"solid": {"color": CARD_BG}}, "transparency": 0}],
                "border": [{"show": True, "color": {"solid": {"color": LINE}}, "radius": 10}],
                "title": [{"fontColor": {"solid": {"color": INK}}, "fontSize": 12, "bold": True}],
                "subTitle": [{"fontColor": {"solid": {"color": MUTED}}, "fontSize": 9}],
            }},
            "textbox": {"*": {"background": [{"show": False}], "border": [{"show": False}]}},
        },
    }


def report_json() -> dict:
    stamp = {"visual": VERSIONS["visualContainer"], "report": VERSIONS["report"], "page": VERSIONS["page"]}
    return {
        "$schema": f"{SCHEMA}/report/{VERSIONS['report']}/schema.json",
        "themeCollection": {"customTheme": {"name": THEME_NAME, "reportVersionAtImport": stamp,
                                            "type": "RegisteredResources"}},
        "resourcePackages": [{"name": "RegisteredResources", "type": "RegisteredResources",
                              "items": [{"name": THEME_NAME, "path": THEME_NAME, "type": "CustomTheme"}]}],
        "settings": {"useStylableVisualContainerHeader": True, "defaultDrillFilterOtherVisuals": True,
                     "useEnhancedTooltips": True, "exportDataMode": "AllowSummarized"},
        "annotations": [{"name": "generatedBy", "value": "scripts/build_bi_report.py"}],
    }


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build(report: Path = REPORT) -> list[Path]:
    """Write the report definition, the theme and definition.pbir; return the files written."""
    definition = report / "definition"
    if definition.exists():
        shutil.rmtree(definition)
    legacy = report / "report.json"
    if legacy.exists():
        legacy.unlink()
    written = []

    def put(path: Path, data: dict) -> None:
        _write(path, data)
        written.append(path)

    put(report / "definition.pbir", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0",
        "datasetReference": {"byPath": {"path": "../FloodPolicyKit.SemanticModel"}}})
    put(definition / "version.json", {
        "$schema": f"{SCHEMA}/versionMetadata/{VERSIONS['versionMetadata']}/schema.json", "version": "2.0.0"})
    put(definition / "report.json", report_json())
    put(report / "StaticResources" / "RegisteredResources" / THEME_NAME, theme())
    names = []
    for make in PAGES:
        page, visuals = make()
        names.append(page["name"])
        folder = definition / "pages" / page["name"]
        put(folder / "page.json", page)
        for z, v in enumerate(visuals):
            v["position"]["z"] = v["position"]["tabOrder"] = z * 1000
            put(folder / "visuals" / v["name"] / "visual.json", v)
    put(definition / "pages" / "pages.json", {
        "$schema": f"{SCHEMA}/pagesMetadata/{VERSIONS['pagesMetadata']}/schema.json",
        "pageOrder": names, "activePageName": names[0]})
    return written


def main() -> int:
    written = build()
    print(f"{len(written)} files written under {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
