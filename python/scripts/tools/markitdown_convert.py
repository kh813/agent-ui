#!/usr/bin/env python3
"""
Markitdown 変換スクリプト — ファイルを Markdown に変換する

Usage:
  python3 python/scripts/tools/markitdown_convert.py --all [--output-dir DIR] [--dry-run]
  python3 python/scripts/tools/markitdown_convert.py FILE [FILE ...] [--output-dir DIR] [--dry-run]
"""

import sys
import os
from pathlib import Path

SCRIPT_DIR   = Path(__file__).resolve().parent   # python/scripts/tools
PROJECT_ROOT = SCRIPT_DIR.parents[2]             # project root
FILES_DIR    = PROJECT_ROOT / "files"

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx", ".doc",
    ".pptx", ".ppt",
    ".xlsx", ".xls", ".csv",
    ".html", ".htm",
    ".xml", ".json",
    ".txt", ".rtf", ".epub",
    ".zip",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff",
    ".mp3", ".wav", ".m4a", ".ogg",
}


TOOLS_VENV = PROJECT_ROOT / ".tools-venv"


def _ensure_markitdown():
    """markitdown が未インストールなら .tools-venv を作成してインストール後 re-exec する。"""
    try:
        from markitdown import MarkItDown  # noqa: F401
        return
    except ImportError:
        pass

    vi = sys.version_info
    if vi < (3, 10):
        print(f"[ERROR] markitdown には Python 3.10 以上が必要です（現在: {vi.major}.{vi.minor}）。")
        print(f"[ERROR] markitdown requires Python 3.10+. Current: {vi.major}.{vi.minor}")
        print(f"        python3.10 以上で実行してください / Please run with Python 3.10 or later.")
        sys.exit(1)

    import subprocess as _sp
    import importlib

    # まず直接インストールを試みる（venv 内や非管理 Python の場合に成功）
    result = _sp.run(
        [sys.executable, "-m", "pip", "install", "-q", "--no-cache-dir", "markitdown"],
        capture_output=True,
    )
    if result.returncode == 0:
        importlib.invalidate_caches()
        return

    # externally-managed-environment などで失敗した場合 → .tools-venv を使用
    if sys.platform == "win32":
        venv_py = TOOLS_VENV / "Scripts" / "python.exe"
    else:
        venv_py = TOOLS_VENV / "bin" / "python3"

    if not venv_py.exists():
        print("  tools venv を作成中 / Creating .tools-venv ...")
        _sp.run([sys.executable, "-m", "venv", str(TOOLS_VENV)], check=True)
        print("  markitdown をインストール中 / Installing markitdown...")
        _sp.run([str(venv_py), "-m", "pip", "install", "-q", "--no-cache-dir",
                 "markitdown[pdf,docx,pptx,xlsx]"], check=True)

    # .tools-venv の Python で再実行
    os.environ["PYTHONWARNINGS"] = "ignore"
    if sys.platform == "win32":
        sys.exit(_sp.run([str(venv_py)] + sys.argv).returncode)
    else:
        os.execv(str(venv_py), [str(venv_py)] + sys.argv)


_ensure_markitdown()


def _is_convertible(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS and path.suffix.lower() != ".md"


def _find_convertible_files(directory: Path) -> list:
    if not directory.exists():
        return []
    return sorted(
        f for f in directory.iterdir()
        if f.is_file() and not f.name.startswith(".") and _is_convertible(f)
    )


def _rel(path: Path) -> Path:
    try:
        return path.relative_to(PROJECT_ROOT)
    except ValueError:
        return path


def _convert_file(input_path: Path, output_dir: Path = None, dry_run: bool = False):
    """Returns (success, output_path, message, size_kb)"""
    if output_dir is None:
        output_dir = input_path.parent
    output_path = output_dir / (input_path.stem + ".md")

    if dry_run:
        return True, output_path, "[DRY-RUN]", 0

    try:
        from markitdown import MarkItDown
        result = MarkItDown().convert(str(input_path))
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result.text_content, encoding="utf-8")
        size_kb = output_path.stat().st_size // 1024
        return True, output_path, "OK", size_kb
    except Exception as e:
        return False, output_path, str(e), 0


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="ファイルを Markdown に変換します / Convert files to Markdown"
    )
    parser.add_argument("files", nargs="*", metavar="FILE",
                        help="変換するファイルパス")
    parser.add_argument("--all", action="store_true",
                        help="files/ フォルダ内の対応ファイルをすべて変換")
    parser.add_argument("--output-dir", type=Path, metavar="DIR",
                        help="出力先ディレクトリ（デフォルト: 入力ファイルと同じ場所）")
    parser.add_argument("--dry-run", action="store_true",
                        help="変換せずに対象ファイルを一覧表示")
    args = parser.parse_args()

    if args.all:
        targets = _find_convertible_files(FILES_DIR)
        if not targets:
            print(f"変換対象のファイルがありません: {FILES_DIR}")
            print(f"No convertible files found in: {FILES_DIR}")
            sys.exit(0)
    elif args.files:
        targets = []
        for f in args.files:
            p = Path(f)
            if not p.exists():
                print(f"[ERROR] ファイルが見つかりません / File not found: {f}")
                sys.exit(1)
            if not _is_convertible(p):
                print(f"[WARN] 対応外の形式です / Unsupported format: {f} (suffix={p.suffix})")
            else:
                targets.append(p)
    else:
        parser.print_help()
        sys.exit(1)

    if not targets:
        print("変換対象がありません / No files to convert.")
        sys.exit(0)

    prefix = "[DRY-RUN] " if args.dry_run else ""
    print(f"{prefix}変換対象 / Files to convert: {len(targets)} ファイル\n")

    succeeded, failed = 0, 0
    for input_path in targets:
        ok, output_path, msg, size_kb = _convert_file(input_path, args.output_dir, args.dry_run)
        if ok:
            size_str = f" ({size_kb} KB)" if size_kb > 0 else ""
            print(f"  ✓ {_rel(input_path)}  →  {_rel(output_path)}{size_str}")
            succeeded += 1
        else:
            print(f"  ✗ {_rel(input_path)}  [FAILED] {msg}")
            failed += 1

    print()
    if args.dry_run:
        print(f"[DRY-RUN] {len(targets)} ファイルが変換対象です（実際の変換は行っていません）")
        print(f"[DRY-RUN] {len(targets)} file(s) would be converted (no actual conversion performed)")
    else:
        print(f"完了 / Done: {succeeded}/{len(targets)} ファイルを変換しました")
        if failed:
            print(f"  エラー / Errors: {failed} ファイル")
            sys.exit(1)


if __name__ == "__main__":
    main()
