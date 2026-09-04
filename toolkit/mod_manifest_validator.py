import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RUNTIME_API_VERSION = "1.0"
MANIFEST_SCHEMA_VERSION = "1"
ALLOWED_CAPABILITIES = {
    "command_registration",
    "world_modification",
    "server_broadcast",
    "system_provider_registration",
}


@dataclass
class ManifestIssue:
    severity: str
    path: str
    message: str


def _parse_version(value: str) -> tuple[int, ...] | None:
    text = str(value).strip()
    if text == "":
        return None
    parts = text.split(".")
    out: list[int] = []
    for part in parts:
        if not part.isdigit():
            return None
        out.append(int(part))
    return tuple(out)


def _in_range(current: str, min_v: str, max_v: str) -> bool:
    c = _parse_version(current)
    mn = _parse_version(min_v)
    mx = _parse_version(max_v)
    if c is None or mn is None or mx is None:
        return False
    return mn <= c <= mx


def validate_manifest(payload: Any, source: str, runtime_api: str = RUNTIME_API_VERSION) -> list[ManifestIssue]:
    issues: list[ManifestIssue] = []
    if not isinstance(payload, dict):
        return [ManifestIssue("error", source, "manifest must be a JSON object")]

    required_str = [
        "plugin_id",
        "name",
        "version",
        "manifest_schema_version",
        "engine_api_min",
        "engine_api_max",
    ]
    for key in required_str:
        value = payload.get(key)
        if not isinstance(value, str) or value.strip() == "":
            issues.append(ManifestIssue("error", source, f"missing/invalid string field '{key}'"))

    plugin_id = str(payload.get("plugin_id", "")).strip()
    if plugin_id and re.fullmatch(r"[a-z0-9_\\.-]+", plugin_id) is None:
        issues.append(ManifestIssue("error", source, "plugin_id must match [a-z0-9_.-]+"))

    schema_v = str(payload.get("manifest_schema_version", "")).strip()
    if schema_v and schema_v != MANIFEST_SCHEMA_VERSION:
        issues.append(
            ManifestIssue(
                "error",
                source,
                f"unsupported manifest_schema_version '{schema_v}', expected '{MANIFEST_SCHEMA_VERSION}'",
            )
        )

    engine_min = str(payload.get("engine_api_min", "")).strip()
    engine_max = str(payload.get("engine_api_max", "")).strip()
    if engine_min and engine_max:
        min_p = _parse_version(engine_min)
        max_p = _parse_version(engine_max)
        if min_p is None or max_p is None:
            issues.append(ManifestIssue("error", source, "engine_api_min/max must be dotted numeric versions"))
        elif min_p > max_p:
            issues.append(ManifestIssue("error", source, "engine_api_min must be <= engine_api_max"))
        elif not _in_range(runtime_api, engine_min, engine_max):
            issues.append(
                ManifestIssue(
                    "error",
                    source,
                    f"runtime API {runtime_api} outside supported range {engine_min}..{engine_max}",
                )
            )

    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, list):
        issues.append(ManifestIssue("error", source, "capabilities must be an array"))
    else:
        for cap in capabilities:
            cap_text = str(cap).strip()
            if cap_text == "":
                issues.append(ManifestIssue("error", source, "capabilities entries must be non-empty strings"))
                continue
            if cap_text not in ALLOWED_CAPABILITIES:
                issues.append(ManifestIssue("error", source, f"unknown capability '{cap_text}'"))

    return issues


def validate_manifest_file(path: Path, runtime_api: str = RUNTIME_API_VERSION) -> list[ManifestIssue]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [ManifestIssue("error", str(path), f"failed to parse JSON: {exc}")]
    return validate_manifest(payload, str(path), runtime_api=runtime_api)


def validate_mod_roots(roots: list[Path], runtime_api: str = RUNTIME_API_VERSION) -> tuple[int, int]:
    manifests: list[Path] = []
    for root in roots:
        if root.exists() and root.is_dir():
            manifests.extend(sorted(root.rglob("manifest.json")))
    errors = 0
    checked = 0
    for manifest_path in manifests:
        checked += 1
        issues = validate_manifest_file(manifest_path, runtime_api=runtime_api)
        for issue in issues:
            if issue.severity == "error":
                errors += 1
                print(f"[ERROR] {issue.path} - {issue.message}")
            else:
                print(f"[WARN]  {issue.path} - {issue.message}")
    print(f"Checked {checked} mod manifests")
    print(f"Errors: {errors}")
    return checked, errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate mod manifest compatibility and capabilities.")
    parser.add_argument(
        "--roots",
        nargs="*",
        default=["server/mods", "mods"],
        help="Directories to scan recursively for manifest.json files.",
    )
    parser.add_argument("--runtime-api", default=RUNTIME_API_VERSION, help="Runtime API version.")
    args = parser.parse_args()

    roots = [Path(r) for r in args.roots]
    _checked, errors = validate_mod_roots(roots, runtime_api=args.runtime_api)
    raise SystemExit(1 if errors > 0 else 0)


if __name__ == "__main__":
    main()
