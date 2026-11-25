#!/usr/bin/env python3
"""Verify MANIFEST.sha256 exactly covers every regular file in this skill bundle."""
from __future__ import annotations
import argparse, hashlib, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/"MANIFEST.sha256"

def skipped(path:Path)->bool:
    """Bytecode caches are build artefacts, never part of the package."""
    return "__pycache__" in path.relative_to(ROOT).parts or path.suffix==".pyc"

def main()->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write",action="store_true",help="regenerate the manifest from this skill bundle")
    args=parser.parse_args()
    if MANIFEST.is_symlink():
        print("MANIFEST UNSAFE",file=sys.stderr)
        return 1
    if args.write:
        entries=[]
        for path in sorted(ROOT.rglob("*")):
            if path==MANIFEST or path.is_dir() or skipped(path): continue
            if path.is_symlink() or not path.is_file():
                print(f"unsafe entry: {path.relative_to(ROOT)}",file=sys.stderr)
                return 1
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            entries.append(f"{digest}  {path.relative_to(ROOT).as_posix()}")
        MANIFEST.write_text("\n".join(entries)+"\n",encoding="utf-8")
        print(f"MANIFEST WRITTEN ({len(entries)} files)")
    if not MANIFEST.is_file():
        print("MANIFEST MISSING",file=sys.stderr)
        return 1
    expected={}
    try:
        for line_number,line in enumerate(MANIFEST.read_text(encoding="utf-8").splitlines(),1):
            if not line.strip(): continue
            parts=line.split("  ",1)
            if len(parts)!=2 or len(parts[0])!=64:
                raise ValueError(f"malformed entry on line {line_number}")
            digest,rel=parts
            path=Path(rel)
            if path.is_absolute() or ".." in path.parts or rel in expected:
                raise ValueError(f"unsafe/duplicate path on line {line_number}: {rel}")
            expected[rel]=digest.lower()
    except (OSError,UnicodeError,ValueError) as exc:
        print(f"MANIFEST INVALID: {exc}",file=sys.stderr)
        return 1
    actual=set()
    errors=[]
    for path in ROOT.rglob("*"):
        if path==MANIFEST or path.is_dir() or skipped(path): continue
        rel=path.relative_to(ROOT).as_posix()
        if path.is_symlink() or not path.is_file():
            errors.append(f"unsafe entry: {rel}")
            continue
        actual.add(rel)
        if rel not in expected:
            errors.append(f"unlisted file: {rel}")
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected[rel]:
            errors.append(f"hash mismatch: {rel}")
    for rel in sorted(set(expected)-actual):
        errors.append(f"missing file: {rel}")
    if errors:
        print("MANIFEST FAILED")
        for error in errors[:30]: print(f"  {error}")
        return 1
    print(f"MANIFEST PASSED ({len(actual)} files)")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
