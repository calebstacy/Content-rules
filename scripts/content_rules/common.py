from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any

from . import TOOL_NAME, TOOL_VERSION


MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_SOURCES = 50
MAX_RULES = 200
MAX_SOURCE_REFS_PER_RULE = 20
MAX_INSTANCES = 1000
MAX_TOTAL_TERM_ENTRIES = 500
MAX_REPORTED_OCCURRENCES = 1000
MAX_JSON_NUMBER_CHARACTERS = 100
MAX_FACT_DEFINITIONS = 100
MAX_FACT_ASSERTIONS = 100
MAX_RULE_INSTANCE_EVALUATIONS = 10_000
MAX_RECEIPT_EVIDENCE_ITEMS_PER_RESULT = 1_000
MAX_RECEIPT_TRACE_UNITS = 25_000
MAX_RECEIPT_BYTES = 16 * 1024 * 1024
RULE_SET_PROTOCOL = "content-rule-set/1"
RULE_SET_PROTOCOL_V2 = "content-rule-set/2"
ARTIFACT_PROTOCOL = "content-artifact/1"
ARTIFACT_PROTOCOL_V2 = "content-artifact/2"
RECEIPT_PROTOCOL = "content-rule-receipt/1"
RECEIPT_PROTOCOL_V2 = "content-rule-receipt/2"
ERROR_PROTOCOL = "content-rule-error/1"
VALIDATION_PROTOCOL = "content-rule-validation/1"
CHECK_TYPES = {
    "banned_terms",
    "character_limit",
    "required_terminology",
    "required_fields",
}
STATUSES = {"PASS", "FAIL", "REVIEW", "NOT_APPLICABLE"}
ID_PATTERN = re.compile(r"^[a-z][a-z0-9._-]{0,79}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class RuleError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_utf8_with_hash(path: Path) -> tuple[str, str]:
    try:
        if not path.is_file():
            raise RuleError("FILE_NOT_FOUND", f"File does not exist: {path}")
        with path.open("rb") as handle:
            data = handle.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise RuleError(
                "FILE_TOO_LARGE",
                f"File exceeds the {MAX_FILE_BYTES // (1024 * 1024)} MB limit: {path.name}",
            )
        return data.decode("utf-8-sig"), hashlib.sha256(data).hexdigest()
    except UnicodeDecodeError as exc:
        raise RuleError("INVALID_UTF8", f"File is not valid UTF-8: {path.name}") from exc
    except OSError as exc:
        if isinstance(exc, RuleError):
            raise
        raise RuleError("FILE_READ_ERROR", f"Could not read file: {path.name}") from exc


def _reject_json_constant(token: str) -> None:
    raise ValueError(f"Non-finite JSON number is not allowed: {token}")


def _parse_json_int(token: str) -> int:
    digits = token[1:] if token.startswith("-") else token
    if len(digits) > MAX_JSON_NUMBER_CHARACTERS:
        raise ValueError("JSON integer is too large")
    return int(token)


def _parse_json_float(token: str) -> float:
    if len(token) > MAX_JSON_NUMBER_CHARACTERS:
        raise ValueError("JSON number is too large")
    value = float(token)
    if not math.isfinite(value):
        raise ValueError("Non-finite JSON number is not allowed")
    return value


def _reject_invalid_unicode(value: Any) -> None:
    if isinstance(value, str):
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise ValueError("JSON contains an invalid Unicode surrogate")
        return
    if isinstance(value, list):
        for item in value:
            _reject_invalid_unicode(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_invalid_unicode(key)
            _reject_invalid_unicode(item)


def load_json(path: Path, code: str) -> tuple[Any, str]:
    text, digest = read_utf8_with_hash(path)

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            _reject_invalid_unicode(key)
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(
            text,
            object_pairs_hook=unique_object,
            parse_constant=_reject_json_constant,
            parse_int=_parse_json_int,
            parse_float=_parse_json_float,
        )
        _reject_invalid_unicode(value)
        return value, digest
    except (json.JSONDecodeError, RecursionError, UnicodeError, ValueError) as exc:
        raise RuleError(code, f"Invalid strict JSON in {path.name}: {exc}") from exc


def atomic_write(path: Path, content: str, *, overwrite: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not overwrite:
        created = False
        try:
            with path.open("x", encoding="utf-8", newline="\n") as handle:
                created = True
                handle.write(content)
            return
        except FileExistsError as exc:
            raise RuleError("OUTPUT_EXISTS", f"Output already exists: {path.name}") from exc
        except OSError as exc:
            if created:
                path.unlink(missing_ok=True)
            raise RuleError("OUTPUT_WRITE_ERROR", f"Could not write output: {path.name}") from exc

    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(content)
            temp_name = handle.name
        os.replace(temp_name, path)
    except OSError as exc:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)
        raise RuleError("OUTPUT_WRITE_ERROR", f"Could not write output: {path.name}") from exc


def error_receipt(error: RuleError) -> dict[str, Any]:
    return {
        "protocol": ERROR_PROTOCOL,
        "status": "ERROR",
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
        "error": {"code": error.code, "message": error.message},
    }


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuleError("INVALID_CONFIG", f"{label} must be a JSON object")
    return value


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise RuleError("INVALID_CONFIG", f"{label} must be a JSON array")
    return value


def _reject_unknown(value: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise RuleError("INVALID_CONFIG", f"{label} has unknown field(s): {', '.join(unknown)}")


def _nonempty_string(value: Any, label: str, maximum: int = 500) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuleError("INVALID_CONFIG", f"{label} must be a non-empty string")
    if len(value) > maximum:
        raise RuleError("INVALID_CONFIG", f"{label} exceeds {maximum} characters")
    return value


def _identifier(value: Any, label: str) -> str:
    text = _nonempty_string(value, label, 80)
    if not ID_PATTERN.fullmatch(text):
        raise RuleError(
            "INVALID_CONFIG",
            f"{label} must start with a lowercase letter and use lowercase letters, digits, '.', '_' or '-'",
        )
    return text


def _string_list(
    value: Any,
    label: str,
    *,
    allow_star: bool = False,
    maximum_items: int = 100,
) -> list[str]:
    raw = _list(value, label)
    if not raw:
        raise RuleError("INVALID_CONFIG", f"{label} must not be empty")
    if len(raw) > maximum_items:
        raise RuleError("INVALID_CONFIG", f"{label} exceeds {maximum_items} items")
    result: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        text = _nonempty_string(item, f"{label}[{index}]", 200)
        if text in seen:
            raise RuleError("INVALID_CONFIG", f"{label} contains duplicate value: {text}")
        seen.add(text)
        result.append(text)
    if "*" in result and (not allow_star or len(result) != 1):
        raise RuleError("INVALID_CONFIG", f"{label} may use '*' only as its sole value")
    return result


def _relative_source_path(value: Any, label: str) -> str:
    text = _nonempty_string(value, label, 300)
    if "\\" in text or ":" in text:
        raise RuleError("INVALID_CONFIG", f"{label} must be a relative POSIX path")
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts or text.startswith("~"):
        raise RuleError("INVALID_CONFIG", f"{label} must stay inside the project")
    return text


def _scope_overlap(left: dict[str, list[str]], right: dict[str, list[str]]) -> bool:
    def intersects(a: list[str], b: list[str]) -> bool:
        return "*" in a or "*" in b or bool(set(a) & set(b))

    return intersects(left["surfaces"], right["surfaces"]) and intersects(left["fields"], right["fields"])


def _contains_unresolved_template(value: Any) -> bool:
    if isinstance(value, str):
        return value == "__REPLACE_ME__"
    if isinstance(value, list):
        return any(_contains_unresolved_template(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_unresolved_template(item) for item in value.values())
    return False


def _validate_rule_set_v1(raw: Any) -> dict[str, Any]:
    document = _object(raw, "rule set")
    if _contains_unresolved_template(document):
        raise RuleError(
            "UNRESOLVED_TEMPLATE",
            "Rule set still contains __REPLACE_ME__ template values",
        )
    _reject_unknown(document, {"schema_version", "rule_set", "sources", "rules"}, "rule set")
    if document.get("schema_version") != RULE_SET_PROTOCOL:
        raise RuleError("INVALID_CONFIG", f"schema_version must be {RULE_SET_PROTOCOL!r}")

    metadata = _object(document.get("rule_set"), "rule_set")
    _reject_unknown(metadata, {"id", "name", "status", "owner", "decision_ref"}, "rule_set")
    _identifier(metadata.get("id"), "rule_set.id")
    _nonempty_string(metadata.get("name"), "rule_set.name", 120)
    status = metadata.get("status")
    if status not in {"proposed", "adopted"}:
        raise RuleError("INVALID_CONFIG", "rule_set.status must be 'proposed' or 'adopted'")
    owner = metadata.get("owner")
    decision_ref = metadata.get("decision_ref")
    if status == "adopted":
        _nonempty_string(owner, "rule_set.owner", 120)
        _nonempty_string(decision_ref, "rule_set.decision_ref", 300)
    elif owner is not None or decision_ref is not None:
        raise RuleError("INVALID_CONFIG", "proposed rule sets must use null owner and decision_ref")

    sources = _list(document.get("sources"), "sources")
    if len(sources) > MAX_SOURCES:
        raise RuleError("INVALID_CONFIG", f"sources exceeds {MAX_SOURCES} items")
    source_ids: set[str] = set()
    for index, source_value in enumerate(sources):
        source = _object(source_value, f"sources[{index}]")
        _reject_unknown(source, {"id", "path", "sha256"}, f"sources[{index}]")
        source_id = _identifier(source.get("id"), f"sources[{index}].id")
        if source_id in source_ids:
            raise RuleError("INVALID_CONFIG", f"Duplicate source id: {source_id}")
        source_ids.add(source_id)
        _relative_source_path(source.get("path"), f"sources[{index}].path")
        sha = source.get("sha256")
        if not isinstance(sha, str) or not SHA256_PATTERN.fullmatch(sha):
            raise RuleError("INVALID_CONFIG", f"sources[{index}].sha256 must be a lowercase SHA-256")
        if sha == "0" * 64:
            raise RuleError("UNRESOLVED_TEMPLATE", f"sources[{index}].sha256 is still the template placeholder")

    rules = _list(document.get("rules"), "rules")
    if len(rules) > MAX_RULES:
        raise RuleError("INVALID_CONFIG", f"rules exceeds {MAX_RULES} items")
    rule_ids: set[str] = set()
    terminology_targets: dict[str, list[tuple[str, str, bool, dict[str, list[str]]]]] = {}
    total_term_entries = 0
    for index, rule_value in enumerate(rules):
        label = f"rules[{index}]"
        rule = _object(rule_value, label)
        _reject_unknown(rule, {"id", "description", "check", "scope", "params", "source_refs"}, label)
        rule_id = _identifier(rule.get("id"), f"{label}.id")
        if rule_id in rule_ids:
            raise RuleError("INVALID_CONFIG", f"Duplicate rule id: {rule_id}")
        rule_ids.add(rule_id)
        _nonempty_string(rule.get("description"), f"{label}.description", 300)
        check = rule.get("check")
        if check not in CHECK_TYPES:
            raise RuleError("INVALID_CONFIG", f"{label}.check is unsupported: {check!r}")

        scope = _object(rule.get("scope"), f"{label}.scope")
        _reject_unknown(scope, {"surfaces", "fields"}, f"{label}.scope")
        surfaces = _string_list(scope.get("surfaces"), f"{label}.scope.surfaces", allow_star=True)
        fields = _string_list(scope.get("fields"), f"{label}.scope.fields", allow_star=True)
        if check == "required_fields" and fields != ["*"]:
            raise RuleError("INVALID_CONFIG", f"{label}.scope.fields must be ['*'] for required_fields")

        params = _object(rule.get("params"), f"{label}.params")
        if check == "banned_terms":
            _reject_unknown(params, {"terms", "case_sensitive", "match"}, f"{label}.params")
            terms = _string_list(params.get("terms"), f"{label}.params.terms")
            total_term_entries += len(terms)
            if total_term_entries > MAX_TOTAL_TERM_ENTRIES:
                raise RuleError(
                    "INVALID_CONFIG",
                    f"Configured term entries exceed {MAX_TOTAL_TERM_ENTRIES}",
                )
            if not isinstance(params.get("case_sensitive"), bool):
                raise RuleError("INVALID_CONFIG", f"{label}.params.case_sensitive must be true or false")
            if params.get("match") not in {"whole", "substring"}:
                raise RuleError("INVALID_CONFIG", f"{label}.params.match must be 'whole' or 'substring'")
        elif check == "character_limit":
            _reject_unknown(params, {"maximum", "count"}, f"{label}.params")
            maximum = params.get("maximum")
            if not isinstance(maximum, int) or isinstance(maximum, bool) or not 0 <= maximum <= 100_000:
                raise RuleError("INVALID_CONFIG", f"{label}.params.maximum must be an integer from 0 to 100000")
            if params.get("count") != "unicode_code_points":
                raise RuleError("INVALID_CONFIG", f"{label}.params.count must be 'unicode_code_points'")
        elif check == "required_terminology":
            _reject_unknown(
                params,
                {"preferred", "instead_of", "case_sensitive", "match"},
                f"{label}.params",
            )
            preferred = _nonempty_string(params.get("preferred"), f"{label}.params.preferred", 200)
            variants = _string_list(params.get("instead_of"), f"{label}.params.instead_of")
            total_term_entries += len(variants) + 1
            if total_term_entries > MAX_TOTAL_TERM_ENTRIES:
                raise RuleError(
                    "INVALID_CONFIG",
                    f"Configured term entries exceed {MAX_TOTAL_TERM_ENTRIES}",
                )
            if not isinstance(params.get("case_sensitive"), bool):
                raise RuleError("INVALID_CONFIG", f"{label}.params.case_sensitive must be true or false")
            if params.get("match") not in {"whole", "substring"}:
                raise RuleError("INVALID_CONFIG", f"{label}.params.match must be 'whole' or 'substring'")
            case_sensitive = params["case_sensitive"]
            normalized_preferred = unicodedata.normalize("NFC", preferred)
            for variant in variants:
                normalized_variant = unicodedata.normalize("NFC", variant)
                same_term = (
                    normalized_variant == normalized_preferred
                    if case_sensitive
                    else normalized_variant.casefold() == normalized_preferred.casefold()
                )
                if same_term:
                    raise RuleError("INVALID_CONFIG", f"{label} maps a term to itself: {variant}")
                folded_variant = normalized_variant.casefold()
                target = (
                    normalized_variant,
                    normalized_preferred,
                    case_sensitive,
                    {"surfaces": surfaces, "fields": fields},
                )
                for (
                    other_variant,
                    other_preferred,
                    other_case_sensitive,
                    other_scope,
                ) in terminology_targets.get(folded_variant, []):
                    variants_overlap = (
                        normalized_variant == other_variant
                        if case_sensitive and other_case_sensitive
                        else folded_variant == other_variant.casefold()
                    )
                    preferred_agrees = (
                        normalized_preferred == other_preferred
                        if case_sensitive and other_case_sensitive
                        else normalized_preferred.casefold() == other_preferred.casefold()
                    )
                    if variants_overlap and not preferred_agrees and _scope_overlap(target[3], other_scope):
                        raise RuleError(
                            "INVALID_CONFIG",
                            "Conflicting required_terminology mappings target the same term in overlapping scopes",
                        )
                terminology_targets.setdefault(folded_variant, []).append(target)
        else:
            _reject_unknown(params, {"fields", "require_non_empty"}, f"{label}.params")
            _string_list(params.get("fields"), f"{label}.params.fields")
            if not isinstance(params.get("require_non_empty"), bool):
                raise RuleError("INVALID_CONFIG", f"{label}.params.require_non_empty must be true or false")

        refs = _list(rule.get("source_refs"), f"{label}.source_refs")
        if not refs:
            raise RuleError("INVALID_CONFIG", f"{label}.source_refs must not be empty")
        if len(refs) > MAX_SOURCE_REFS_PER_RULE:
            raise RuleError("INVALID_CONFIG", f"{label}.source_refs exceeds {MAX_SOURCE_REFS_PER_RULE} items")
        for ref_index, ref_value in enumerate(refs):
            ref_label = f"{label}.source_refs[{ref_index}]"
            ref = _object(ref_value, ref_label)
            _reject_unknown(ref, {"source_id", "line_start", "line_end", "quote"}, ref_label)
            source_id = _identifier(ref.get("source_id"), f"{ref_label}.source_id")
            if source_id not in source_ids:
                raise RuleError("INVALID_CONFIG", f"{ref_label} references unknown source: {source_id}")
            line_start = ref.get("line_start")
            line_end = ref.get("line_end")
            if not isinstance(line_start, int) or isinstance(line_start, bool) or line_start < 1:
                raise RuleError("INVALID_CONFIG", f"{ref_label}.line_start must be a positive integer")
            if not isinstance(line_end, int) or isinstance(line_end, bool) or line_end < line_start:
                raise RuleError("INVALID_CONFIG", f"{ref_label}.line_end must be at least line_start")
            _nonempty_string(ref.get("quote"), f"{ref_label}.quote", 1000)

    return document


def validate_rule_set(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict) and raw.get("schema_version") == RULE_SET_PROTOCOL_V2:
        from .contextual import validate_rule_set_v2

        return validate_rule_set_v2(raw)
    return _validate_rule_set_v1(raw)


def _validate_artifact_v1(raw: Any) -> dict[str, Any]:
    artifact = _object(raw, "artifact")
    _reject_unknown(artifact, {"schema_version", "instances"}, "artifact")
    if artifact.get("schema_version") != ARTIFACT_PROTOCOL:
        raise RuleError("INVALID_ARTIFACT", f"artifact.schema_version must be {ARTIFACT_PROTOCOL!r}")
    instances = artifact.get("instances")
    if not isinstance(instances, list):
        raise RuleError("INVALID_ARTIFACT", "artifact.instances must be a JSON array")
    if len(instances) > MAX_INSTANCES:
        raise RuleError("INVALID_ARTIFACT", f"artifact.instances exceeds {MAX_INSTANCES} items")
    seen_ids: set[str] = set()
    for index, instance_value in enumerate(instances):
        label = f"artifact.instances[{index}]"
        if not isinstance(instance_value, dict):
            raise RuleError("INVALID_ARTIFACT", f"{label} must be a JSON object")
        unknown = sorted(set(instance_value) - {"id", "surface", "fields"})
        if unknown:
            raise RuleError("INVALID_ARTIFACT", f"{label} has unknown field(s): {', '.join(unknown)}")
        instance_id = instance_value.get("id")
        if not isinstance(instance_id, str) or not ID_PATTERN.fullmatch(instance_id):
            raise RuleError("INVALID_ARTIFACT", f"{label}.id must be a lowercase identifier")
        if instance_id in seen_ids:
            raise RuleError("INVALID_ARTIFACT", f"Duplicate artifact instance id: {instance_id}")
        seen_ids.add(instance_id)
        surface = instance_value.get("surface")
        if not isinstance(surface, str) or not surface.strip() or len(surface) > 120:
            raise RuleError("INVALID_ARTIFACT", f"{label}.surface must be a non-empty string")
        fields = instance_value.get("fields")
        if not isinstance(fields, dict):
            raise RuleError("INVALID_ARTIFACT", f"{label}.fields must be a JSON object")
        if len(fields) > 200:
            raise RuleError("INVALID_ARTIFACT", f"{label}.fields exceeds 200 fields")
        for field_name in fields:
            if not isinstance(field_name, str) or not field_name.strip() or len(field_name) > 120:
                raise RuleError("INVALID_ARTIFACT", f"{label}.fields has an invalid field name")
    return artifact


def validate_artifact(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict) and raw.get("schema_version") == ARTIFACT_PROTOCOL_V2:
        from .contextual import validate_artifact_v2

        return validate_artifact_v2(raw)
    return _validate_artifact_v1(raw)


def verify_sources(
    rule_set: dict[str, Any],
    *,
    source_root: Path,
) -> tuple[list[dict[str, str]], list[Path]]:
    try:
        resolved_root = source_root.resolve(strict=True)
    except OSError as exc:
        raise RuleError("INVALID_SOURCE_ROOT", f"Source root does not exist: {source_root}") from exc
    if not resolved_root.is_dir():
        raise RuleError("INVALID_SOURCE_ROOT", f"Source root is not a directory: {source_root}")

    verified: list[dict[str, str]] = []
    resolved_sources: list[Path] = []
    source_lines: dict[str, list[str]] = {}
    for source in rule_set["sources"]:
        relative = PurePosixPath(source["path"])
        candidate = resolved_root.joinpath(*relative.parts)
        try:
            resolved_candidate = candidate.resolve(strict=True)
            resolved_candidate.relative_to(resolved_root)
        except (OSError, ValueError) as exc:
            raise RuleError(
                "UNSAFE_SOURCE_PATH",
                f"Source path is missing or leaves the source root: {source['path']}",
            ) from exc
        text, actual = read_utf8_with_hash(resolved_candidate)
        if actual != source["sha256"]:
            raise RuleError(
                "SOURCE_HASH_MISMATCH",
                f"Source changed after extraction: {source['path']}",
            )
        verified.append(
            {
                "id": source["id"],
                "path": source["path"],
                "sha256": actual,
                "status": "VERIFIED",
            }
        )
        resolved_sources.append(resolved_candidate)
        source_lines[source["id"]] = text.splitlines()

    if rule_set["schema_version"] == RULE_SET_PROTOCOL_V2:
        from .contextual import iter_source_refs_v2

        source_references = iter_source_refs_v2(rule_set)
    else:
        source_references = (
            (f"Rule {rule['id']}", ref)
            for rule in rule_set["rules"]
            for ref in rule["source_refs"]
        )

    for reference_owner, ref in source_references:
        lines = source_lines[ref["source_id"]]
        if ref["line_end"] > len(lines):
            raise RuleError(
                "SOURCE_REF_MISMATCH",
                f"{reference_owner} cites lines beyond the end of source {ref['source_id']}",
            )
        excerpt = "\n".join(lines[ref["line_start"] - 1 : ref["line_end"]])
        if ref["quote"] not in excerpt:
            raise RuleError(
                "SOURCE_REF_MISMATCH",
                f"{reference_owner} quote does not match its cited source lines",
            )
    return verified, resolved_sources


def normalize_text(value: str, *, case_sensitive: bool) -> str:
    normalized = unicodedata.normalize("NFC", value)
    return normalized if case_sensitive else normalized.casefold()


def literal_occurrences(text: str, term: str, *, case_sensitive: bool, match: str) -> tuple[int, bool]:
    haystack = normalize_text(text, case_sensitive=case_sensitive)
    needle = normalize_text(term, case_sensitive=case_sensitive)
    escaped = re.escape(needle)
    if match == "whole":
        left = r"(?<!\w)" if needle and (needle[0].isalnum() or needle[0] == "_") else ""
        right = r"(?!\w)" if needle and (needle[-1].isalnum() or needle[-1] == "_") else ""
        pattern = re.compile(f"{left}{escaped}{right}")
    else:
        pattern = re.compile(escaped)
    count = 0
    for _ in pattern.finditer(haystack):
        count += 1
        if count > MAX_REPORTED_OCCURRENCES:
            return MAX_REPORTED_OCCURRENCES, True
    return count, False


def matching_instances(artifact: dict[str, Any], surfaces: list[str]) -> list[dict[str, Any]]:
    if surfaces == ["*"]:
        return list(artifact["instances"])
    allowed = set(surfaces)
    return [instance for instance in artifact["instances"] if instance["surface"] in allowed]


def text_scope(
    artifact: dict[str, Any], scope: dict[str, list[str]]
) -> tuple[list[dict[str, str]], list[dict[str, str]], bool]:
    instances = matching_instances(artifact, scope["surfaces"])
    if not instances:
        return [], [], False
    units: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []
    for instance in instances:
        fields = instance["fields"]
        field_names = sorted(fields) if scope["fields"] == ["*"] else scope["fields"]
        if not field_names:
            missing.append(
                {
                    "instance_id": instance["id"],
                    "surface": instance["surface"],
                    "field": "*",
                    "reason": "no_fields",
                }
            )
            continue
        for field_name in field_names:
            if field_name not in fields:
                missing.append(
                    {
                        "instance_id": instance["id"],
                        "surface": instance["surface"],
                        "field": field_name,
                        "reason": "missing_field",
                    }
                )
                continue
            value = fields[field_name]
            if not isinstance(value, str):
                missing.append(
                    {
                        "instance_id": instance["id"],
                        "surface": instance["surface"],
                        "field": field_name,
                        "reason": "non_string_value",
                    }
                )
                continue
            units.append(
                {
                    "instance_id": instance["id"],
                    "surface": instance["surface"],
                    "field": field_name,
                    "text": value,
                }
            )
    return units, missing, True


def result_base(rule: dict[str, Any]) -> dict[str, Any]:
    return {
        "rule_id": rule["id"],
        "description": rule["description"],
        "check": rule["check"],
        "scope": rule["scope"],
        "source_refs": rule["source_refs"],
    }
