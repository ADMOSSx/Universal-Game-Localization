#!/usr/bin/env python3
"""Small safety helpers shared by standalone localization utilities."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Iterable


class OutputSafetyError(ValueError):
    """Raised when a requested output could overwrite or redirect unsafe data."""


def _contains_symlink(path: Path) -> bool:
    """Return True when an existing component of path is a symlink."""
    path = Path(os.path.abspath(os.fspath(path)))
    parts = [path, *path.parents]
    for part in parts:
        try:
            if part.is_symlink():
                return True
        except OSError:
            return True
    return False


def safe_write_bytes(
    output: str | os.PathLike[str],
    data: bytes,
    *,
    inputs: Iterable[str | os.PathLike[str]] = (),
    force: bool = False,
) -> Path:
    """Atomically write output; never replace an input or follow output symlinks."""
    dest = Path(output)
    if not os.fspath(output).strip():
        raise OutputSafetyError("output path is empty")

    # Compare canonical destinations so ./x, ../dir/x and symlink aliases cannot
    # accidentally turn an input into an output.
    dest_abs = Path(os.path.abspath(os.fspath(dest)))
    dest_resolved = dest_abs.resolve(strict=False)
    protected = set()
    for item in inputs:
        try:
            protected.add(Path(item).resolve(strict=True))
        except FileNotFoundError:
            protected.add(Path(os.path.abspath(os.fspath(item))).resolve(strict=False))
    if dest_resolved in protected:
        raise OutputSafetyError("refusing to overwrite an input file; choose a separate workspace output")

    if _contains_symlink(dest_abs):
        raise OutputSafetyError("refusing to write through a symlink/junction path")

    parent = dest_abs.parent
    parent.mkdir(parents=True, exist_ok=True)
    if dest_abs.exists() and not force:
        raise OutputSafetyError(f"output already exists (use --force to replace it): {dest_abs}")
    if dest_abs.exists() and not dest_abs.is_file():
        raise OutputSafetyError("output exists and is not a regular file")

    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(prefix=f".{dest_abs.name}.", suffix=".tmp", dir=parent, delete=False) as f:
            temp_name = f.name
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_name, dest_abs)
        temp_name = None
    finally:
        if temp_name:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
    return dest_abs


def safe_write_text(
    output: str | os.PathLike[str],
    data: str,
    *,
    encoding: str = "utf-8",
    inputs: Iterable[str | os.PathLike[str]] = (),
    force: bool = False,
) -> Path:
    return safe_write_bytes(output, data.encode(encoding), inputs=inputs, force=force)
