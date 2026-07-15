"""Fix line endings in a file. Works on Windows and Mac."""

import argparse
import sys
from pathlib import Path


def fix_eol(path: Path, mode: str) -> None:
    data = path.read_bytes()
    normalized = data.replace(b"\r\n", b"\n")
    if mode == "crlf":
        result = normalized.replace(b"\n", b"\r\n")
    else:
        result = normalized
    if result == data:
        print(f"  (no change) {path}")
    else:
        path.write_bytes(result)
        label = "CRLF" if mode == "crlf" else "LF"
        print(f"  Fixed → {label}: {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--crlf", dest="mode", action="store_const", const="crlf",
                       help="Convert to CRLF (Windows, .bat)")
    group.add_argument("--lf", dest="mode", action="store_const", const="lf",
                       help="Convert to LF (Unix/Mac, .sh)")
    parser.add_argument("files", nargs="+", type=Path, help="File(s) to fix")
    args = parser.parse_args()

    errors = []
    for f in args.files:
        if not f.exists():
            errors.append(f"Not found: {f}")
            continue
        fix_eol(f, args.mode)

    if errors:
        for e in errors:
            print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
