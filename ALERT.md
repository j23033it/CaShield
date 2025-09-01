# ALERT.md — 警告音・通知音・入力デバイス・ファイル名の変更ガイド

本ドキュメントは、運用時に変更することが多い「警告音（OSで鳴る）」「Web通知音（ブラウザで鳴る）」「マイク入力デバイス」「ログ/要約ファイル名」の変更手順をまとめたものです。

前提:
- .env は使用しません。すべての設定は「コード内設定」で集中管理しています。
- 依存追加は不要です（ただし Windows で `.wav` 以外を再生する場合は `pygame` が必要になることがあります）。

---

## 1) 警告音（OS側で鳴る音）を変更する

方法A（推奨・簡単）:
- `assets/alert.wav` を任意の警告音に差し替えてください（同名・同パスで上書き）。コード変更は不要です。

方法B（ファイル名・拡張子も変更したい場合）:
- `scripts/rt_stream.py` 内で `ActionManager("assets/alert.wav")` に渡しているパスを変更します。
- 修正箇所付近のコード全体（抜粋）:

```python
from src.action_manager import ActionManager
...
asr = DualASREngine()
keywords = load_keywords(Path("config/keywords.txt"))
kws = FuzzyKWS(keywords, threshold=ASRConfig.KWS_FUZZY_THRESHOLD)
action_mgr = ActionManager("assets/alert.wav")  # ←ここを任意のファイルパスに変更（例: "assets/custom.mp3"）

print("=" * 50)
print("CaShield RT stream - start")
print(
    f"FAST={ASRConfig.FAST_MODEL}({ASRConfig.FAST_COMPUTE}, beam={ASRConfig.FAST_BEAM}) "
    f"FINAL={ASRConfig.FINAL_MODEL}({ASRConfig.FINAL_COMPUTE}, beam={ASRConfig.FINAL_BEAM}) "
    f"Device={ASRConfig.DEVICE}"
)
print(f"Keywords: {', '.join(keywords)}")
print("Ctrl+C to stop\n")
```

備考（Windows）:
- `.wav` なら追加ライブラリなしで確実に鳴ります。
- `.mp3` など `.wav` 以外の場合は `pygame` が必要になる場合があります（`src/action_manager.py` が自動的にフォールバック処理を行います）。

---

## 2) Web通知音（ブラウザで鳴る音）を変更する

方法A（推奨・簡単）:
- `webapp/static/notify.mp3` を任意の音源に差し替えてください（同名で上書き）。

方法B（ファイル名・拡張子も変更したい場合）:
- `webapp/templates/log.html` の `<audio>` タグの `src` を変更します。
- 該当箇所付近のコード全体（`content` ブロック末尾部分）:

```html
{% extends "base.html" %}

{% block title %}{{ date }} の会話ログ{% endblock %}

{% block content %}
  <button class="btn btn-outline-secondary mode-btn" id="modeToggle">🌙</button>
  <h1 class="mb-4 fw-bold">{{ date }} の会話ログ</h1>
  <a href="/" class="btn btn-secondary mb-3">← 戻る</a>
  <input type="text" class="form-control search-box" id="searchInput" placeholder="キーワードで検索...">
  <div class="chat-container" id="logContainer">
    {% for text, is_ng, role, time in logs %}
      <div class="chat-row {{ role }}">
        {% if role=='customer' %}<img src="{{ url_for('static', filename='customer.png') }}" class="avatar">{% endif %}
        <div class="bubble {{ role }} {% if is_ng %}ng{% endif %}" data-time="{{ time }}">
          <div class="content">{{ text }}</div>
          {% if is_ng %}<div class="small text-muted mt-1 summary-slot"></div>{% endif %}
          <div class="chat-meta">{{ time }}</div>
        </div>
        {% if role=='clerk' %}<img src="{{ url_for('static', filename='clerk.png') }}" class="avatar">{% endif %}
      </div>
    {% endfor %}
  </div>
  <script id="initData" type="application/json">
    {{ logs|tojson }}
  </script>
  <audio id="notifySound" src="{{ url_for('static', filename='notify.mp3') }}" preload="auto"></audio>
{% endblock %}
```

例: `filename='notify.ogg'` に変更し、`webapp/static/notify.ogg` を配置します。

---

## 3) マイク入力デバイス（録音デバイス）を変更する

- `scripts/rt_stream.py` のコード内設定 `INPUT_DEVICE` を編集します。
- 該当箇所（定義部のコード全体）:

```python
LOG_DIR = Path("logs")

# --- コード内設定: 入力デバイス ---
# None の場合はデフォルトデバイスを使用。ID(int) または名称(str) も指定可能。
INPUT_DEVICE: Optional[int | str] = None
```

設定例:
- 既定デバイス: `INPUT_DEVICE = None`
- デバイスID指定: `INPUT_DEVICE = 1`
- デバイス名指定: `INPUT_DEVICE = "マイク(Realtek ...)"`

---

## 4) ログ/要約ファイル名を変更したい（上級者向け・非推奨）

現状は「日付ベースの固定命名（`logs/YYYY-MM-DD.txt`、`logs/summaries/YYYY-MM-DD.jsonl`）」に複数箇所が依存しています。変更は非推奨ですが、必要な場合は以下のすべてを一貫して修正してください。

1) 原文ログの追記箇所 — `scripts/rt_stream.py`

```python
def _append_log_line(role: str, stage: str, entry_id: str, text: str, hits: List[str]) -> None:
    """Append one line to logs/YYYY-MM-DD.txt with stage + [ID:xxxx]."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    date = datetime.now().strftime("%Y-%m-%d")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    who = "店員" if role == "clerk" else "客"
    ng = f" [NG: {', '.join(hits)}]" if hits else ""
    line = f"[{ts}] {who}: [{stage}] [ID:{entry_id}] {text}{ng}\n"
    (LOG_DIR / f"{date}.txt").open("a", encoding="utf-8").write(line)  # ←ファイル名を変更する場合はここ


def _replace_log_line(entry_id: str, role: str, new_stage: str, text: str, hits: List[str]) -> bool:
    """Replace the first line containing [ID:entry_id] with the FINAL result.

    Keeps original timestamp; overwrites content after the role marker.
    Returns True if replaced.
    """
    date = datetime.now().strftime("%Y-%m-%d")
    p = LOG_DIR / f"{date}.txt"  # ←ここ
    if not p.exists():
        return False
    who = "店員" if role == "clerk" else "客"
    ng = f" [NG: {', '.join(hits)}]" if hits else ""
    pat = re.compile(r"^\[(?P<ts>[^\]]+)\]\s+%s:\s+.*\[ID:%s\].*$" % (re.escape(who), re.escape(entry_id)))
    lines = p.read_text(encoding="utf-8").splitlines(True)
    replaced = False
    for i, line in enumerate(lines):
        m = pat.match(line)
        if not m:
            continue
        ts = m.group("ts")
        lines[i] = f"[{ts}] {who}: [{new_stage}] [ID:{entry_id}] {text}{ng}\n"
        replaced = True
        break
    if replaced:
        p.write_text("".join(lines), encoding="utf-8")
    return replaced
```

2) 原文ログの追記（保険） — `src/action_manager.py`

```python
def log_detection(self, detected_words: list, full_text: str, role: str = "customer"):
    """
    検出ログを記録する（将来拡張用）
    Args:
        detected_words: 検出されたトリガーワードのリスト
        full_text: 文字起こしされた全文
        role: "customer" or "clerk"
    """
    print(f"[ログ] 検出ワード: {detected_words}")
    print(f"[ログ] 全文: {full_text}")

    # 日次ログファイルへ追記
    try:
        date_str = datetime.datetime.now().strftime("%Y-%m-%d")
        ts      = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        role_prefix = "客:" if role == "customer" else "店員:"
        ng_part = f" [NG:{','.join(detected_words)}]" if detected_words else ""
        line = f"[{ts}] {role_prefix} {full_text}{ng_part}\n"
        with open(os.path.join(LOG_DIR, f"{date_str}.txt"), "a", encoding="utf-8") as f:  # ←ここ
            f.write(line)
    except Exception as e:
        print(f"[ログ] ファイル書き込み失敗: {e}")
```

3) Web 側（原文ファイル名の期待）— `webapp/app.py`

```python
def safe_log_path(date: str) -> str:
    try:
        datetime.date.fromisoformat(date)
    except Exception:
        abort(400, description="invalid date")
    return os.path.join(LOG_DIR, f"{date}.txt")  # ←ここ


def load_summaries(date: str):
    """logs/summaries/<date>.jsonl を読み込む"""
    p = Path(LOG_DIR) / "summaries" / f"{date}.jsonl"  # ←ここ
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
```

4) 要約ファイルの保存側 — `src/llm/queue.py`

```python
out_path = job.out_dir / f"{job.date}.jsonl"  # ←ここ
with out_path.open("a", encoding="utf-8") as f:
    f.write(json.dumps(record, ensure_ascii=False) + "\n")
```

変更のポイント:
- 命名変更は「生成側」と「参照側」の両方を合わせる必要があります。片側のみの変更は動作不整合の原因になります。
- 既定の命名のまま運用することを推奨します。

---

## 5) 反映手順と確認

- ファイルを差し替え/修正後、プロセスを再起動してください。
  - RT監視: `python -m scripts.rt_stream`
  - Web: `python -m webapp.app`
  - 要約ワーカ: `python -m scripts.llm_worker`
- テスト:
  - 警告音: NGワードを含む発話でOSの警告音が鳴るか
  - Web通知音: `/logs/<date>` 画面でNG行が追記されたときに通知音が鳴るか
  - 入力デバイス: 期待のマイクから音が取れているか（ログ出力に発話が現れるか）

---

## 6) 補足（設計ポリシー）

- 環境変数や .env は使用せず、すべて「コード内設定」で集中管理しています。
- 追加依存は極力不要に設計しています（Windows + `.wav` 推奨）。
- 将来の拡張に備え、ログ/要約のI/Oは1ファイル1日・JSONL（要約）を採用しています。

---

---
