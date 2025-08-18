import os
import datetime
import time
import json
from flask import Flask, render_template, jsonify, request, abort, Response, stream_with_context

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
COMFORT_MESSAGE = "大丈夫ですよ、あなたは悪くありません。"

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
    is_ng = "[NG:" in original
    return {"text": text_part, "is_ng": is_ng, "role": role, "time": timestamp}

def parse_log_file(date: str):
    path = safe_log_path(date)
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            rows.append(parse_log_line(line))
    return rows

# -------------------- ルーティング --------------------

@app.route("/")
def index():
    dates = list_dates()
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

@app.route("/stream/<date>")
def stream_logs(date):
    """指定日のログファイルを Server-Sent Events でストリーム。
    1秒間隔で追記を監視し、新しい行だけ送る。
    """
    safe_log_path(date)  # バリデーションのみ
    path = safe_log_path(date)

    def generate():
        sent = 0
        # 初回に既存行を送る場合は以下を追加
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    lines = f.readlines()
                for l in lines:
                    item = parse_log_line(l)
                    yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                sent = len(lines)
            except Exception:
                pass
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
                        yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                    sent = len(lines)
            # ハートビート
            yield ": keep-alive\n\n"
            time.sleep(1)

    return Response(stream_with_context(generate()), mimetype='text/event-stream', headers={"Cache-Control": "no-cache"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
