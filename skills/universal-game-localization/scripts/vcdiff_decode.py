#!/usr/bin/env python3
"""Conservative RFC-3284 VCDIFF decoder for uncompressed default-code-table patches.

Supported:
  * standard VCDIFF magic/version with the default code table
  * checksum (Adler-32) before or after the data/instruction/address sections
  * VCD_SOURCE and VCD_TARGET source windows, including non-zero source positions
  * byte-level unknown-source propagation through chained target copies
  * gzip-wrapped deltas, ADD/RUN/COPY, NEAR/SAME caches and overlapping target copies

Intentionally rejected: custom code tables, non-zero header indicators, compressed
sections, and unknown/reserved flags. Unsupported data is never silently decoded.

Commands:
  info <delta> [...]
  decode <delta> [--source file] [--src-offset N] [--out file] [--prov file]
         [--expect-md5 hex] [--force]

Exit codes: 0 success, 1 malformed/unsupported/decode failure, 2 checksum or MD5
mismatch, 3 verification incomplete because source bytes were unavailable.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import os
import sys
import zlib
from pathlib import Path

from _safe_output import safe_write_bytes, OutputSafetyError

RUN, ADD, COPY, NOOP = 0, 1, 2, 3
MAGIC = b"\xd6\xc3\xc4"

# RFC 3284 section 5.6 default code table.
T = [None] * 256
T[0] = (RUN, 0, 0, NOOP, 0, 0)
for _size in range(18):
    T[1 + _size] = (ADD, _size, 0, NOOP, 0, 0)
for _mode in range(9):
    for _size in range(16):
        T[19 + _mode * 16 + _size] = (COPY, 0 if _size == 0 else _size + 3, _mode,
                                       NOOP, 0, 0)
_index = 163
for _mode in range(6):
    for _add_size in range(1, 5):
        for _copy_size in range(4, 7):
            T[_index] = (ADD, _add_size, 0, COPY, _copy_size, _mode)
            _index += 1
for _mode in (6, 7, 8):
    for _add_size in range(1, 5):
        T[_index] = (ADD, _add_size, 0, COPY, 4, _mode)
        _index += 1
for _mode in range(9):
    T[_index] = (COPY, 4, _mode, ADD, 1, 0)
    _index += 1
assert _index == 256 and all(entry is not None for entry in T)


def varint(data: bytes, offset: int):
    value = 0
    for count in range(10):
        if offset >= len(data):
            raise ValueError("truncated variable-length integer")
        byte = data[offset]
        offset += 1
        value = (value << 7) | (byte & 0x7F)
        if value > 0xFFFFFFFFFFFFFFFF:
            raise ValueError("variable-length integer exceeds 64-bit range")
        if not (byte & 0x80):
            return value, offset
    raise ValueError("variable-length integer is too long")


def load(path: str | os.PathLike[str]) -> bytes:
    raw = Path(path).read_bytes()
    if raw.startswith(b"\x1f\x8b"):
        try:
            return gzip.decompress(raw)
        except (OSError, EOFError) as exc:
            raise ValueError(f"invalid gzip-wrapped delta: {exc}") from exc
    return raw


def _parse_variant(data: bytes, checksum_before: bool):
    if not data.startswith(MAGIC):
        raise ValueError("not a VCDIFF file (bad magic)")
    if len(data) < 5:
        raise ValueError("truncated VCDIFF header")
    version = data[3]
    if version != 0:
        raise ValueError(f"unsupported VCDIFF version: {version}")
    header_indicator = data[4]
    if header_indicator != 0:
        raise ValueError(
            f"unsupported VCDIFF header indicator 0x{header_indicator:02x}; "
            "only the default code table without secondary compression is supported"
        )

    offset = 5
    windows = []
    while offset < len(data):
        window_start = offset
        indicator = data[offset]
        offset += 1
        if indicator & ~0x07:
            raise ValueError(f"reserved window-indicator bits set: 0x{indicator:02x}")
        source_type = indicator & 0x03
        if source_type == 0x03:
            raise ValueError("a VCDIFF window cannot use both VCD_SOURCE and VCD_TARGET")

        source_length = source_position = 0
        if source_type:
            source_length, offset = varint(data, offset)
            source_position, offset = varint(data, offset)

        delta_length, offset = varint(data, offset)
        delta_start = offset  # Delta_Encoding_Length counts bytes after its own varint.
        target_length, offset = varint(data, offset)
        if offset >= len(data):
            raise ValueError("truncated delta-encoding indicator")
        delta_indicator = data[offset]
        offset += 1
        if delta_indicator & ~0x07:
            raise ValueError(f"reserved delta-indicator bits set: 0x{delta_indicator:02x}")
        if delta_indicator:
            raise ValueError(
                f"compressed VCDIFF sections are unsupported (Delta_Indicator=0x{delta_indicator:02x})"
            )

        data_length, offset = varint(data, offset)
        inst_length, offset = varint(data, offset)
        addr_length, offset = varint(data, offset)

        checksum = b""
        if indicator & 0x04 and checksum_before:
            if offset + 4 > len(data):
                raise ValueError("truncated Adler-32 checksum")
            checksum = data[offset:offset + 4]
            offset += 4

        if offset + data_length + inst_length + addr_length > len(data):
            raise ValueError("truncated VCDIFF data/instruction/address section")
        data_section = data[offset:offset + data_length]
        offset += data_length
        inst_section = data[offset:offset + inst_length]
        offset += inst_length
        addr_section = data[offset:offset + addr_length]
        offset += addr_length

        if indicator & 0x04 and not checksum_before:
            if offset + 4 > len(data):
                raise ValueError("truncated trailing Adler-32 checksum")
            checksum = data[offset:offset + 4]
            offset += 4

        expected_end = delta_start + delta_length
        if offset != expected_end:
            raise ValueError(
                f"window {len(windows)} delta length mismatch: declared {delta_length} bytes, "
                f"consumed {offset - delta_start}"
            )
        windows.append(dict(
            indicator=indicator,
            source_type=source_type,
            source_length=source_length,
            source_position=source_position,
            delta_length=delta_length,
            target_length=target_length,
            delta_indicator=delta_indicator,
            data=data_section,
            instructions=inst_section,
            addresses=addr_section,
            checksum=checksum,
            window_start=window_start,
        ))
        if offset <= window_start:
            raise ValueError("decoder made no progress while parsing windows")

    if not windows:
        raise ValueError("VCDIFF file contains no windows")
    return windows


def parse(data: bytes, checksum_before=None):
    """Parse windows, validating instruction streams to disambiguate checksum layout.

    Some vendor and standard files can be syntactically sliced at either location
    because the section lengths alone do not identify the checksum position. A
    candidate is accepted only if its decoded instruction/address streams are valid.
    """
    if checksum_before is not None:
        windows = _parse_variant(data, bool(checksum_before))
        return windows, len(data), "adler-before" if checksum_before else "adler-after"
    errors = []
    # RFC 3284 puts the checksum after the sections; a known legacy installer puts
    # it before. Prefer the standard layout, but reject it when its instruction
    # stream is malformed and try the vendor placement.
    for before in (False, True):
        try:
            windows = _parse_variant(data, before)
            decode(windows, source=b"")  # structural validation; source bytes may be absent
            return windows, len(data), "adler-before" if before else "adler-after"
        except ValueError as exc:
            errors.append(("adler-before" if before else "adler-after") + ": " + str(exc))
    raise ValueError("could not parse/decode VCDIFF windows: " + " | ".join(errors))


def decode_window(window, source_segment=b"", source_available=True, source_unknown_mask=b""):
    """Decode one window and track bytes whose source data was unavailable."""
    output = bytearray()
    provenance = bytearray()
    unknown_mask = bytearray()
    near_cache = [0] * 4
    same_cache = [0] * 768
    next_near = 0
    data_pos = inst_pos = addr_pos = 0
    data = window["data"]
    instructions = window["instructions"]
    addresses = window["addresses"]
    source_length = window["source_length"]
    stats = dict(add=0, run=0, copy=0, src_copy=0, tgt_copy=0, bad=0)
    unknown_source_bytes = 0

    while inst_pos < len(instructions):
        opcode = instructions[inst_pos]
        inst_pos += 1
        entry = T[opcode]
        for kind, size, mode in ((entry[0], entry[1], entry[2]),
                                 (entry[3], entry[4], entry[5])):
            if kind == NOOP:
                continue
            if size == 0:
                size, inst_pos = varint(instructions, inst_pos)
            if size < 0:
                raise ValueError("negative instruction size")

            if kind == ADD:
                if data_pos + size > len(data):
                    raise ValueError("ADD instruction reads beyond the data section")
                output.extend(data[data_pos:data_pos + size])
                provenance.extend(b"A" * size)
                unknown_mask.extend(b"\x00" * size)
                data_pos += size
                stats["add"] += size

            elif kind == RUN:
                if size and data_pos >= len(data):
                    raise ValueError("RUN instruction reads beyond the data section")
                if size:
                    output.extend(bytes((data[data_pos],)) * size)
                    provenance.extend(b"R" * size)
                    unknown_mask.extend(b"\x00" * size)
                    data_pos += 1
                stats["run"] += size

            elif kind == COPY:
                here = source_length + len(output)
                if mode == 0:  # SELF
                    address, addr_pos = varint(addresses, addr_pos)
                elif mode == 1:  # HERE
                    distance, addr_pos = varint(addresses, addr_pos)
                    address = here - distance
                elif 2 <= mode <= 5:  # NEAR
                    delta, addr_pos = varint(addresses, addr_pos)
                    address = near_cache[mode - 2] + delta
                elif 6 <= mode <= 8:  # SAME
                    if addr_pos >= len(addresses):
                        raise ValueError("SAME address is missing its one-byte cache index")
                    index = (mode - 6) * 256 + addresses[addr_pos]
                    addr_pos += 1
                    address = same_cache[index]
                else:
                    raise ValueError(f"invalid COPY mode: {mode}")

                if address < 0 or address >= source_length + len(output):
                    raise ValueError(f"COPY address out of range: {address} (here={here})")

                if address < source_length:
                    if address + size <= len(source_segment):
                        chunk = source_segment[address:address + size]
                        output.extend(chunk)
                        if source_unknown_mask:
                            mask = source_unknown_mask[address:address + size]
                            if len(mask) != size:
                                raise ValueError("VCD_TARGET unknown-byte map is shorter than its source segment")
                            unknown_mask.extend(mask)
                            unknown_source_bytes += sum(mask)
                        else:
                            unknown_mask.extend(b"\x00" * size)
                    elif source_available:
                        raise ValueError("COPY reads beyond the declared source segment")
                    else:
                        available = source_segment[address:] if address < len(source_segment) else b""
                        missing = size - len(available)
                        output.extend(available)
                        output.extend(b"\x00" * missing)
                        unknown_mask.extend(b"\x01" * size)
                        unknown_source_bytes += size
                        stats["bad"] += 1
                    provenance.extend(b"S" * size)
                    stats["src_copy"] += size
                else:
                    target_pos = address - source_length
                    if target_pos < 0 or target_pos >= len(output):
                        raise ValueError("target COPY references bytes not yet produced")
                    # Byte-wise copying is required for overlapping copies.
                    for _ in range(size):
                        if target_pos >= len(output):
                            raise ValueError("overlapping target COPY ran beyond available output")
                        output.append(output[target_pos])
                        unknown_mask.append(unknown_mask[target_pos])
                        if unknown_mask[-1]:
                            unknown_source_bytes += 1
                        target_pos += 1
                    provenance.extend(b"T" * size)
                    stats["tgt_copy"] += size

                near_cache[next_near] = address
                same_cache[address % 768] = address
                next_near = (next_near + 1) % 4
                stats["copy"] += size
            else:
                raise ValueError(f"unsupported instruction type: {kind}")

            if len(output) > window["target_length"]:
                raise ValueError("window produced more bytes than its declared target length")

    if data_pos != len(data):
        raise ValueError(f"unused data-section bytes: consumed {data_pos}/{len(data)}")
    if addr_pos != len(addresses):
        raise ValueError(f"unused address-section bytes: consumed {addr_pos}/{len(addresses)}")
    if len(output) != window["target_length"]:
        raise ValueError(f"target window length mismatch: got {len(output)}, expected {window['target_length']}")
    return bytes(output), bytes(provenance), stats, bytes(unknown_mask), unknown_source_bytes


def decode(windows, source=b"", src_offset=0):
    """Decode windows and verify per-window Adler-32 where all source bytes are known."""
    complete_output = bytearray()
    complete_provenance = bytearray()
    complete_unknown_mask = bytearray()
    stats_by_window = {}
    checksum_results = []

    for index, window in enumerate(windows):
        source_type = window["source_type"]
        src_len = window["source_length"]
        src_pos = window["source_position"]
        if source_type == 0x01:  # VCD_SOURCE
            absolute_start = src_offset + src_pos
            absolute_end = absolute_start + src_len
            if absolute_start > len(source) or absolute_end > len(source):
                if source:
                    raise ValueError(
                        f"window {index} source range {absolute_start}:{absolute_end} "
                        f"exceeds provided source size {len(source)}"
                    )
                source_segment = b""
                source_available = False
            else:
                source_segment = source[absolute_start:absolute_end]
                source_available = bool(source)
        elif source_type == 0x02:  # VCD_TARGET
            if src_pos + src_len > len(complete_output):
                raise ValueError(
                    f"window {index} VCD_TARGET range {src_pos}:{src_pos + src_len} "
                    f"exceeds reconstructed target size {len(complete_output)}"
                )
            source_segment = bytes(complete_output[src_pos:src_pos + src_len])
            source_unknown_mask = bytes(complete_unknown_mask[src_pos:src_pos + src_len])
            source_available = True
        else:
            source_segment = b""
            source_unknown_mask = b""
            source_available = True

        if source_type == 0x01:
            source_unknown_mask = b""
        decoded, provenance, stats, unknown_mask, unknown = decode_window(
            window, source_segment, source_available=source_available,
            source_unknown_mask=source_unknown_mask
        )
        complete_output.extend(decoded)
        complete_provenance.extend(provenance)
        complete_unknown_mask.extend(unknown_mask)
        stats["unknown_source_bytes"] = unknown
        stats_by_window[index] = stats

        expected = int.from_bytes(window["checksum"], "big") if window["checksum"] else None
        if expected is None:
            checksum_results.append(None)
        elif unknown:
            checksum_results.append(None)
        else:
            actual = zlib.adler32(decoded) & 0xFFFFFFFF
            checksum_results.append(actual == expected)

    return bytes(complete_output), bytes(complete_provenance), stats_by_window, checksum_results


def cmd_info(args):
    for path in args.delta:
        data = load(path)
        windows, consumed, variant = parse(data, args.adler_first)
        print(f"{os.path.basename(path)}: {len(data)} bytes, {len(windows)} window(s), {variant}, "
              f"consumed {consumed}/{len(data)}")
        for number, window in enumerate(windows):
            checksum = int.from_bytes(window["checksum"], "big") if window["checksum"] else None
            checksum_text = f"{checksum:08x}" if checksum is not None else "none"
            print(f"  win{number}: source_type={window['source_type']} "
                  f"src={window['source_length']}@{window['source_position']} "
                  f"target={window['target_length']} data={len(window['data'])} "
                  f"inst={len(window['instructions'])} addr={len(window['addresses'])} "
                  f"adler={checksum_text}")
        print(f"  total target = {sum(w['target_length'] for w in windows)}")


def cmd_decode(args):
    delta_data = load(args.delta)
    windows, _, variant = parse(delta_data, args.adler_first)
    source_data = Path(args.source).read_bytes() if args.source else b""
    output, provenance, stats, checksum_results = decode(
        windows, source=source_data, src_offset=args.src_offset
    )
    totals = {key: sum(row[key] for row in stats.values()) for key in
              ("add", "run", "copy", "src_copy", "tgt_copy", "bad", "unknown_source_bytes")}
    target_expected = sum(window["target_length"] for window in windows)
    known = totals["add"] + totals["run"] + totals["tgt_copy"] + (totals["src_copy"] - totals["unknown_source_bytes"])
    print(f"{os.path.basename(args.delta)}: {variant}, {len(windows)} window(s)")
    print(f"  target {len(output)}/{target_expected}  ADD={totals['add']} RUN={totals['run']} "
          f"SRC-COPY={totals['src_copy']} TGT-COPY={totals['tgt_copy']} "
          f"unknown-source={totals['unknown_source_bytes']}")
    print(f"  readable without source: {100.0 * known / max(1, len(output)):.1f}%")

    checksum_failed = False
    checksum_unknown = False
    for index, result in enumerate(checksum_results):
        if result is False:
            checksum_failed = True
            print(f"  window {index}: ADLER-32 MISMATCH")
        elif result is None and windows[index]["checksum"]:
            checksum_unknown = True
            print(f"  window {index}: ADLER-32 NOT VERIFIED (source bytes unavailable)")
        elif result is True:
            print(f"  window {index}: ADLER-32 MATCH")

    complete = totals["unknown_source_bytes"] == 0
    md5 = hashlib.md5(output).hexdigest()
    print(f"  {'md5' if complete else 'partial-md5'}={md5}")
    if args.expect_md5:
        if not complete:
            print("  MD5 NOT VERIFIED: reconstruction contains unknown source bytes")
        elif md5.lower() == args.expect_md5.lower():
            print("  MD5 MATCH")
        else:
            checksum_failed = True
            print(f"  MD5 MISMATCH (expected {args.expect_md5})")

    # The two outputs must be distinct before either one is written.
    if args.out and args.prov and Path(args.out).resolve(strict=False) == Path(args.prov).resolve(strict=False):
        raise OutputSafetyError("--out and --prov must be different files")

    # Never emit a file after a failed checksum/MD5, or when the caller explicitly
    # requested an MD5 proof that cannot be completed. Partial output is permitted
    # only when no complete-MD5 expectation was supplied.
    if checksum_failed:
        sys.exit(2)
    if args.expect_md5 and not complete:
        sys.exit(3)

    if args.out:
        inputs = [args.delta] + ([args.source] if args.source else [])
        safe_write_bytes(args.out, output, inputs=inputs, force=args.force)
        print(f"  wrote {args.out}" + (" (partial: unknown source bytes are zero-filled)" if not complete else ""))
    if args.prov:
        inputs = [args.delta] + ([args.source] if args.source else [])
        safe_write_bytes(args.prov, provenance, inputs=inputs + ([args.out] if args.out else []), force=args.force)
        print(f"  wrote {args.prov}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    info = sub.add_parser("info", help="inspect windows and checksums")
    info.add_argument("delta", nargs="+")
    info.add_argument("--adler-first", dest="adler_first", action="store_true", default=None)
    info.set_defaults(func=cmd_info)

    decode_parser = sub.add_parser("decode", help="reconstruct a target file")
    decode_parser.add_argument("delta")
    decode_parser.add_argument("--source", help="pristine source file")
    decode_parser.add_argument("--src-offset", type=int, default=0,
                               help="base offset added to VCD_SOURCE window positions")
    decode_parser.add_argument("--out", help="write reconstructed bytes")
    decode_parser.add_argument("--prov", help="write A/R/S/T provenance map")
    decode_parser.add_argument("--expect-md5", help="verify complete reconstruction against this MD5")
    decode_parser.add_argument("--adler-first", dest="adler_first", action="store_true", default=None)
    decode_parser.add_argument("--force", action="store_true", help="replace existing output files")
    decode_parser.set_defaults(func=cmd_decode)

    args = parser.parse_args()
    if getattr(args, "src_offset", 0) < 0:
        parser.error("--src-offset must be >= 0")
    try:
        args.func(args)
    except (OSError, ValueError, OutputSafetyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
