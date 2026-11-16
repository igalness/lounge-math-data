#!/usr/bin/env python3
"""Validate v1/airports.json and v1/countries.json.

Standard library only (Python 3.11+). Prints one line per violation and exits
non-zero if there is any.

Checks, in order:
  1. JSON Schema (the subset of 2020-12 that schema/*.schema.json uses).
  2. Stamp rules — a stamp is any object carrying "confidence":
       - verified/scraped with no verified_on fails (a value without a date
         renders NO DATA in the app, so it is a data bug);
       - verified/scraped with no source fails;
       - verified_on (and an airport's updated_at) must be a real calendar day,
         not in the future.
     rule and unknown stamps carry no date by design and are exempt.
  3. data_version must be greater than the value on origin/main whenever the
     file differs from origin/main. Skipped when there is no origin/main yet,
     or when the file is unchanged (a docs-only PR needs no bump, and a push to
     main compares main with itself).

Usage: python3 scripts/validate.py [--root DIR] [--base-ref origin/main]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

FILES = {
    "v1/airports.json": "schema/airports.schema.json",
    "v1/countries.json": "schema/countries.schema.json",
}
DATED = {"verified", "scraped"}


# MARK: - JSON Schema subset

def _is_type(value, name: str) -> bool:
    return {
        "object": lambda v: isinstance(v, dict),
        "array": lambda v: isinstance(v, list),
        "string": lambda v: isinstance(v, str),
        "boolean": lambda v: isinstance(v, bool),
        "null": lambda v: v is None,
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    }[name](value)


def _parse_date(text: str) -> dt.date | None:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return None
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        return None


def _parse_datetime(text: str) -> dt.datetime | None:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})", text):
        return None
    try:
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


FORMATS = {
    "date": lambda s: _parse_date(s) is not None,
    "date-time": lambda s: _parse_datetime(s) is not None,
    "uri": lambda s: re.fullmatch(r"https?://\S+", s) is not None,
}


def _resolve(root: dict, ref: str) -> dict:
    if not ref.startswith("#/"):
        raise ValueError(f"only local $ref is supported: {ref}")
    node = root
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def schema_errors(value, schema: dict, root: dict, path: str = "$") -> list[str]:
    errors: list[str] = []
    if "$ref" in schema:
        errors += schema_errors(value, _resolve(root, schema["$ref"]), root, path)
    for sub in schema.get("allOf", []):
        errors += schema_errors(value, sub, root, path)
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: must be {json.dumps(schema['const'])}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {json.dumps(value)} is not one of {json.dumps(schema['enum'])}")
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_is_type(value, t) for t in types):
            errors.append(f"{path}: expected {' or '.join(types)}, got {json.dumps(value)}")
            return errors
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{path}: must not be empty")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{path}: {json.dumps(value)} does not match {schema['pattern']}")
        fmt = schema.get("format")
        if fmt in FORMATS and not FORMATS[fmt](value):
            errors.append(f"{path}: {json.dumps(value)} is not a valid {fmt}")
    if _is_type(value, "number") and "minimum" in schema and value < schema["minimum"]:
        errors.append(f"{path}: {value} is below the minimum {schema['minimum']}")
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            errors += schema_errors(item, schema["items"], root, f"{path}[{i}]")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: missing required key {json.dumps(key)}")
        props = schema.get("properties", {})
        for key, item in value.items():
            if "propertyNames" in schema:
                errors += schema_errors(key, schema["propertyNames"], root, f"{path} key {json.dumps(key)}")
            if key in props:
                errors += schema_errors(item, props[key], root, f"{path}.{key}")
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}: unexpected key {json.dumps(key)}")
            elif isinstance(schema.get("additionalProperties"), dict):
                errors += schema_errors(item, schema["additionalProperties"], root, f"{path}.{key}")
    return errors


# MARK: - Stamp rules

def _check_day(text, path: str, today: dt.date) -> list[str]:
    day = _parse_date(text) if isinstance(text, str) else None
    if day is None:
        return [f"{path}: {json.dumps(text)} is not a real date (YYYY-MM-DD)"]
    if day > today:
        return [f"{path}: {text} is in the future"]
    return []


def stamp_errors(node, today: dt.date, path: str = "$") -> list[str]:
    errors: list[str] = []
    if isinstance(node, dict):
        if "confidence" in node:
            confidence = node.get("confidence")
            if confidence in DATED:
                if not node.get("verified_on"):
                    errors.append(f"{path}: {confidence} stamp has no verified_on")
                if not node.get("source"):
                    errors.append(f"{path}: {confidence} stamp has no source")
            if "verified_on" in node:
                errors += _check_day(node["verified_on"], f"{path}.verified_on", today)
        if "updated_at" in node:
            errors += _check_day(node["updated_at"], f"{path}.updated_at", today)
        for key, value in node.items():
            errors += stamp_errors(value, today, f"{path}.{key}")
    elif isinstance(node, list):
        for i, item in enumerate(node):
            label = item.get("iata") or item.get("id") if isinstance(item, dict) else None
            errors += stamp_errors(item, today, f"{path}[{label or i}]")
    return errors


# MARK: - data_version

def base_text(root: Path, base_ref: str, rel: str) -> str | None:
    """The file as it is on base_ref, or None if the ref or the file is absent."""
    result = subprocess.run(
        ["git", "-C", str(root), "show", f"{base_ref}:{rel}"],
        capture_output=True, text=True,
    )
    return result.stdout if result.returncode == 0 else None


def version_errors(rel: str, data: dict, current_text: str, base: str | None) -> list[str]:
    if base is None or base == current_text:
        return []
    try:
        old = json.loads(base).get("data_version")
    except json.JSONDecodeError:
        return []
    new = data.get("data_version")
    if isinstance(old, int) and isinstance(new, int) and new <= old:
        return [f"{rel}: data_version {new} must be greater than {old} on main — bump it"]
    return []


# MARK: - Main

def validate(root: Path, base_ref: str | None, today: dt.date) -> list[str]:
    errors: list[str] = []
    for rel, schema_rel in FILES.items():
        path = root / rel
        try:
            text = path.read_text(encoding="utf-8")
            data = json.loads(text)
        except FileNotFoundError:
            errors.append(f"{rel}: file is missing")
            continue
        except json.JSONDecodeError as exc:
            errors.append(f"{rel}: invalid JSON — {exc}")
            continue
        schema = json.loads((root / schema_rel).read_text(encoding="utf-8"))
        errors += [f"{rel}: {e}" for e in schema_errors(data, schema, schema)]
        errors += [f"{rel}: {e}" for e in stamp_errors(data, today)]
        if base_ref:
            errors += version_errors(rel, data, text, base_text(root, base_ref, rel))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=Path(__file__).resolve().parent.parent, type=Path)
    parser.add_argument("--base-ref", default="origin/main",
                        help="git ref to compare data_version against ('' to skip)")
    args = parser.parse_args(argv)

    errors = validate(args.root, args.base_ref or None, dt.datetime.now(dt.timezone.utc).date())
    for line in errors:
        print(line)
    if errors:
        print(f"{len(errors)} violation(s)", file=sys.stderr)
        return 1
    print("ok: " + ", ".join(FILES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
