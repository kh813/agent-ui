#!/usr/bin/env python3
"""
ファイル一括リネームスクリプト / Bulk file rename script

Usage:
  python3 python/scripts/tools/rename_files.py [PATH ...] MODE [options] [--dry-run]

Modes (choose exactly one):
  --sequential             連番付与
    --prefix TEXT          連番の前に付ける固定文字列（省略時は元のファイル名 stem）
    --start N              開始番号 (default: 1)
    --width N              番号の桁数 (default: 3)
    --sep TEXT             区切り文字 (default: "_")
    --sort name|date|none  ソート順 (default: name)

  --date-prefix            日付プレフィックス付与
    --date-format FMT      日付フォーマット (default: %Y%m%d)
    --sep TEXT             区切り文字 (default: "_")
    --date-source mtime|today  日付の取得元 (default: mtime)

  --replace OLD NEW        ファイル名 stem 内の文字列を置換
  --regex PATTERN REPLACE  ファイル名 stem 内を正規表現で置換

  --dry-run                実際にはリネームせず結果を表示
"""

import sys
import re
import argparse
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _collect_files(paths: list, sort_by: str) -> list:
    if paths:
        files = [Path(p) for p in paths if Path(p).is_file() and not Path(p).name.startswith(".")]
    else:
        files_dir = PROJECT_ROOT / "files"
        if not files_dir.exists():
            print("[ERROR] files/ フォルダが見つかりません。")
            sys.exit(1)
        files = sorted(
            [f for f in files_dir.iterdir() if f.is_file() and not f.name.startswith(".")],
            key=lambda f: f.name.lower(),
        )

    if sort_by == "name":
        files.sort(key=lambda f: f.name.lower())
    elif sort_by == "date":
        files.sort(key=lambda f: f.stat().st_mtime)

    return files


def _sequential(files: list, prefix: str, start: int, width: int, sep: str) -> list:
    pairs = []
    for i, f in enumerate(files, start=start):
        num = str(i).zfill(width)
        stem = prefix if prefix else f.stem
        new_name = stem + sep + num + f.suffix
        pairs.append((f, f.parent / new_name))
    return pairs


def _date_prefix(files: list, date_format: str, sep: str, date_source: str) -> list:
    pairs = []
    today_str = datetime.today().strftime(date_format)
    for f in files:
        if date_source == "today":
            date_str = today_str
        else:
            date_str = datetime.fromtimestamp(f.stat().st_mtime).strftime(date_format)
        pairs.append((f, f.parent / (date_str + sep + f.name)))
    return pairs


def _replace(files: list, old: str, new: str) -> list:
    return [(f, f.parent / (f.stem.replace(old, new) + f.suffix)) for f in files]


def _regex(files: list, pattern: str, replacement: str) -> list:
    pairs = []
    try:
        compiled = re.compile(pattern)
    except re.error as e:
        print(f"[ERROR] 正規表現エラー / Invalid regex: {e}")
        sys.exit(1)
    for f in files:
        new_stem = compiled.sub(replacement, f.stem)
        pairs.append((f, f.parent / (new_stem + f.suffix)))
    return pairs


def _execute(pairs: list, dry_run: bool) -> tuple:
    renamed = skipped = failed = 0
    for src, dst in pairs:
        if src == dst:
            print(f"  - {src.name}  →  (変更なし / no change)")
            skipped += 1
        elif dst.exists():
            print(f"  ✗ {src.name}  →  {dst.name}  [SKIP: 同名ファイルが存在 / already exists]")
            skipped += 1
        elif dry_run:
            print(f"  ✓ {src.name}  →  {dst.name}")
            renamed += 1
        else:
            try:
                src.rename(dst)
                print(f"  ✓ {src.name}  →  {dst.name}")
                renamed += 1
            except Exception as e:
                print(f"  ✗ {src.name}  →  {dst.name}  [FAILED] {e}")
                failed += 1
    return renamed, skipped, failed


def main():
    parser = argparse.ArgumentParser(description="ファイル一括リネーム / Bulk file rename")
    parser.add_argument("paths", nargs="*", metavar="PATH",
                        help="対象ファイルパス（省略時は files/ 直下の全ファイル）")
    parser.add_argument("--dry-run", action="store_true",
                        help="実際にはリネームせず結果を表示")
    parser.add_argument("--sort", choices=["name", "date", "none"], default="name",
                        help="処理順のソート（sequential モードで有効）")

    # sequential
    parser.add_argument("--sequential", action="store_true", help="連番付与モード")
    parser.add_argument("--prefix", default="", help="連番の前に付ける文字列（省略時は元のファイル名）")
    parser.add_argument("--start", type=int, default=1, help="開始番号 (default: 1)")
    parser.add_argument("--width", type=int, default=3, help="番号の桁数 (default: 3)")
    parser.add_argument("--sep", default="_", help="区切り文字 (default: _)")

    # date-prefix
    parser.add_argument("--date-prefix", action="store_true", help="日付プレフィックス付与モード")
    parser.add_argument("--date-format", default="%Y%m%d", help="日付フォーマット (default: %%Y%%m%%d)")
    parser.add_argument("--date-source", choices=["mtime", "today"], default="mtime",
                        help="日付の取得元: mtime（ファイル更新日）/ today（今日）")

    # replace / regex
    parser.add_argument("--replace", nargs=2, metavar=("OLD", "NEW"), help="文字列置換")
    parser.add_argument("--regex", nargs=2, metavar=("PATTERN", "REPLACEMENT"), help="正規表現置換")

    args = parser.parse_args()

    modes = [args.sequential, args.date_prefix, bool(args.replace), bool(args.regex)]
    if sum(modes) == 0:
        parser.error("モードを指定してください: --sequential | --date-prefix | --replace OLD NEW | --regex PATTERN REPLACEMENT")
    if sum(modes) > 1:
        parser.error("モードは1つだけ指定できます。")

    files = _collect_files(args.paths, args.sort)
    if not files:
        print("[INFO] 対象ファイルが見つかりません。")
        sys.exit(0)

    if args.sequential:
        pairs = _sequential(files, args.prefix, args.start, args.width, args.sep)
    elif args.date_prefix:
        pairs = _date_prefix(files, args.date_format, args.sep, args.date_source)
    elif args.replace:
        pairs = _replace(files, args.replace[0], args.replace[1])
    else:
        pairs = _regex(files, args.regex[0], args.regex[1])

    label = "[DRY-RUN] " if args.dry_run else ""
    print(f"{label}リネーム対象 / Files: {len(files)} 件")
    print()

    renamed, skipped, failed = _execute(pairs, args.dry_run)

    print()
    if args.dry_run:
        print(f"[DRY-RUN] {renamed} 件がリネーム対象（実際の変更は行っていません）")
        print(f"[DRY-RUN] {renamed} file(s) would be renamed — no changes made")
    else:
        parts = []
        if renamed: parts.append(f"{renamed} 件リネーム完了")
        if skipped: parts.append(f"{skipped} 件スキップ")
        if failed:  parts.append(f"{failed} 件エラー")
        print("完了 / Done: " + "、".join(parts))
        if failed:
            sys.exit(1)


if __name__ == "__main__":
    main()
