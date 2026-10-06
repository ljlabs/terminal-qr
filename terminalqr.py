#!/usr/bin/env python3
"""Dependency-free QR Model 2 encoder and terminal renderer.

The encoder intentionally implements one compact, predictable symbol format:
version 5, error-correction level L, byte mode, and mask 0.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import TextIO


QR_VERSION = 5
QR_SIZE = 17 + QR_VERSION * 4
QR_DATA_CODEWORDS = 108
QR_ECC_CODEWORDS = 26
MAX_PAYLOAD_BYTES = QR_DATA_CODEWORDS - 2
Matrix = list[list[bool]]


def _gf_multiply(left: int, right: int) -> int:
    product = 0
    while right:
        if right & 1:
            product ^= left
        right >>= 1
        left <<= 1
        if left & 0x100:
            left ^= 0x11D
    return product


def _error_correction(data: list[int]) -> list[int]:
    generator = [1]
    root = 1
    for _ in range(QR_ECC_CODEWORDS):
        next_generator = [0] * (len(generator) + 1)
        for index, coefficient in enumerate(generator):
            next_generator[index] ^= coefficient
            next_generator[index + 1] ^= _gf_multiply(coefficient, root)
        generator = next_generator
        root = _gf_multiply(root, 2)

    generator = generator[1:]
    remainder = [0] * QR_ECC_CODEWORDS
    for byte in data:
        factor = byte ^ remainder[0]
        remainder = remainder[1:] + [0]
        for index, coefficient in enumerate(generator):
            remainder[index] ^= _gf_multiply(coefficient, factor)
    return remainder


def _append_bits(bits: list[int], value: int, length: int) -> None:
    for shift in range(length - 1, -1, -1):
        bits.append((value >> shift) & 1)


def _format_bits(mask: int = 0) -> int:
    # Error-correction level L has format value 01.
    value = (0b01 << 3) | mask
    remainder = value
    for _ in range(10):
        remainder = (remainder << 1) ^ (0x537 if remainder & 0x200 else 0)
    return ((value << 10) | remainder) ^ 0x5412


def encode(payload: str | bytes) -> Matrix:
    """Encode UTF-8 text or bytes and return a square matrix (True means dark).

    This compact encoder supports payloads up to 106 bytes. It raises
    ``ValueError`` for larger payloads rather than silently truncating them.
    """
    raw = payload.encode("utf-8") if isinstance(payload, str) else bytes(payload)
    if len(raw) > MAX_PAYLOAD_BYTES:
        raise ValueError(f"The QR payload must be at most {MAX_PAYLOAD_BYTES} bytes.")

    bits: list[int] = []
    _append_bits(bits, 0b0100, 4)  # Byte mode
    _append_bits(bits, len(raw), 8)  # Version 5 uses an 8-bit byte count
    for byte in raw:
        _append_bits(bits, byte, 8)

    capacity = QR_DATA_CODEWORDS * 8
    bits.extend([0] * min(4, capacity - len(bits)))
    bits.extend([0] * ((-len(bits)) % 8))
    data: list[int] = []
    for offset in range(0, len(bits), 8):
        value = 0
        for bit in bits[offset:offset + 8]:
            value = (value << 1) | bit
        data.append(value)
    pad_bytes = (0xEC, 0x11)
    while len(data) < QR_DATA_CODEWORDS:
        data.append(pad_bytes[(len(data) - (len(bits) // 8)) % 2])

    codewords = data + _error_correction(data)
    stream = [((byte >> shift) & 1) for byte in codewords for shift in range(7, -1, -1)]

    modules = [[False] * QR_SIZE for _ in range(QR_SIZE)]
    function = [[False] * QR_SIZE for _ in range(QR_SIZE)]

    def set_function(x: int, y: int, dark: bool) -> None:
        if 0 <= x < QR_SIZE and 0 <= y < QR_SIZE:
            modules[y][x] = dark
            function[y][x] = True

    def place_finder(left: int, top: int) -> None:
        for dy in range(-1, 8):
            for dx in range(-1, 8):
                x, y = left + dx, top + dy
                inside = 0 <= dx <= 6 and 0 <= dy <= 6
                dark = inside and max(abs(dx - 3), abs(dy - 3)) != 2
                set_function(x, y, dark)

    place_finder(0, 0)
    place_finder(QR_SIZE - 7, 0)
    place_finder(0, QR_SIZE - 7)

    for index in range(8, QR_SIZE - 8):
        set_function(index, 6, index % 2 == 0)
        set_function(6, index, index % 2 == 0)

    # Version 5 alignment centers are 6 and 30; the other three overlap finders.
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            set_function(QR_SIZE - 7 + dx, QR_SIZE - 7 + dy, max(abs(dx), abs(dy)) != 1)

    # Reserve both format-information copies and the fixed dark module.
    for index in range(6):
        set_function(8, index, False)
    set_function(8, 7, False)
    set_function(8, 8, False)
    set_function(7, 8, False)
    for index in range(9, 15):
        set_function(14 - index, 8, False)
    for index in range(8):
        set_function(QR_SIZE - 1 - index, 8, False)
    for index in range(8, 15):
        set_function(8, QR_SIZE - 15 + index, False)
    set_function(8, QR_SIZE - 8, True)

    # Place data in the standard alternating two-column pattern, using mask 0.
    bit_index = 0
    right = QR_SIZE - 1
    while right >= 1:
        if right == 6:
            right = 5
        for vertical in range(QR_SIZE):
            upward = ((right + 1) & 2) == 0
            y = QR_SIZE - 1 - vertical if upward else vertical
            for offset in range(2):
                x = right - offset
                if not function[y][x]:
                    if bit_index < len(stream):
                        bit = stream[bit_index]
                        bit_index += 1
                    else:
                        bit = 0
                    modules[y][x] = bool(bit ^ int((x + y) % 2 == 0))
        right -= 2
    if bit_index != QR_DATA_CODEWORDS * 8 + QR_ECC_CODEWORDS * 8:
        raise RuntimeError("QR encoder module count is inconsistent.")

    fmt = _format_bits()
    for index in range(6):
        modules[index][8] = bool((fmt >> index) & 1)
    modules[7][8] = bool((fmt >> 6) & 1)
    modules[8][8] = bool((fmt >> 7) & 1)
    modules[8][7] = bool((fmt >> 8) & 1)
    for index in range(9, 15):
        modules[8][14 - index] = bool((fmt >> index) & 1)
    for index in range(8):
        modules[8][QR_SIZE - 1 - index] = bool((fmt >> index) & 1)
    for index in range(8, 15):
        modules[QR_SIZE - 15 + index][8] = bool((fmt >> index) & 1)
    modules[QR_SIZE - 8][8] = True
    return modules


def render_terminal(
    matrix: Sequence[Sequence[bool]],
    *,
    border: int = 4,
    color: bool | None = None,
    stream: TextIO | None = None,
) -> str:
    """Render a square module matrix for terminals; auto-detect ANSI color."""
    if border < 0:
        raise ValueError("The border must be zero or greater.")
    size = len(matrix)
    if size == 0 or any(len(row) != size for row in matrix):
        raise ValueError("The QR matrix must be non-empty and square.")
    if stream is None:
        stream = sys.stdout
    if color is None:
        color = bool(getattr(stream, "isatty", lambda: False)())

    rendered: list[str] = []
    for y in range(-border, size + border):
        row: list[str] = []
        for x in range(-border, size + border):
            dark = 0 <= x < size and 0 <= y < size and bool(matrix[y][x])
            if color:
                row.append(("\x1b[40m" if dark else "\x1b[47m") + "  ")
            else:
                row.append("██" if dark else "  ")
        rendered.append(("\x1b[47m" if color else "") + "".join(row) + ("\x1b[0m" if color else ""))
    return "\n".join(rendered)


def print_qr(
    payload: str | bytes,
    *,
    label: str | None = None,
    border: int = 4,
    color: bool | None = None,
    stream: TextIO | None = None,
) -> None:
    """Encode and print a QR symbol to a terminal or text stream."""
    if stream is None:
        stream = sys.stdout
    if label:
        stream.write(label + "\n")
    stream.write(render_terminal(encode(payload), border=border, color=color, stream=stream) + "\n")
    stream.flush()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print a dependency-free QR code in the terminal.")
    parser.add_argument("text", help="text or URL to encode (up to 106 UTF-8 bytes)")
    parser.add_argument("--no-color", action="store_true", help="use Unicode blocks instead of ANSI colors")
    args = parser.parse_args(argv)
    try:
        print_qr(args.text, color=False if args.no_color else None)
    except ValueError as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
