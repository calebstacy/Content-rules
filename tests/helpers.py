from __future__ import annotations

import json
import hashlib
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

SOURCE_TEXT = "Exact source guidance.\n"
SOURCE_SHA256 = hashlib.sha256(SOURCE_TEXT.encode("utf-8")).hexdigest()


def source() -> dict[str, Any]:
    return {
        "id": "guide",
        "path": "guidance.md",
        "sha256": SOURCE_SHA256,
    }


def source_ref(quote: str = "Exact source guidance.") -> dict[str, Any]:
    return {
        "source_id": "guide",
        "line_start": 1,
        "line_end": 1,
        "quote": quote,
    }


def rule(check: str, *, rule_id: str | None = None) -> dict[str, Any]:
    params: dict[str, Any]
    fields = ["title"]
    if check == "banned_terms":
        params = {"terms": ["log"], "case_sensitive": False, "match": "whole"}
    elif check == "character_limit":
        params = {"maximum": 10, "count": "unicode_code_points"}
    elif check == "required_terminology":
        params = {
            "preferred": "sign in",
            "instead_of": ["log in"],
            "case_sensitive": False,
            "match": "whole",
        }
    elif check == "required_fields":
        params = {"fields": ["title"], "require_non_empty": True}
        fields = ["*"]
    else:
        params = {}
    return {
        "id": rule_id or check.replace("_", "-"),
        "description": f"Test {check}.",
        "check": check,
        "scope": {"surfaces": ["notice"], "fields": fields},
        "params": params,
        "source_refs": [source_ref()],
    }


def rule_set(*rules: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "content-rule-set/1",
        "rule_set": {
            "id": "test-rules",
            "name": "Test rules",
            "status": "proposed",
            "owner": None,
            "decision_ref": None,
        },
        "sources": [source()] if rules else [],
        "rules": [deepcopy(item) for item in rules],
    }


def artifact(fields: dict[str, Any], *, surface: str = "notice") -> dict[str, Any]:
    return {
        "schema_version": "content-artifact/1",
        "instances": [
            {
                "id": "notice-01",
                "surface": surface,
                "fields": deepcopy(fields),
            }
        ],
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def write_source(root: Path) -> None:
    (root / "guidance.md").write_text(SOURCE_TEXT, encoding="utf-8", newline="\n")
