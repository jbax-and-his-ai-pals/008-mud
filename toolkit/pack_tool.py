import argparse
import json
import os
import sys
from pathlib import Path

DEFAULT_THEME_PATH = Path("client/themes/default.json")
CURRENT_RUNTIME_API = "1.0"
CURRENT_PACK_SPEC = "1"


def parse_version(value: str) -> tuple[int, ...] | None:
    text = str(value).strip()
    if text == "":
        return None
    parts = text.split(".")
    parsed: list[int] = []
    for p in parts:
        if p == "" or not p.isdigit():
            return None
        parsed.append(int(p))
    return tuple(parsed)


def version_in_range(version: str, min_v: str, max_v: str) -> bool:
    current = parse_version(version)
    min_parsed = parse_version(min_v)
    max_parsed = parse_version(max_v)
    if current is None or min_parsed is None or max_parsed is None:
        return False
    return min_parsed <= current <= max_parsed

def load_json(path: Path) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading JSON from {path}: {e}")
        return None

def validate_pack(
    target_path: Path,
    reference_pack: dict,
    strict: bool = False,
    runtime_api: str = CURRENT_RUNTIME_API,
    require_compat: bool = True,
) -> bool:
    print(f"Validating {target_path}...")
    pack = load_json(target_path)
    if pack is None:
        return False
    
    is_valid = True
    
    # 1. Required fields
    for required in ["theme_id", "display_name"]:
        if required not in pack:
            print(f"  [ERROR] Missing required field: '{required}'")
            is_valid = False
        elif not isinstance(pack[required], str):
            print(f"  [ERROR] Field '{required}' must be a string.")
            is_valid = False

    # 2. Compatibility contract
    compat_fields = ["pack_spec_version", "runtime_api_min", "runtime_api_max"]
    for key in compat_fields:
        value = pack.get(key)
        if value is None:
            if require_compat:
                print(f"  [ERROR] Missing compatibility field: '{key}'")
                is_valid = False
            else:
                print(f"  [WARN] Missing compatibility field: '{key}'")
            continue
        if not isinstance(value, str) or value.strip() == "":
            print(f"  [ERROR] Field '{key}' must be a non-empty string.")
            is_valid = False
    pack_spec = str(pack.get("pack_spec_version", "")).strip()
    if pack_spec and pack_spec != CURRENT_PACK_SPEC:
        print(
            f"  [ERROR] Unsupported pack_spec_version '{pack_spec}'. "
            f"Expected '{CURRENT_PACK_SPEC}'."
        )
        is_valid = False
    runtime_min = str(pack.get("runtime_api_min", "")).strip()
    runtime_max = str(pack.get("runtime_api_max", "")).strip()
    if runtime_min and runtime_max:
        min_parsed = parse_version(runtime_min)
        max_parsed = parse_version(runtime_max)
        if min_parsed is None or max_parsed is None:
            print("  [ERROR] runtime_api_min/runtime_api_max must be dotted numeric versions.")
            is_valid = False
        elif min_parsed > max_parsed:
            print("  [ERROR] runtime_api_min must be <= runtime_api_max.")
            is_valid = False
        elif not version_in_range(runtime_api, runtime_min, runtime_max):
            print(
                f"  [ERROR] Runtime API {runtime_api} not supported by pack "
                f"(supports {runtime_min}..{runtime_max})."
            )
            is_valid = False
            
    # 3. Dictionary sections
    dict_sections = ["ui_strings", "lexicon", "style_tokens", "icon_tokens"]
    for section in dict_sections:
        if section in pack:
            if not isinstance(pack[section], dict):
                print(f"  [ERROR] Field '{section}' must be an object (dictionary).")
                is_valid = False
                continue
                
            ref_section = reference_pack.get(section, {})
            pack_section = pack[section]
            
            # Check for unknown keys (warnings)
            for key in pack_section:
                if key not in ref_section:
                    print(f"  [WARN] Unknown key '{key}' in section '{section}'. This will be ignored.")
            
            # Strict mode: check for missing keys
            if strict:
                for ref_key in ref_section:
                    if ref_key not in pack_section:
                        print(f"  [ERROR] Strict mode: Missing key '{ref_key}' in section '{section}'.")
                        is_valid = False
                        
    if is_valid:
        print(f"  [OK] {target_path.name} is valid.")
    else:
        print(f"  [FAIL] {target_path.name} failed validation.")
        
    return is_valid

def export_pack(
    target_path: Path,
    output_dir: Path,
    reference_pack: dict,
    runtime_api: str = CURRENT_RUNTIME_API,
    require_compat: bool = True,
):
    if not validate_pack(
        target_path,
        reference_pack,
        strict=False,
        runtime_api=runtime_api,
        require_compat=require_compat,
    ):
        print("Export failed due to validation errors.")
        return False
        
    os.makedirs(output_dir, exist_ok=True)
    out_file = output_dir / f"{target_path.stem}_export.json"
    
    # Normally we would bundle SVGs and zip it, but for v1 single-JSON themes, 
    # we just copy it and maybe minify.
    try:
        pack = load_json(target_path)
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(pack, f, separators=(",", ":"))
        print(f"Exported pack to {out_file}")
        return True
    except Exception as e:
        print(f"Export failed: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Toolkit for MUD Theme Packs.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    val_parser = subparsers.add_parser("validate", help="Validate a theme pack.")
    val_parser.add_argument("target", nargs="?", default="client/themes", help="Path to JSON file or directory.")
    val_parser.add_argument("--strict", action="store_true", help="Enforce 100% key coverage matching default.json.")
    val_parser.add_argument("--reference", default=str(DEFAULT_THEME_PATH), help="Path to the reference pack.")
    val_parser.add_argument("--runtime-api", default=CURRENT_RUNTIME_API, help="Runtime API version to validate against.")
    val_parser.add_argument("--allow-missing-compat", action="store_true", help="Downgrade missing compatibility fields to warnings.")
    
    exp_parser = subparsers.add_parser("export", help="Validate and export a theme pack for distribution.")
    exp_parser.add_argument("target", help="Path to JSON file.")
    exp_parser.add_argument("--out", default="dist/packs", help="Output directory.")
    exp_parser.add_argument("--reference", default=str(DEFAULT_THEME_PATH), help="Path to the reference pack.")
    exp_parser.add_argument("--runtime-api", default=CURRENT_RUNTIME_API, help="Runtime API version to validate against.")
    exp_parser.add_argument("--allow-missing-compat", action="store_true", help="Downgrade missing compatibility fields to warnings.")
    
    args = parser.parse_args()
    
    ref_path = Path(args.reference)
    if not ref_path.exists():
        print(f"Error: Reference pack not found at {ref_path}.")
        sys.exit(1)
        
    reference_pack = load_json(ref_path)
    
    if args.command == "validate":
        target_path = Path(args.target)
        targets = []
        if target_path.is_file() and target_path.suffix == ".json":
            targets.append(target_path)
        elif target_path.is_dir():
            targets.extend(target_path.glob("*.json"))
            
        all_valid = True
        for p in targets:
            if not validate_pack(
                p,
                reference_pack,
                args.strict,
                runtime_api=args.runtime_api,
                require_compat=(not args.allow_missing_compat),
            ):
                all_valid = False
                
        sys.exit(0 if all_valid else 1)
        
    elif args.command == "export":
        target_path = Path(args.target)
        if not target_path.is_file():
            print(f"Error: Target must be a file for export: {target_path}")
            sys.exit(1)
            
        out_dir = Path(args.out)
        success = export_pack(
            target_path,
            out_dir,
            reference_pack,
            runtime_api=args.runtime_api,
            require_compat=(not args.allow_missing_compat),
        )
        sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
