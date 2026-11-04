"""ETL 共通処理（標準ライブラリのみ）。"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent  # diet-tracker/
DATA_DIR = ROOT / "data"
USER_AGENT = "open-data-lab-diet-tracker/0.1 (+https://github.com/cum38898/open-data-lab)"


def log(*args) -> None:
    print(*args, file=sys.stderr, flush=True)


def today_jst() -> date:
    return datetime.now(JST).date()


def now_jst_iso() -> str:
    return datetime.now(JST).isoformat(timespec="minutes")


class Polite:
    """アクセス先ごとに「前のリクエストが終わってから interval 秒あける」ための待ち合わせ。

    国会会議録検索システムは「データを取得し終えてから数秒程度空けて次のリクエストを」と
    求めているので、既定は 3 秒。
    """

    def __init__(self, interval: float):
        self.interval = interval
        self.last = 0.0

    def wait(self) -> None:
        delta = time.monotonic() - self.last
        if delta < self.interval:
            time.sleep(self.interval - delta)

    def done(self) -> None:
        self.last = time.monotonic()


def http_get_json(url: str, params: dict | None = None, *, polite: Polite | None = None,
                  timeout: int = 120, retries: int = 3) -> dict:
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    last: Exception | None = None
    for attempt in range(retries):
        if polite:
            polite.wait()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as res:
                body = res.read()
            return json.loads(body)
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500 and e.code != 429:
                raise
            last = e
        except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError) as e:
            last = e
        finally:
            if polite:
                polite.done()
        wait = 10 * (attempt + 1)
        log(f"  retry {attempt + 1}/{retries} in {wait}s: {url[:120]} ({last})")
        time.sleep(wait)
    assert last is not None
    raise last


def read_json(path: Path, default):
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj, *, compact_rows: bool = True) -> None:
    """rows のような大きい配列は1行1要素で書き、git の差分を読みやすく小さくする。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, indent=1)
    if compact_rows:
        # インデントされた配列の中身（数値・文字列・null だけの内側の配列）を1行にまとめる
        import re

        text = re.sub(
            r"\[\n\s+((?:(?:\"(?:[^\"\\]|\\.)*\"|-?\d+(?:\.\d+)?|null|true|false),\n\s+)*(?:\"(?:[^\"\\]|\\.)*\"|-?\d+(?:\.\d+)?|null|true|false))\n\s+\]",
            lambda m: "[" + ", ".join(x.strip() for x in m.group(1).split(",\n")) + "]",
            text,
        )
    with path.open("w", encoding="utf-8") as f:
        f.write(text)
        f.write("\n")
