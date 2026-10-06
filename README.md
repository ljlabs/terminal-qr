# terminalqr

A small Python QR encoder and terminal renderer with no runtime dependencies.
It is designed for short text and URLs, including one-time local-network links.

## Limits

This intentionally compact implementation produces QR Model 2 version 5,
error-correction level L symbols in byte mode with mask 0. Payloads are limited
to 106 bytes after UTF-8 encoding. It raises `ValueError` for larger input.

## Use as a single Python file

Copy `terminalqr.py` into your project:

```python
from terminalqr import encode, print_qr, render_terminal

matrix = encode("https://example.com")  # True means a dark module
print(render_terminal(matrix))
print_qr("https://example.com", label="Scan to open:")
```

## Command line

```console
python terminalqr.py "https://example.com"
```

When output is a terminal, it uses ANSI background colors. When redirected,
it uses Unicode blocks. Add `--no-color` to force the Unicode rendering.

## Install from a local checkout

```console
python -m pip install .
terminalqr "hello from the terminal"
```

The encoder itself only uses the Python standard library. Installing from the
source checkout uses the standard Python packaging build backend declared in
`pyproject.toml`.
