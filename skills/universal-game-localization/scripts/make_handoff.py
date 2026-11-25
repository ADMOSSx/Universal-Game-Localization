#!/usr/bin/env python3
"""Build a validated, privacy-conscious manual translation handoff ZIP."""
from pathlib import Path, PurePosixPath
import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DIRS = ["translation_batches"]
BATCH_RE = re.compile(r"batch_\d{4}\.json\Z")
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
BLOCK_EXTS = {
    ".exe", ".dll", ".so", ".dylib", ".msi", ".pak", ".ucas", ".utoc", ".upk", ".vpk", ".pck",
    ".rpa", ".bsa", ".ba2", ".bundle", ".assets", ".arc", ".bin", ".dat", ".zip", ".7z",
    ".rar", ".iso", ".bik", ".mp4", ".wav", ".ogg", ".locres", ".locmeta", ".mo", ".esm", ".esp",
    ".rgss3a", ".rgss2a", ".rgssad", ".wad",
}
SECRET_GLOBS = [".env*", "*.pem", "*.key", "id_rsa*", "credentials*", "*.pfx", "*token*", "*secret*"]
SECRET_CONTENT_RE = re.compile(
    rb"(?i)(api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[:=]\s*[\x27\x22]?[A-Za-z0-9_./+=-]{12,}"
)
PATH_KEYS = {
    "root", "game_dir", "source_root", "game_path", "source_path", "source_folder",
    "workspace_path", "project_path", "input", "workspace",
}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inside(path, parent):
    try:
        Path(path).resolve().relative_to(Path(parent).resolve())
        return True
    except ValueError:
        return False


def contains_symlink(path):
    current = Path(path).absolute()
    return any(part.is_symlink() for part in (current, *current.parents)
               if part.exists() or part.is_symlink())


def contains_secret_content(path, chunk_size=1 << 20):
    overlap = b""
    with Path(path).open("rb") as stream:
        while True:
            chunk = stream.read(chunk_size)
            if not chunk:
                return False
            data = overlap + chunk
            if SECRET_CONTENT_RE.search(data):
                return True
            overlap = data[-512:]


def blocked(path, max_bytes):
    if path.is_symlink():
        return "symbolic link"
    if path.suffix.lower() in BLOCK_EXTS:
        return "blocked extension"
    if any(fnmatch.fnmatch(path.name.lower(), pattern) for pattern in SECRET_GLOBS):
        return "looks like a secret"
    try:
        if path.stat().st_size > max_bytes:
            return "larger than --max-file-mb"
        # Hash-verified translation batches are game text ("password: ..." can be dialogue);
        # scanning them would abort the whole package. Everything else is still scanned.
        if not BATCH_RE.fullmatch(path.name) and contains_secret_content(path):
            return "possible embedded credential"
    except OSError as exc:
        return f"unreadable: {exc}"
    return ""


def is_absolute_local_path(value):
    if not isinstance(value, str):
        return False
    return (
        Path(value).is_absolute()
        or bool(re.match(r"^[A-Za-z]:[\\/]", value))
        or value.startswith("\\\\")
    )


def sanitize_json_paths(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False

    def visit(value):
        if isinstance(value, dict):
            for key, item in list(value.items()):
                if str(key).lower() in PATH_KEYS and is_absolute_local_path(item):
                    value[key] = "<LOCAL_PATH_REDACTED>"
                else:
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(data)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def sanitize_project_paths(path):
    try:
        original = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False
    output = []
    for line in original.splitlines():
        if line.lower().startswith(("workspace / source path:", "game path:", "source path:")):
            line = line.split(":", 1)[0] + ": <LOCAL_PATH_REDACTED>"
        output.append(line)
    path.write_text("\n".join(output) + ("\n" if original.endswith("\n") else ""), encoding="utf-8")
    return True


def valid_package_marker(data):
    return isinstance(data, dict) and data.get("format") == "ADMOSS_HANDOFF_PACKAGE" and data.get("version") == 1


def valid_manifest_items(manifest):
    items = manifest.get("files", [])
    if not isinstance(items, list):
        return None
    names = []
    for item in items:
        if not isinstance(item, dict):
            return None
        name, digest = item.get("file"), item.get("sha256")
        if not isinstance(name, str) or not isinstance(digest, str) or not SHA_RE.fullmatch(digest):
            return None
        rel = PurePosixPath(name)
        if rel.is_absolute() or not rel.parts or any(part in ("", ".", "..") for part in rel.parts) or "\\" in name:
            return None
        names.append(name)
    if len(names) != len(set(names)):
        return None
    return items


def required_package_files():
    return {
        "ADMOSS_HANDOFF_PACKAGE.json",
        "README_FIRST.md",
        "MASTER_INSTRUCTIONS.md",
        "translator/GUIDE.md",
        "translation_batches/BATCH_MANIFEST.json",
    }


def verified_package_dir(path):
    marker = path / "ADMOSS_HANDOFF_PACKAGE.json"
    manifest_path = path / "HANDOFF_MANIFEST.json"
    if (not path.is_dir() or path.is_symlink() or marker.is_symlink() or manifest_path.is_symlink()
            or not marker.is_file() or not manifest_path.is_file()):
        return False
    try:
        if not valid_package_marker(json.loads(marker.read_text(encoding="utf-8"))):
            return False
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        items = valid_manifest_items(manifest)
        if items is None:
            return False
        names = {item["file"] for item in items}
        if not required_package_files().issubset(names):
            return False
        expected = names | {"HANDOFF_MANIFEST.json", "CHECKSUMS.sha256"}
        actual = set()
        for item_path in path.rglob("*"):
            if item_path.is_symlink():
                return False
            if item_path.is_file():
                actual.add(item_path.relative_to(path).as_posix())
        if actual != expected:
            return False
        for item in items:
            target = path.joinpath(*PurePosixPath(item["file"]).parts)
            if contains_symlink(target) or not inside(target, path) or not target.is_file():
                return False
            if target.stat().st_size != item.get("size") or sha256(target) != item["sha256"]:
                return False
        return True
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False


def verified_package_zip(path, package_name):
    try:
        with zipfile.ZipFile(path) as archive:
            names_in_zip = archive.namelist()
            if archive.testzip() or len(names_in_zip) != len(set(names_in_zip)):
                return False
            prefix = package_name + "/"
            marker = json.loads(archive.read(prefix + "ADMOSS_HANDOFF_PACKAGE.json").decode("utf-8"))
            manifest = json.loads(archive.read(prefix + "HANDOFF_MANIFEST.json").decode("utf-8"))
            if not valid_package_marker(marker):
                return False
            items = valid_manifest_items(manifest)
            if items is None:
                return False
            names = {item["file"] for item in items}
            if not required_package_files().issubset(names):
                return False
            expected = {prefix + name for name in names | {"HANDOFF_MANIFEST.json", "CHECKSUMS.sha256"}}
            if set(names_in_zip) != expected:
                return False
            for item in items:
                member = prefix + item["file"]
                data = archive.read(member)
                if len(data) != item.get("size") or hashlib.sha256(data).hexdigest() != item["sha256"]:
                    return False
            return True
    except (OSError, KeyError, ValueError, zipfile.BadZipFile, json.JSONDecodeError):
        return False


def load_batch_inputs(workspace):
    """Require a complete, hash-matched batch set and its exact normalized source."""
    batch_dir = workspace / "translation_batches"
    manifest_path = batch_dir / "BATCH_MANIFEST.json"
    if batch_dir.is_symlink() or manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("translation_batches/BATCH_MANIFEST.json is missing; create translation batches first.")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read BATCH_MANIFEST.json: {exc}") from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("batches"), list):
        raise ValueError("BATCH_MANIFEST.json has an invalid batches list.")
    declared = manifest["batches"]
    if not declared or int(manifest.get("total_entries", 0)) < 1:
        raise ValueError("No translation entries were found in the batch manifest.")
    if manifest.get("total_batches", len(declared)) != len(declared):
        raise ValueError("BATCH_MANIFEST total_batches does not match its batch list.")

    declared_names = []
    ids = set()
    covered = 0
    for item in declared:
        if not isinstance(item, dict):
            raise ValueError("Malformed batch manifest entry.")
        name = item.get("file")
        if not isinstance(name, str) or not BATCH_RE.fullmatch(name) or name in declared_names:
            raise ValueError(f"Invalid or duplicate batch filename in manifest: {name!r}")
        declared_names.append(name)
        batch_path = batch_dir / name
        if batch_path.is_symlink() or not batch_path.is_file():
            raise ValueError(f"Missing or unsafe translation batch: {name}")
        if not isinstance(item.get("sha256"), str) or sha256(batch_path) != item["sha256"]:
            raise ValueError(f"Batch checksum mismatch: {name}")
        try:
            payload = json.loads(batch_path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid JSON in {name}: {exc}") from exc
        entries = payload.get("entries") if isinstance(payload, dict) else None
        if not isinstance(entries, list) or not entries:
            raise ValueError(f"{name} has no entries list.")
        if len(entries) != item.get("count"):
            raise ValueError(f"Batch entry count mismatch: {name}")
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not entry["id"]:
                raise ValueError(f"Invalid entry or missing ID in {name}.")
            if not isinstance(entry.get("original"), str):
                raise ValueError(f"Missing/non-string original text in {name}.")
            if entry["id"] in ids:
                raise ValueError(f"Duplicate entry ID across batches: {entry['id']}")
            ids.add(entry["id"])
            covered += 1

    actual_names = sorted(path.name for path in batch_dir.iterdir() if BATCH_RE.fullmatch(path.name))
    if sorted(declared_names) != actual_names:
        raise ValueError("Actual batch files do not exactly match BATCH_MANIFEST.json.")
    if covered != manifest.get("total_entries"):
        raise ValueError(f"Batch coverage mismatch: {covered} entries vs manifest {manifest.get('total_entries')}.")

    source_name = str(manifest.get("input", "")).replace("\\", "/").rsplit("/", 1)[-1]
    if not source_name.lower().endswith(".json") or source_name in {"", ".", ".."}:
        raise ValueError("Batch manifest must point to a JSON source file under normalized/.")
    source_path = workspace / "normalized" / source_name
    if contains_symlink(source_path) or not source_path.is_file():
        raise ValueError(f"Normalized source is missing: normalized/{source_name}")
    expected_source_hash = manifest.get("input_sha256")
    if not isinstance(expected_source_hash, str) or sha256(source_path) != expected_source_hash:
        raise ValueError("Normalized source SHA-256 does not match BATCH_MANIFEST.json.")
    try:
        source_data = json.loads(source_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read normalized source: {exc}") from exc
    if not isinstance(source_data, dict):
        raise ValueError("Normalized source must be a JSON object.")
    source_entries = source_data.get("entries")
    project = source_data.get("project", {}) or {}
    if not isinstance(source_entries, list) or not isinstance(project, dict):
        raise ValueError("Normalized source needs an entries list and a project object.")
    source_ids = {entry.get("id") for entry in source_entries if isinstance(entry, dict)}
    if len(source_ids) != len(source_entries) or source_ids != ids:
        raise ValueError("Batch IDs do not exactly match the normalized source IDs.")
    return manifest, project, len(declared), covered


def render_placeholders(template, values):
    for key, value in values.items():
        template = template.replace("{" + key + "}", str(value))
    return template


def project_values(project, manifest):
    return {
        "GAME_TITLE": project.get("game_title") or "Unknown game",
        "GAME_VERSION": project.get("game_version") or "Unknown",
        "ENGINE": project.get("engine") or "Not recorded",
        "SOURCE_LANGUAGE": project.get("source_language") or "Unknown",
        "TARGET_LANGUAGE": project.get("target_language") or "Unknown",
        "BATCH_COUNT": manifest.get("total_batches", len(manifest.get("batches", []))),
        "ENTRY_COUNT": manifest.get("total_entries", "Unknown"),
    }


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", help="localization workspace folder")
    parser.add_argument("--out", default="", help="output folder (default: <workspace>/HANDOFF_PACKAGE)")
    parser.add_argument("--max-file-mb", type=float, default=25.0)
    parser.add_argument("--force", action="store_true", help="replace a previously generated package only")
    args = parser.parse_args()

    workspace_arg = Path(args.workspace)
    if workspace_arg.is_symlink():
        raise SystemExit("Workspace must not be a symbolic link.")
    workspace = workspace_arg.resolve()
    if not workspace.is_dir():
        raise SystemExit(f"Workspace not found: {workspace}")
    try:
        batch_manifest, project, batch_count, entry_count = load_batch_inputs(workspace)
    except (OSError, TypeError, ValueError) as exc:
        raise SystemExit(f"Handoff preflight failed: {exc}")

    output_arg = Path(args.out) if args.out else workspace / "HANDOFF_PACKAGE"
    if contains_symlink(output_arg):
        raise SystemExit("Output path contains a symbolic link.")
    output = output_arg.resolve()
    if output == workspace or inside(workspace, output):
        raise SystemExit("Refusing to use the workspace or one of its ancestors as package output.")
    default_output = (workspace / "HANDOFF_PACKAGE").resolve()
    if inside(output, workspace) and output != default_output:
        raise SystemExit("When output is inside the workspace, only <workspace>/HANDOFF_PACKAGE is allowed.")
    if args.max_file_mb <= 0:
        raise SystemExit("--max-file-mb must be greater than zero.")

    zip_path = output.with_suffix(".zip")
    if output.exists():
        if not args.force:
            raise SystemExit(f"{output} exists. Use --force to replace a verified handoff package.")
        if not verified_package_dir(output):
            raise SystemExit("Refusing to delete an existing directory that is not a verified handoff package.")
    if zip_path.exists() or zip_path.is_symlink():
        if not args.force:
            raise SystemExit(f"{zip_path} exists. Use --force to replace a verified generated ZIP.")
        if zip_path.is_symlink() or not zip_path.is_file() or not verified_package_zip(zip_path, output.name):
            raise SystemExit("Refusing to replace a ZIP that is not a verified ADMOSS handoff package.")

    max_bytes = int(args.max_file_mb * 1024 * 1024)
    directories = DEFAULT_DIRS
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix=".handoff-build-", dir=output.parent))
    staged = temp_root / output.name
    staged.mkdir()
    copied, skipped = [], []
    values = project_values(project, batch_manifest)
    try:
        allowed_batch_files = {"BATCH_MANIFEST.json"} | {
            item["file"] for item in batch_manifest["batches"]
        }
        for dirname in directories:
            base = workspace / dirname
            if not base.is_dir() or base.is_symlink():
                continue
            for directory, dirnames, filenames in os.walk(base, topdown=True, followlinks=False):
                current = Path(directory)
                dirnames[:] = [name for name in dirnames if not (current / name).is_symlink()]
                if dirname == "translation_batches" and current != base:
                    skipped.append({"file": current.relative_to(workspace).as_posix(),
                                     "reason": "unexpected nested directory in verified batch folder"})
                    dirnames[:] = []
                    continue
                for filename in sorted(filenames):
                    source = current / filename
                    rel = source.relative_to(workspace)
                    if dirname == "translation_batches" and filename not in allowed_batch_files:
                        skipped.append({"file": rel.as_posix(), "reason": "not listed in verified batch manifest"})
                        continue
                    if rel.as_posix() == "translator/MASTER_TRANSLATION_PROMPT.md":
                        continue
                    if source.is_symlink():
                        skipped.append({"file": rel.as_posix(), "reason": "symbolic link"})
                        continue
                    reason = blocked(source, max_bytes)
                    if reason:
                        skipped.append({"file": rel.as_posix(), "reason": reason})
                        continue
                    destination = staged / rel
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
                    if destination.name in {"files.json", "INVENTORY_SUMMARY.json", "BATCH_MANIFEST.json"} and destination.suffix.lower() == ".json":
                        if not sanitize_json_paths(destination):
                            raise SystemExit(f"Could not safely sanitize local paths in {rel}")
                    if destination.name == "PROJECT.md":
                        if not sanitize_project_paths(destination):
                            raise SystemExit(f"Could not safely sanitize local paths in {rel}")
                    copied.append(rel.as_posix())

        expected_batch_names = {item["file"] for item in batch_manifest["batches"]}
        copied_batch_names = {
            PurePosixPath(name).name for name in copied
            if name.startswith("translation_batches/") and BATCH_RE.fullmatch(PurePosixPath(name).name)
        }
        if copied_batch_names != expected_batch_names:
            missing = sorted(expected_batch_names - copied_batch_names)
            raise SystemExit(f"Refusing to create an incomplete handoff package; declared batches excluded: {missing}")
        if "translation_batches/BATCH_MANIFEST.json" not in copied:
            raise SystemExit("Refusing to create a handoff package without its batch manifest.")

        guide_source = workspace / "translator" / "GUIDE.md"
        guide_path = staged / "translator" / "GUIDE.md"
        if contains_symlink(guide_source):
            raise SystemExit("translator/GUIDE.md or one of its parent paths is a symlink.")
        if guide_source.is_file():
            reason = blocked(guide_source, max_bytes)
            if reason:
                raise SystemExit(f"Unsafe translator/GUIDE.md: {reason}")
            if not guide_path.is_file():
                guide_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(guide_source, guide_path)
                copied.append("translator/GUIDE.md")
        elif not guide_path.is_file():
            guide_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SKILL_DIR / "templates" / "GUIDE_TEMPLATE.md", guide_path)
            copied.append("translator/GUIDE.md")

        master_source = workspace / "translator" / "MASTER_TRANSLATION_PROMPT.md"
        if contains_symlink(master_source):
            raise SystemExit("translator/MASTER_TRANSLATION_PROMPT.md or one of its parent paths is a symlink.")
        if master_source.is_file():
            reason = blocked(master_source, max_bytes)
            if reason:
                raise SystemExit(f"Unsafe custom master translation prompt: {reason}")
        else:
            master_source = SKILL_DIR / "templates" / "MASTER_TRANSLATION_PROMPT.md"
        rules_source = SKILL_DIR / "references" / "external-ai-handoff-rules.md"
        master_text = render_placeholders(master_source.read_text(encoding="utf-8"), values)
        rules_text = rules_source.read_text(encoding="utf-8")
        master_path = staged / "MASTER_INSTRUCTIONS.md"
        master_path.write_text(master_text.rstrip() + "\n\n---\n\n" + rules_text, encoding="utf-8")
        copied.append("MASTER_INSTRUCTIONS.md")

        readme_source = workspace / "README_FIRST.md"
        if contains_symlink(readme_source):
            raise SystemExit("README_FIRST.md or one of its parent paths is a symlink.")
        if readme_source.is_file():
            reason = blocked(readme_source, max_bytes)
            if reason:
                raise SystemExit(f"Unsafe custom README_FIRST.md: {reason}")
        else:
            readme_source = SKILL_DIR / "templates" / "README_FIRST_TEMPLATE.md"
        readme_text = render_placeholders(readme_source.read_text(encoding="utf-8"), values)
        readme_path = staged / "README_FIRST.md"
        readme_path.write_text(readme_text, encoding="utf-8")
        copied.append("README_FIRST.md")

        marker = {
            "format": "ADMOSS_HANDOFF_PACKAGE",
            "version": 1,
            "game_title": values["GAME_TITLE"],
            "engine": values["ENGINE"],
            "source_language": values["SOURCE_LANGUAGE"],
            "target_language": values["TARGET_LANGUAGE"],
            "batch_count": batch_count,
            "entry_count": entry_count,
        }
        marker_path = staged / "ADMOSS_HANDOFF_PACKAGE.json"
        marker_path.write_text(json.dumps(marker, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        copied.append("ADMOSS_HANDOFF_PACKAGE.json")

        manifest_files = [
            {"file": name, "size": (staged / name).stat().st_size, "sha256": sha256(staged / name)}
            for name in sorted(set(copied))
        ]
        handoff_manifest = {
            "files": manifest_files,
            "skipped": skipped,
            "privacy": "Only translation batches and instructions are included. Absolute local source paths are redacted from the copied batch manifest; reports and normalized full-source files are excluded.",
            "translation": {
                "game_title": values["GAME_TITLE"],
                "source_language": values["SOURCE_LANGUAGE"],
                "target_language": values["TARGET_LANGUAGE"],
                "batch_count": batch_count,
                "entry_count": entry_count,
            },
        }
        (staged / "HANDOFF_MANIFEST.json").write_text(
            json.dumps(handoff_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (staged / "CHECKSUMS.sha256").write_text(
            "".join(f"{item['sha256']}  {item['file']}\n" for item in manifest_files), encoding="utf-8"
        )

        staged_zip = temp_root / (output.name + ".zip")
        with zipfile.ZipFile(staged_zip, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(staged.rglob("*")):
                if file.is_file() and not file.is_symlink():
                    archive.write(file, f"{output.name}/{file.relative_to(staged).as_posix()}")
        if not verified_package_dir(staged):
            raise SystemExit("Generated handoff directory failed its manifest verification.")
        if not verified_package_zip(staged_zip, output.name):
            raise SystemExit("Generated handoff ZIP failed its manifest verification.")

        if output.exists():
            shutil.rmtree(output)
        if zip_path.exists():
            zip_path.unlink()
        os.replace(staged, output)
        os.replace(staged_zip, zip_path)
        print(f"Package: {output}")
        print(f"ZIP: {zip_path} ({zip_path.stat().st_size / 1048576:.1f} MB) - integrity verified")
        print(f"Translation set: {entry_count} entries in {batch_count} batch(es)")
        print(f"Files: {len(manifest_files)}; skipped: {len(skipped)}")
        for item in skipped[:8]:
            print(f"  skipped {item['file']} ({item['reason']})")
        print("No API key or paid API is needed. Use any chat AI you can access; its own limits still apply.")
        print("Upload order: README_FIRST.md, MASTER_INSTRUCTIONS.md, translator/GUIDE.md, then one or a few translation_batches/batch_NNNN.json files.")
        print("Keep returned files in a separate returned_1 folder; never overwrite the original batches.")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    main()
