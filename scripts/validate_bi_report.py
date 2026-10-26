"""Validate the Power BI project's JSON files against Microsoft's published schemas.

Nobody on the team can open Power BI Desktop at every change, and Desktop
refuses a PBIR file that breaks its schema with a blocking error. So every JSON
file under `bi/` is checked here, offline, against the schemas vendored in
`bi/schemas/` (microsoft/json-schemas and microsoft/powerbi-desktop-samples,
both MIT - the licences are copied beside them):

* each file against the schema its own `$schema` names - the theme, which
  carries none, against the report theme schema of Desktop 2.159;
* each visual's formatting, against that theme schema too. The PBIR
  visualContainer schema accepts any object and property name in a visual's
  `objects`, so a misspelt `categoryAxis.labelColour` would pass it and be
  silently dropped by Desktop. The theme schema lists, per visual type, the
  objects and properties Desktop knows and the values each accepts, so it is
  the closest published check of formatting there is. The expressions inside
  those values (literals, measures, fill rules) are checked against the
  semantic query schema, which the visual schema does not apply to them.

What no schema checks: the data roles a visual uses (`Category`, `Y`, ...) and
whether the result looks right. Those need Power BI Desktop.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from jsonschema import Draft7Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT7

ROOT = Path(__file__).resolve().parents[1]
BI = ROOT / "bi"
SCHEMAS = BI / "schemas"
PREFIX = "https://developer.microsoft.com/json-schemas/"
THEME_SCHEMA = SCHEMAS / "reportThemeSchema-2.159.json"
#: Folders under bi/ that hold no project file: the vendored schemas, the
#: exported data, Desktop's per-user state.
SKIP = {"schemas", "data", ".pbi"}



#: Files Power BI Desktop writes back without a `$schema` when it saves the
#: project (measured 2026-10-25 after the owner saved the .pbip once).
DESKTOP_OWNED = {"FloodPolicyKit.pbip", "definition.pbism", "definition.pbir", "diagramLayout.json"}

#: Schema versions Power BI Desktop writes before Microsoft publishes them, read
#: against the newest published one. Desktop saved visuals as visualContainer
#: 2.14.0 while microsoft/json-schemas stopped at 2.13.0 and the URL answered
#: 404; validating against 2.13.0 still rejects any key 2.13.0 does not know,
#: so a property only 2.14.0 allows shows up as a failure rather than a pass.
UNPUBLISHED = {
    "fabric/item/report/definition/visualContainer/2.14.0/schema.json":
        "fabric/item/report/definition/visualContainer/2.13.0/schema.json",
}


def _local(uri: str) -> Path:
    """The vendored copy of a schema URL. The `$id` of an embedded schema says
    `schema.embedded.json` while the file and every `$ref` say `schema-embedded.json`."""
    if not uri.startswith(PREFIX):
        raise LookupError(f"not a vendored schema: {uri}")
    relative = uri[len(PREFIX):].replace("schema.embedded.json", "schema-embedded.json")
    return SCHEMAS / UNPUBLISHED.get(relative, relative)


def _retrieve(uri: str) -> Resource:
    path = _local(uri)
    if not path.exists():
        raise LookupError(f"schema not vendored: {uri} (expected {path})")
    return Resource.from_contents(json.loads(path.read_text(encoding="utf-8")), default_specification=DRAFT7)


_REGISTRY = Registry(retrieve=_retrieve)


def _theme_schema() -> dict:
    return json.loads(THEME_SCHEMA.read_text(encoding="utf-8"))


def project_files(bi: Path = BI) -> list[Path]:
    """Every JSON-format file of the project: .json, .pbir, .pbism, .pbip."""
    out = []
    for path in sorted(bi.rglob("*")):
        if path.is_file() and path.suffix in {".json", ".pbir", ".pbism", ".pbip"} \
                and not SKIP & set(path.relative_to(bi).parts):
            out.append(path)
    return out


def is_theme(path: Path) -> bool:
    return path.parent.name == "RegisteredResources" and path.suffix == ".json"


def schema_of(path: Path, data: dict) -> str:
    """The schema a file is validated against: its `$schema`, or the theme schema."""
    if is_theme(path):
        return THEME_SCHEMA.name
    return data.get("$schema", "")


def _errors(validator: Draft7Validator, data) -> list[str]:
    return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
            for e in sorted(validator.iter_errors(data), key=lambda e: list(map(str, e.absolute_path)))]


def validate_file(path: Path) -> list[str]:
    """Schema errors of one file; an empty list when it validates."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if is_theme(path):
        return _errors(Draft7Validator(_theme_schema()), data)
    url = data.get("$schema")
    if not url:
        # Power BI Desktop rewrites these on every save without a $schema line
        # (and adds diagramLayout.json): files it owns, not ours to validate.
        if path.name in DESKTOP_OWNED:
            return []
        return ["no $schema: the file cannot be checked"]
    try:
        schema = _retrieve(url).contents
    except LookupError as exc:
        return [str(exc)]
    relative = url[len(PREFIX):] if url.startswith(PREFIX) else url
    if relative in UNPUBLISHED:
        # The schema pins its own URL as a constant; the file names the newer one.
        data = {**data, "$schema": PREFIX + UNPUBLISHED[relative]}
    return _errors(Draft7Validator(schema, registry=_REGISTRY), data)


# --- visual formatting against the theme schema --------------------------------

def _literal(value):
    """A PBIR formatting value as the plain value a theme would hold, or None
    when it is not a literal (a measure, a fill rule, rich text)."""
    if isinstance(value, dict) and set(value) == {"solid"}:
        inner = _literal(value["solid"].get("color"))
        return None if inner is None else {"solid": {"color": inner}}
    try:
        text = value["expr"]["Literal"]["Value"]
    except (KeyError, TypeError):
        return None
    if text in ("true", "false"):
        return text == "true"
    if text.startswith("'") and text.endswith("'"):
        return text[1:-1].replace("''", "'")
    match = re.fullmatch(r"(-?\d+(?:\.\d+)?)([DL]?)", text)
    if match:
        number = float(match.group(1))
        return int(number) if match.group(2) == "L" or number.is_integer() else number
    return None


def _allowed(theme: dict, visual_type: str) -> tuple[dict, dict]:
    """(objects of this visual type, objects of every visual container) in the theme schema."""
    defs = theme["definitions"]

    def objects(definition: dict) -> dict:
        parts = definition.get("allOf", [definition])
        found: dict = {}
        for part in parts:
            if "$ref" in part:
                part = defs[part["$ref"].split("/")[-1]]
            found.update({k: v["items"]["properties"] for k, v in part.get("properties", {}).items()
                          if k != "*" and "items" in v})
        return found

    own = defs.get(f"visual-{visual_type}")
    return (objects(own) if own else {}), objects(defs["commonCards"])


#: Every formatting value is an expression - a literal, a measure, a fill rule -
#: but the visual schema types `objects` as free-form, so the expression
#: grammar is checked here against the semantic query schema it comes from.
_EXPRESSION = Draft7Validator(
    {"$ref": PREFIX + "fabric/item/report/definition/semanticQuery/1.4.0/schema.json"
             "#/definitions/QueryExpressionContainer"},
    registry=_REGISTRY)


def _expressions(value, where: str):
    """Each `expr` inside a formatting value, with where it sits."""
    if isinstance(value, dict):
        for key, inner in value.items():
            if key == "expr":
                yield where, inner
            else:
                yield from _expressions(inner, f"{where}.{key}")
    elif isinstance(value, list):
        for i, inner in enumerate(value):
            yield from _expressions(inner, f"{where}[{i}]")


def formatting_errors(path: Path, theme: dict | None = None) -> list[str]:
    """Formatting objects, properties and literal values of one visual.json that
    the theme schema does not know for that visual type."""
    theme = theme or _theme_schema()
    visual = json.loads(path.read_text(encoding="utf-8")).get("visual", {})
    kind = visual.get("visualType", "")
    own, common = _allowed(theme, kind)
    if not own:
        return [f"visual type {kind!r} is not in the theme schema"]
    errors = []
    for section, allowed in (("objects", own), ("visualContainerObjects", common)):
        for name, entries in visual.get(section, {}).items():
            if name not in allowed:
                errors.append(f"{section}.{name}: no such object for {kind}")
                continue
            for entry in entries:
                for prop, value in entry.get("properties", {}).items():
                    for where, expr in _expressions(value, f"{section}.{name}.{prop}"):
                        errors += [f"{where}: {m}" for m in _errors(_EXPRESSION, expr)]
                    if prop not in allowed[name]:
                        errors.append(f"{section}.{name}.{prop}: no such property for {kind}")
                        continue
                    plain = _literal(value)
                    if plain is None:
                        continue
                    schema = {**allowed[name][prop], "definitions": theme["definitions"]}
                    for message in _errors(Draft7Validator(schema), plain):
                        errors.append(f"{section}.{name}.{prop} = {plain!r}: {message}")
    return errors


def main() -> int:
    theme = _theme_schema()
    failures = 0
    for path in project_files():
        data = json.loads(path.read_text(encoding="utf-8"))
        errors = validate_file(path)
        if path.name == "visual.json":
            errors += formatting_errors(path, theme)
        failures += bool(errors)
        version = re.search(r"/([^/]+/\d+\.\d+\.\d+)/schema\.json$", schema_of(path, data))
        label = version.group(1) if version else schema_of(path, data)
        print(f"{'FAIL' if errors else 'ok  '} {path.relative_to(BI).as_posix()}  [{label}]")
        for error in errors:
            print(f"       {error}")
    print(f"{failures} file(s) failing")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
