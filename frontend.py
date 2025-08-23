#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Web UIを提供するFlaskアプリケーション。

- 保存された生ログと要約ログを日付ごとに一覧・表示
- Server-Sent Eventsを使い、生ログをリアルタイムに更新表示

実行方法:
    リポジトリのルートから `python frontend.py` を実行してください。
"""

# --- 標準ライブラリのインポート ---
import datetime
import json
import os
import re
import sys
import time
from pathlib import Path

# --- 外部ライブラリのインポート ---
try:
    from flask import \
        (Flask, Response, jsonify, redirect, render_template, 
                       request, stream_with_context, url_for)
except ImportError:
    print("エラー: Flaskがインストールされていません。", file=sys.stderr)
    print("pip install Flask を実行してください。", file=sys.stderr)
    sys.exit(1)

# =============================================================================
# --- グローバル定数 & Flaskアプリケーション初期化 ---
# =============================================================================

# このファイルを基準にプロジェクトルートを特定
ROOT_DIR = Path(__file__).resolve().parent
LOG_DIR = ROOT_DIR / "logs"
SUM_DIR = LOG_DIR / "summaries"

# Flaskアプリを初期化。テンプレートと静的ファイルの場所を明示
app = Flask(__name__, 
            template_folder=str(ROOT_DIR / 'templates'), 
            static_folder=str(ROOT_DIR / 'static'))

# =============================================================================
# --- ユーティリティ関数 ---
# =============================================================================

def list_log_dates() -> list[str]:
    """logsディレクトリ内にあるログファイルの日付リストを返す"""
    if not LOG_DIR.exists(): return []
    return sorted([f.stem for f in LOG_DIR.glob("*.txt")], reverse=True)

def parse_log_line(line: str) -> dict | None:
    """ログファイルの一行をパースして、扱いやすい辞書形式に変換する"""
    original = line.strip()
    if not original or re.fullmatch(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}", original):
        return None
    timestamp, rest = "", original
    match = re.match(r"(?:\[([^\]]+)\]\s*)?(.*)", original)
    if match:
        timestamp, rest = match.groups()
    role, text_part = "customer", rest
    if rest.startswith("店員:"):
        role, text_part = "clerk", rest[len("店員:"):
].lstrip()
    elif rest.startswith("客:"):
        role, text_part = "customer", rest[len("客:"):
].lstrip()
    if not text_part: return None
    return {"text": text_part, "is_ng": "[NG:" in original, "role": role, "time": timestamp}

def load_summaries(date: str) -> dict:
    """指定された日付の要約ファイル(.jsonl)を読み込む"""
    p = SUM_DIR / f"{date}.jsonl"
    items = []
    if p.exists():
        with p.open(encoding="utf-8") as f:
            for line in f:
                try: items.append(json.loads(line))
                except json.JSONDecodeError: pass
    return {"date": date, "items": items, "count": len(items)}

# =============================================================================
# --- Flaskページルート ---
# =============================================================================

@app.route("/")
def index():
    """トップページ。ログのある日付の一覧を表示する"""
    return render_template("index.html", title="会話ログ一覧", dates=list_log_dates())

@app.route("/logs/<date>")
def show_log(date: str):
    """指定された日付の生ログを表示するページ"""
    if not (LOG_DIR / f"{date}.txt").exists(): return redirect(url_for("index")
)
    return render_template("log.html", title=f"{date} の会話ログ", date=date)

@app.route("/summaries/<date>")
def show_summaries(date: str):
    """指定された日付の要約ログを表示するページ"""
    if date not in list_log_dates(): return redirect(url_for("index")
)
    return render_template("summaries.html", title=f"{date} の要約", date=date)

# =============================================================================
# --- APIエンドポイント ---
# =============================================================================

@app.route("/api/logs/<date>")
def api_logs(date: str):
    """生ログデータをJSONで返すAPI"""
    log_file = LOG_DIR / f"{date}.txt"
    rows = [item for line in log_file.read_text(encoding="utf-8").splitlines() if (item := parse_log_line(line))]
    return jsonify({"date": date, "items": rows, "count_all": len(rows), "count_ng": sum(1 for r in rows if r["is_ng"])
})

@app.route("/api/summaries/<date>")
def api_summaries(date: str):
    """要約ログデータをJSONで返すAPI"""
    return jsonify(load_summaries(date))

@app.route("/stream/<date>")
def stream_logs(date: str):
    """生ログの更新をServer-Sent Events (SSE)でリアルタイムに配信する"""
    def generate():
        log_file = LOG_DIR / f"{date}.txt"
        sent_lines = 0
        if log_file.exists():
            sent_lines = len(log_file.read_text(encoding="utf-8").splitlines())
        while True:
            if log_file.exists():
                lines = log_file.read_text(encoding="utf-8").splitlines()
                if sent_lines < len(lines):
                    for line in lines[sent_lines:]:
                        if item := parse_log_line(line):
                            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                    sent_lines = len(lines)
            yield ": \n\n"
            time.sleep(1)
    return Response(stream_with_context(generate()), mimetype='text/event-stream', headers={"Cache-Control": "no-cache"})

# =============================================================================
# --- 実行ブロック ---
# =============================================================================

if __name__ == "__main__":
    print("Webサーバーを起動します: http://127.0.0.1:5000")
    print("停止するにはCtrl+Cを押してください")
    app.run(host="0.0.0.0", port=5000, debug=False)
