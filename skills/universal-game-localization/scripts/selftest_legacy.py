#!/usr/bin/env python3
"""Fast regression tests for the Outlast legacy-RTL and VCDIFF helpers."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PY = sys.executable


def run(*args, expect=0):
    result = subprocess.run([PY, *map(str, args)], capture_output=True, text=True,
                            encoding="utf-8", timeout=30)
    if result.returncode != expect:
        raise AssertionError(
            f"{args[0]} exit {result.returncode} (expected {expect})\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result.stdout


def vi(number: int) -> bytes:
    parts = [number & 0x7F]
    number >>= 7
    while number:
        parts.append(0x80 | (number & 0x7F))
        number >>= 7
    return bytes(reversed(parts))


def make_delta(source_type, source_length, source_position, target_bytes,
               data_section, instruction_section, address_section, checksum_after=True):
    target_length = len(target_bytes)
    prefix = (vi(target_length) + b"\x00" + vi(len(data_section)) +
              vi(len(instruction_section)) + vi(len(address_section)))
    checksum = (zlib.adler32(target_bytes) & 0xFFFFFFFF).to_bytes(4, "big")
    sections = data_section + instruction_section + address_section
    body = prefix + (sections + checksum if checksum_after else checksum + sections)
    source_flag = {"source": 0x01, "target": 0x02, "none": 0x00}[source_type]
    indicator = source_flag | 0x04
    window = bytes([indicator])
    if source_type in ("source", "target"):
        window += vi(source_length) + vi(source_position)
    return b"\xd6\xc3\xc4\x00\x00" + window + vi(len(body)) + body


def main():
    for name in ("arabic_legacy.py", "arabic_lint.py", "vcdiff_decode.py"):
        run(HERE / name, "--help")

    with tempfile.TemporaryDirectory(prefix="ugl-legacy-test-") as temp:
        temp = Path(temp)
        logical = temp / "logical.txt"
        visual = temp / "visual.txt"
        back = temp / "back.txt"
        expected = "ملاحظاتك في دفترك"
        logical.write_text(expected, encoding="utf-8")
        run(HERE / "arabic_legacy.py", "to-visual", logical, "--out", visual, "--utf16")
        visual_text = visual.read_bytes().decode("utf-16le")
        assert visual_text != expected
        assert all(0xFE70 <= ord(ch) <= 0xFEFF or ch == " " for ch in visual_text)
        run(HERE / "arabic_legacy.py", "to-logical", visual, "--out", back)
        assert back.read_text(encoding="utf-8") == expected

        # PUA is presentation-form minus 0xDE6 (F09A -> FE80).
        run(HERE / "arabic_legacy.py", "to-visual", logical, "--out", temp / "pua.txt",
            "--pua", "0xDE6")
        pua_text = (temp / "pua.txt").read_text(encoding="utf-8")
        assert any(0xF000 <= ord(ch) <= 0xF8FF for ch in pua_text)
        sys.path.insert(0, str(HERE))
        import arabic_legacy as AL
        assert AL.pua_to_form("\uf09a", 0xDE6) == "\ufe80"

        # Output protection: same-as-input is forbidden; existing output needs --force.
        run(HERE / "arabic_legacy.py", "to-logical", visual, "--out", visual, expect=1)
        run(HERE / "arabic_legacy.py", "to-logical", visual, "--out", back, expect=1)
        run(HERE / "arabic_legacy.py", "to-logical", visual, "--out", back, "--force")
        assert visual.read_bytes().decode("utf-16le") == visual_text

        bad_json = temp / "bad.json"
        bad_json.write_text(json.dumps({"entries": [
            {"id": "bad", "original": "Press {0}", "translation": "إضغط {0}"}
        ]}, ensure_ascii=False), encoding="utf-8")
        run(HERE / "arabic_lint.py", bad_json, expect=1)
        good_json = temp / "good.json"
        good_json.write_text(json.dumps({"entries": [
            {"id": "good", "original": "Press {0}", "translation": "اضغط {0}"}
        ]}, ensure_ascii=False), encoding="utf-8")
        run(HERE / "arabic_lint.py", good_json)

        evidence = ROOT / "evidence"
        if (evidence / "_arabic_corpus.json").is_file():
            corpus_report = run(HERE / "arabic_lint.py", evidence / "_arabic_corpus.json", "--max", "0")
            assert "5259 strings, 0 error(s), 28 warning(s)" in corpus_report, corpus_report

        # The private audit bundle includes Outlast fixtures; installable skill ZIPs do not.
        # When fixtures are present, re-run the real source MD5 and Adler-32 proof.
        if (evidence / "r_007.delta").is_file() and (evidence / "OLGame.int").is_file():
            outlast_report = run(HERE / "vcdiff_decode.py", "decode", evidence / "r_007.delta",
                                 "--source", evidence / "OLGame.int",
                                 "--expect-md5", "09c420931bbe509803a688204bb2080a")
            assert "ADLER-32 MATCH" in outlast_report and "MD5 MATCH" in outlast_report
        if (evidence / "r_010.delta").is_file():
            partial = run(HERE / "vcdiff_decode.py", "decode", evidence / "r_010.delta")
            assert "37.0%" in partial and "ADLER-32 NOT VERIFIED" in partial

        # Non-zero VCD_SOURCE position, standard checksum-after layout.
        positioned = make_delta("source", 3, 2, b"cde", b"", bytes([19, 3]), b"\x00")
        positioned_path = temp / "positioned.delta"
        positioned_path.write_bytes(positioned)
        source_path = temp / "source.bin"
        source_path.write_bytes(b"abcdef")
        report = run(HERE / "vcdiff_decode.py", "decode", positioned_path, "--source", source_path,
                     "--expect-md5", hashlib.md5(b"cde").hexdigest())
        assert "ADLER-32 MATCH" in report and "MD5 MATCH" in report

        # Overlapping target COPY must repeat bytes, not copy a truncated slice.
        overlap = make_delta("none", 0, 0, b"aaaaaa", b"a", bytes([2, 19, 5]), b"\x00")
        overlap_path = temp / "overlap.delta"
        overlap_path.write_bytes(overlap)
        overlap_out = temp / "overlap.bin"
        run(HERE / "vcdiff_decode.py", "decode", overlap_path, "--out", overlap_out)
        assert overlap_out.read_bytes() == b"aaaaaa"

        # Unknown bytes must remain unknown when a later VCD_TARGET window copies them.
        first = make_delta("source", 3, 0, b"abc", b"", bytes([19, 3]), b"\x00")
        second = make_delta("target", 3, 0, b"abc", b"", bytes([19, 3]), b"\x00")
        chained = temp / "chained-target.delta"
        chained.write_bytes(first + second[5:])
        chained_report = run(HERE / "vcdiff_decode.py", "decode", chained)
        assert "unknown-source=6" in chained_report and "readable without source: 0.0%" in chained_report

        # A corrupted Adler-32 is a hard failure (exit code 2).
        damaged = temp / "damaged.delta"
        damaged.write_bytes(positioned[:-1] + bytes([positioned[-1] ^ 1]))
        bad_output = temp / "must-not-write-bad-checksum.bin"
        run(HERE / "vcdiff_decode.py", "decode", damaged, "--source", source_path,
            "--out", bad_output, expect=2)
        assert not bad_output.exists()

        # Decoder may not overwrite its source, and existing outputs require --force.
        run(HERE / "vcdiff_decode.py", "decode", positioned_path, "--source", source_path,
            "--out", source_path, expect=1)
        run(HERE / "vcdiff_decode.py", "decode", positioned_path, "--source", source_path,
            "--out", overlap_out, expect=1)
        run(HERE / "vcdiff_decode.py", "decode", positioned_path, "--source", source_path,
            "--out", overlap_out, "--force")
        assert source_path.read_bytes() == b"abcdef"

        # A symlink output path is refused (where symlink creation is supported).
        symlink = temp / "output-link.bin"
        try:
            symlink.symlink_to(overlap_out)
        except (OSError, NotImplementedError):
            pass
        else:
            run(HERE / "vcdiff_decode.py", "decode", positioned_path, "--source", source_path,
                "--out", symlink, expect=1)

    print("LEGACY RTL + VCDIFF SELFTEST PASSED")


if __name__ == "__main__":
    main()
