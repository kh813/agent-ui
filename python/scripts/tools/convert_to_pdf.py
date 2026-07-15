#!/usr/bin/env python3
"""
PDF変換スクリプト (Windows専用) / Convert to PDF script (Windows only)

Microsoft Office COM 経由で Word / Excel ファイルを PDF に変換します。
Converts Word / Excel files to PDF via Microsoft Office COM automation.
Requires Microsoft Word and Excel to be installed.

Usage:
  python python/scripts/tools/convert_to_pdf.py PATH [PATH ...] [--dry-run]

  PATH     変換するファイルまたはフォルダのパス（複数指定可）
           File or folder path to convert (multiple allowed)
  --dry-run  実際には変換せず結果を表示 / Preview without converting
"""

import sys
import os
from pathlib import Path

SCRIPT_DIR   = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]

WORD_EXTENSIONS  = {".docx", ".doc"}
EXCEL_EXTENSIONS = {".xlsx", ".xls"}
SUPPORTED_EXTENSIONS = WORD_EXTENSIONS | EXCEL_EXTENSIONS


def _reexec_with_venv():
    if sys.platform != "win32":
        print("[ERROR] このスクリプトは Windows 専用です。/ This script is Windows only.")
        sys.exit(1)
    try:
        import win32com.client  # noqa: F401
        return
    except ImportError:
        pass

    venv_python = PROJECT_ROOT / "venv" / "Scripts" / "python.exe"
    if not venv_python.exists():
        print("[ERROR] venv が見つかりません。先に setup を実行してください。")
        sys.exit(1)

    import subprocess as _sp
    if Path(sys.executable).resolve() == venv_python.resolve():
        # Already in venv but pywin32 missing — install then re-exec
        _sp.run([str(venv_python), "-m", "pip", "install", "-q", "--no-cache-dir", "pywin32"], check=True)
        sys.exit(_sp.run([str(venv_python)] + sys.argv).returncode)

    os.environ["PYTHONWARNINGS"] = "ignore"
    sys.exit(_sp.run([str(venv_python)] + sys.argv).returncode)


_reexec_with_venv()

import argparse          # noqa: E402
import win32com.client   # noqa: E402


# ── File collection ────────────────────────────────────────────

def _collect_files(paths: list) -> list:
    files = []
    for p in paths:
        path = Path(p)
        if not path.exists():
            print(f"[ERROR] パスが見つかりません / Path not found: {p}")
            sys.exit(1)

        if path.is_file():
            if path.suffix.lower() in SUPPORTED_EXTENSIONS:
                files.append(path.resolve())
            elif not path.name.startswith("."):
                print(f"  ! {path.name}  → 変換非対応の形式 / Unsupported format ({path.suffix})")

        elif path.is_dir():
            supported = sorted(
                [f.resolve() for f in path.iterdir()
                 if f.is_file() and not f.name.startswith(".")
                 and f.suffix.lower() in SUPPORTED_EXTENSIONS],
                key=lambda f: f.name.lower(),
            )
            unsupported = sorted(
                [f for f in path.iterdir()
                 if f.is_file() and not f.name.startswith(".")
                 and f.suffix.lower() not in SUPPORTED_EXTENSIONS],
                key=lambda f: f.name.lower(),
            )
            for f in unsupported:
                print(f"  ! {f.name}  → 変換非対応の形式 / Unsupported format ({f.suffix})")
            if not supported:
                print(f"  ! {path.name}/  → 対応ファイルなし / No supported files found")
            files.extend(supported)

    return files


# ── Conversion ─────────────────────────────────────────────────

def _convert_word(src: Path) -> None:
    pdf_path = src.with_suffix(".pdf")
    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    try:
        doc = word.Documents.Open(str(src))
        try:
            doc.SaveAs(str(pdf_path), FileFormat=17)  # 17 = wdFormatPDF
        finally:
            doc.Close(False)
    finally:
        word.Quit()


def _convert_excel(src: Path) -> None:
    pdf_path = src.with_suffix(".pdf")
    excel = win32com.client.Dispatch("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False
    try:
        wb = excel.Workbooks.Open(str(src))
        try:
            wb.ExportAsFixedFormat(0, str(pdf_path))  # 0 = xlTypePDF
        finally:
            wb.Close(False)
    finally:
        excel.Quit()


def _convert_one(src: Path, dry_run: bool) -> bool:
    pdf_path = src.with_suffix(".pdf")
    overwrite = "  ※ 既存PDFを上書き / overwrite existing" if pdf_path.exists() else ""

    if dry_run:
        print(f"  ✓ {src.name}  →  {pdf_path.name}{overwrite}")
        return True

    try:
        if src.suffix.lower() in WORD_EXTENSIONS:
            _convert_word(src)
        else:
            _convert_excel(src)
        print(f"  ✓ {src.name}  →  {pdf_path.name}")
        return True
    except Exception as e:
        msg = str(e)
        if "Word.Application" in msg or "Word" in msg:
            msg = "Microsoft Word が見つかりません / Microsoft Word not found"
        elif "Excel.Application" in msg or "Excel" in msg:
            msg = "Microsoft Excel が見つかりません / Microsoft Excel not found"
        print(f"  ✗ {src.name}  [FAILED] {msg}")
        return False


# ── Entry point ────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Word / Excel を PDF に変換 — Windows専用 / Windows only"
    )
    parser.add_argument("paths", nargs="+", metavar="PATH",
                        help="変換するファイルまたはフォルダのパス（複数指定可）")
    parser.add_argument("--dry-run", action="store_true",
                        help="実際には変換せず結果を表示 / Preview without converting")
    args = parser.parse_args()

    files = _collect_files(args.paths)
    if not files:
        print("[INFO] 変換対象のファイルが見つかりません。/ No files to convert.")
        sys.exit(0)

    label = "[DRY-RUN] " if args.dry_run else ""
    print(f"{label}変換対象 / Files to convert: {len(files)} 件")
    print()

    converted = failed = 0
    for f in files:
        if _convert_one(f, args.dry_run):
            converted += 1
        else:
            failed += 1

    print()
    if args.dry_run:
        print(f"[DRY-RUN] {converted} 件が変換対象（実際の変換は行っていません）")
        print(f"[DRY-RUN] {converted} file(s) would be converted — no changes made")
    else:
        parts = []
        if converted: parts.append(f"{converted} 件変換完了")
        if failed:    parts.append(f"{failed} 件エラー")
        print("完了 / Done: " + "、".join(parts))
        if failed:
            sys.exit(1)


if __name__ == "__main__":
    main()
