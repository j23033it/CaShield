# scripts/purge_raw_logs.py
"""
要約に採用されなかった原文行を TTL 経過後に削除するユーティリティ。

- 設定はコード内（Config）で集中管理（.env/環境変数は使用しない）
- 既定 TTL: 24 時間（`Config.TTL_HOURS`）
- バックアップ: logs/backup/<date>.txt.bak を必ず作成
- ドライラン: --dry-run で結果だけ表示
- 対象: --date YYYY-MM-DD を指定（未指定時は全ファイルを走査）
"""
from __future__ import annotations
import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Set

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
SUM_DIR = LOG_DIR / "summaries"
BACKUP_DIR = LOG_DIR / "backup"


class Config:
    """コード内設定オブジェクト（.envは使用しない）。"""
    TTL_HOURS: int = 24

def _list_dates() -> List[str]:
    return sorted([p.stem for p in LOG_DIR.glob("*.txt")])

def _load_keep_indices(date: str) -> Set[int]:
    keep: Set[int] = set()
    p = SUM_DIR / f"{date}.jsonl"
    if not p.exists():
        return keep
    for ln in p.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(ln)
            idx = rec.get("meta", {}).get("line_indices", [])
            for i in idx:
                if isinstance(i, int):
                    keep.add(i)
        except Exception:
            pass
    return keep

def _is_ttl_expired(path: Path, ttl_hours: int) -> bool:
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    return datetime.now() - mtime >= timedelta(hours=ttl_hours)

def purge_date(date: str, ttl_hours: int, dry_run: bool = False) -> None:
    src = LOG_DIR / f"{date}.txt"
    if not src.exists():
        print(f"[skip] {date}: no log file")
        return

    keep = _load_keep_indices(date)
    lines = src.read_text(encoding="utf-8").splitlines()

    if not _is_ttl_expired(src, ttl_hours):
        print(f"[hold] {date}: TTL not expired (keep all for now)")
        return

    if not keep:
        # 全部要約対象外なら“全削除”は危険 → 空でなく 1 行目だけ残す等のポリシーにしても良い
        print(f"[warn] {date}: no summaries found. keeping file untouched.")
        return

    new_lines = [ln for i, ln in enumerate(lines) if i in keep]
    removed = len(lines) - len(new_lines)

    if removed <= 0:
        print(f"[ok] {date}: nothing to purge")
        return

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    bak = BACKUP_DIR / f"{date}.txt.bak"
    if not dry_run:
        # バックアップ
        bak.write_text("\n".join(lines) + "\n", encoding="utf-8")
        # 上書き
        (LOG_DIR / f"{date}.txt").write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    print(f"[purge] {date}: removed {removed} lines, kept {len(new_lines)} (backup: {bak}){' (dry-run)' if dry_run else ''}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYY-MM-DD（未指定で全日）")
    ap.add_argument("--ttl-hours", type=int, default=Config.TTL_HOURS)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.date:
        purge_date(args.date, args.ttl_hours, args.dry_run)
    else:
        for d in _list_dates():
            purge_date(d, args.ttl_hours, args.dry_run)

if __name__ == "__main__":
    main()
