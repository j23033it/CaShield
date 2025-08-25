import os
import datetime
import time
import json
import re
from pathlib import Path
from flask import Flask, render_template, jsonify, request, abort, Response, stream_with_context, redirect, url_for

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
COMFORT_MESSAGE = "大丈夫ですよ、あなたは悪くありません。"
SUM_DIR = os.path.join(LOG_DIR, "summaries")
os.makedirs(SUM_DIR, exist_ok=True)

app = Flask(__name__)

# -------------------- 共通: ユーティリティ --------------------

def list_dates():
    return sorted([f[:-4] for f in os.listdir(LOG_DIR) if f.endswith(".txt")], reverse=True)

def safe_log_path(date: str) -> str:
    try:
        datetime.date.fromisoformat(date)
    except Exception:
        abort(400, description="invalid date")
    return os.path.join(LOG_DIR, f"{date}.txt")

def parse_log_line(line: str):
    """1行のログを dict にして返す。
    想定フォーマット: [YYYY-MM-DD HH:MM:SS] 店員: 発話  /  [..] 客: 発話
    """
    original = line.rstrip("\n")
    s = original.strip()
    # 空行や「時刻だけ」の行は無視
    if not s:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}", s):
        return None

    timestamp = ""
    rest = original
    if original.startswith("[") and "]" in original:
        try:
            timestamp = original[1:original.index("]")]
            rest = original[original.index("]")+1:].lstrip()
        except Exception:
            # フォーマット不正時はそのまま
            pass
    role = "customer"
    text_part = rest
    if rest.startswith("店員:"):
        role = "clerk"
        text_part = rest[len("店員:"):].lstrip()
    elif rest.startswith("客:"):
        role = "customer"
        text_part = rest[len("客:"):].lstrip()
    # 本文が空、または本文自体が時刻だけなら無視
    if not text_part or re.fullmatch(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}", text_part.strip()):
        return None
    is_ng = "[NG:" in original
    return {"text": text_part, "is_ng": is_ng, "role": role, "time": timestamp}

def parse_log_file(date: str):
    path = safe_log_path(date)
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            item = parse_log_line(line)
            if item:
                rows.append(item)
    return rows

def load_summaries(date: str):
    """logs/summaries/<date>.jsonl を読み込んで返す"""
    path = os.path.join(SUM_DIR, f"{date}.jsonl")
    items = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for ln in f:
                try:
                    items.append(json.loads(ln))
                except Exception:
                    pass
    return {"date": date, "items": items, "count": len(items)}

def load_summaries(date: str):
    """logs/summaries/<date>.jsonl を読み込む"""
    p = Path(LOG_DIR) / "summaries" / f"{date}.jsonl"
    items = []
    if p.exists():
        with p.open(encoding="utf-8") as f:
            for ln in f:
                try:
                    items.append(json.loads(ln))
                except Exception:
                    pass
    # pending/failed は将来拡張（現状は件数を0で返す）
    return {"date": date, "items": items, "pending": 0, "failed": 0}


# -------------------- ルーティング --------------------

@app.route("/")
def index():
    dates = list_dates()
    # 一覧は要約ページを主導線に
    return render_template("index.html", title="会話ログ一覧", dates=dates)

@app.route("/logs/<date>")
def show_log(date):
    path = safe_log_path(date)
    if not os.path.exists(path):
        return render_template("index.html", title="会話ログ一覧", dates=list_dates())
    
    rows = parse_log_file(date)
    if request.args.get("ajax") == "1":
        return jsonify(rows)
    
    return render_template(
        "log.html",
        title=f"{date} の会話ログ",
        date=date,
        logs=[(r["text"], r["is_ng"], r["role"], r["time"]) for r in rows],
        comfort=COMFORT_MESSAGE,
    )

@app.route("/api/logs/<date>")
def api_logs(date):
    rows = parse_log_file(date)
    return jsonify({
        "date": date,
        "items": rows,
        "count_all": len(rows),
        "count_ng": sum(1 for r in rows if r["is_ng"]),
        "comfort": COMFORT_MESSAGE,
    })
    
@app.route("/api/summaries/<date>")
def api_summaries(date):
    """NG要約の取得"""
    return jsonify(load_summaries(date))

@app.route("/summaries/<date>")
def show_summaries(date):
    # テンプレはクライアント側で /api/summaries/<date> をフェッチ
    if date not in list_dates():
        # 存在しない日付なら一覧へ
        return redirect(url_for("index"))
    return render_template("summaries.html", title=f"{date} の要約", date=date, comfort=COMFORT_MESSAGE)


@app.route("/stream/<date>")
def stream_logs(date):
    """指定日のログファイルを Server-Sent Events でストリーム。
    1秒間隔で追記を監視し、新しい行だけ送る。
    """
    safe_log_path(date)  # バリデーションのみ
    path = safe_log_path(date)

    def generate():
        sent = 0
        # 初回は既存行を送らず、位置だけ合わせる（サイレント）
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    sent = len(f.readlines())
            except Exception:
                sent = 0
        # 以降は追記監視
        while True:
            if os.path.exists(path):
                try:
                    with open(path, encoding="utf-8") as f:
                        lines = f.readlines()
                except Exception:
                    lines = []
                if sent < len(lines):
                    new_lines = lines[sent:]
                    for l in new_lines:
                        item = parse_log_line(l)
                        if item:
                            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                    sent = len(lines)
            # ハートビート
            yield ": keep-alive\n\n"
            time.sleep(1)

    return Response(stream_with_context(generate()), mimetype='text/event-stream', headers={"Cache-Control": "no-cache"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
