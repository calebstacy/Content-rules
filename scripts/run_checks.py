#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import NoReturn

from content_rules import TOOL_NAME, TOOL_VERSION
from content_rules.common import (
    VALIDATION_PROTOCOL,
    RuleError,
    atomic_write,
    canonical_json,
    error_receipt,
    load_json,
    validate_artifact,
    validate_rule_set,
    verify_sources,
)
from content_rules.runtime import exit_code, run_checks


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise RuleError("INVALID_ARGUMENTS", message)


def build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(
        description="Run fixed deterministic content checks from a strict JSON rule set.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate a rule-set JSON file.")
    validate_parser.add_argument("--rules", required=True, type=Path)
    validate_parser.add_argument(
        "--source-root",
        type=Path,
        default=Path.cwd(),
        help="Project root used to resolve source paths (default: current directory).",
    )

    check_parser = subparsers.add_parser("check", help="Check a typed content artifact.")
    check_parser.add_argument("--rules", required=True, type=Path)
    check_parser.add_argument("--input", required=True, type=Path)
    check_parser.add_argument(
        "--source-root",
        type=Path,
        default=Path.cwd(),
        help="Project root used to resolve source paths (default: current directory).",
    )
    check_parser.add_argument("--receipt", type=Path)
    check_parser.add_argument("--force", action="store_true", help="Replace an existing receipt file.")
    return parser


def _configure_stdout() -> None:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", newline="\n")


def _same_path(left: Path, right: Path) -> bool:
    return left.resolve(strict=False) == right.resolve(strict=False)


def main(argv: list[str] | None = None) -> int:
    _configure_stdout()
    try:
        args = build_parser().parse_args(argv)
        rule_raw, rules_sha256 = load_json(args.rules, "INVALID_RULES_JSON")
        rule_set = validate_rule_set(rule_raw)
        verified_sources, resolved_sources = verify_sources(rule_set, source_root=args.source_root)
        if args.command == "validate":
            payload = {
                "protocol": VALIDATION_PROTOCOL,
                "status": "VALID",
                "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
                "rule_set": {
                    "id": rule_set["rule_set"]["id"],
                    "status": rule_set["rule_set"]["status"],
                    "rule_count": len(rule_set["rules"]),
                    "path": args.rules.name,
                    "sha256": rules_sha256,
                    "sources_verified": len(verified_sources),
                },
            }
            sys.stdout.write(canonical_json(payload))
            return 0

        artifact_raw, artifact_sha256 = load_json(args.input, "INVALID_ARTIFACT_JSON")
        artifact = validate_artifact(artifact_raw)
        receipt = run_checks(
            rule_set,
            artifact,
            rules_path=args.rules,
            artifact_path=args.input,
            rules_sha256=rules_sha256,
            artifact_sha256=artifact_sha256,
            verified_sources=verified_sources,
        )
        content = canonical_json(receipt)
        if args.receipt is not None:
            protected_paths = [args.rules, args.input, *resolved_sources]
            if any(_same_path(args.receipt, protected) for protected in protected_paths):
                raise RuleError(
                    "UNSAFE_OUTPUT",
                    "Receipt output must not replace the rules, input, or a verified source file",
                )
            atomic_write(args.receipt, content, overwrite=args.force)
        sys.stdout.write(content)
        return exit_code(receipt)
    except RuleError as error:
        sys.stdout.write(canonical_json(error_receipt(error)))
        return 2
    except (OSError, RecursionError, UnicodeError, ValueError) as exc:
        error = RuleError("UNEXPECTED_RUNTIME_ERROR", f"The check could not complete: {type(exc).__name__}")
        sys.stdout.write(canonical_json(error_receipt(error)))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
