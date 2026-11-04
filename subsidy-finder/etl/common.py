"""ETL 共通処理：HTTP 取得、HTML の安全化・テキスト化、和暦を含む日付の抽出。

依存は標準ライブラリのみ（CI で pip install 不要にするため）。
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent  # subsidy-finder/
DATA_DIR = ROOT / "data"

USER_AGENT = "open-data-lab-subsidy-finder/0.1 (+https://github.com/cum38898/open-data-lab)"


def log(*args) -> None:
    print(*args, file=sys.stderr, flush=True)


def today_jst() -> date:
    return datetime.now(JST).date()


def now_jst_iso() -> str:
    return datetime.now(JST).isoformat(timespec="minutes")


# ---------------------------------------------------------------- HTTP


def http_get(url: str, params: dict | None = None, *, timeout: int = 120, retries: int = 3) -> bytes:
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as res:
                return res.read()
        except urllib.error.HTTPError as e:
            # 429（アクセス過多）以外の 4xx はリトライしても変わらない
            if 400 <= e.code < 500 and e.code != 429:
                raise
            last = e
            if e.code == 429:
                retry_after = e.headers.get("Retry-After", "")
                wait = int(retry_after) if retry_after.isdigit() else 30 * (attempt + 1)
                log(f"  429 Too Many Requests; waiting {wait}s: {url}")
                time.sleep(min(wait, 120))
                continue
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
        wait = 2 ** (attempt + 1)
        log(f"  retry {attempt + 1}/{retries} in {wait}s: {url} ({last})")
        time.sleep(wait)
    assert last is not None
    raise last


def http_get_json(url: str, params: dict | None = None, **kw) -> dict:
    return json.loads(http_get(url, params, **kw))


# ---------------------------------------------------------------- JSON I/O


def read_json(path: Path, default):
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj, *, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        if compact:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(obj, f, ensure_ascii=False, indent=1, sort_keys=False)
        f.write("\n")


# ---------------------------------------------------------------- HTML

ALLOWED_TAGS = {
    "p", "br", "strong", "b", "em", "i", "u", "ul", "ol", "li", "a",
    "h2", "h3", "h4", "h5", "table", "thead", "tbody", "tr", "th", "td", "dl", "dt", "dd",
}
VOID_TAGS = {"br"}
DROP_CONTENT_TAGS = {"script", "style", "noscript", "iframe", "object", "svg", "form", "button"}
BLOCK_TAGS = {"p", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "div", "dt", "dd", "table", "section"}


class _Sanitizer(HTMLParser):
    """許可したタグだけ残し、属性は a[href] 以外すべて落とす。見出しは h3 以下に下げる。"""

    def __init__(self, base_url: str | None):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.out: list[str] = []
        self.stack: list[str] = []
        self.drop_depth = 0

    @staticmethod
    def _map(tag: str) -> str:
        return {"h2": "h3", "h3": "h4", "h4": "h5", "b": "strong", "i": "em"}.get(tag, tag)

    def handle_starttag(self, tag, attrs):
        if tag in DROP_CONTENT_TAGS:
            self.drop_depth += 1
            return
        if self.drop_depth or tag not in ALLOWED_TAGS:
            return
        t = self._map(tag)
        if tag == "a":
            href = dict(attrs).get("href") or ""
            if self.base_url:
                href = urllib.parse.urljoin(self.base_url, href)
            if not href.startswith(("http://", "https://")):
                # リンク先が使えない a はタグを捨てて中身だけ残す
                self.stack.append("")
                return
            self.out.append(f'<a href="{html.escape(href, quote=True)}" rel="noopener nofollow" target="_blank">')
            self.stack.append("a")
            return
        if tag in VOID_TAGS:
            self.out.append(f"<{t}>")
            return
        self.out.append(f"<{t}>")
        self.stack.append(t)

    def handle_startendtag(self, tag, attrs):
        if tag in VOID_TAGS and not self.drop_depth:
            self.out.append("<br>")

    def handle_endtag(self, tag):
        if tag in DROP_CONTENT_TAGS:
            self.drop_depth = max(0, self.drop_depth - 1)
            return
        if self.drop_depth or tag not in ALLOWED_TAGS or tag in VOID_TAGS:
            return
        t = "a" if tag == "a" else self._map(tag)
        # 対応する開始タグまで閉じる（壊れた HTML への対策）
        if t in self.stack or (tag == "a" and "" in self.stack):
            while self.stack:
                top = self.stack.pop()
                if top:
                    self.out.append(f"</{top}>")
                if top == t or (tag == "a" and top == ""):
                    break

    def handle_data(self, data):
        if not self.drop_depth:
            self.out.append(html.escape(data, quote=False))

    def result(self) -> str:
        while self.stack:
            top = self.stack.pop()
            if top:
                self.out.append(f"</{top}>")
        s = "".join(self.out)
        s = re.sub(r"<p>\s*(<br>\s*)*</p>", "", s)
        s = re.sub(r"(<br>\s*){3,}", "<br><br>", s)
        return s.strip()


def sanitize_html(src: str | None, base_url: str | None = None) -> str:
    if not src:
        return ""
    p = _Sanitizer(base_url)
    p.feed(src)
    p.close()
    return p.result()


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.drop = 0

    def handle_starttag(self, tag, attrs):
        if tag in DROP_CONTENT_TAGS:
            self.drop += 1
        elif tag in BLOCK_TAGS:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in DROP_CONTENT_TAGS:
            self.drop = max(0, self.drop - 1)
        elif tag in BLOCK_TAGS:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.drop:
            self.out.append(data)


def html_to_text(src: str | None) -> str:
    if not src:
        return ""
    p = _Text()
    p.feed(src)
    p.close()
    text = "".join(p.out)
    text = re.sub(r"[ \t　\xa0]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    return text.strip()


def one_line(text: str, limit: int | None = None) -> str:
    s = re.sub(r"\s+", " ", text or "").strip()
    if limit and len(s) > limit:
        s = s[: limit - 1].rstrip() + "…"
    return s


def normalize(text: str) -> str:
    """検索・照合用の正規化（全角英数→半角、大文字→小文字）。"""
    return unicodedata.normalize("NFKC", text or "").lower()


# ---------------------------------------------------------------- 日付

ERA_BASE = {"令和": 2018, "平成": 1988}

# 年が付いた日付：令和8年(2026年)4月22日 / 令和元年5月1日 / 2026年4月22日 / R8.4.22 / 2026/4/22
_FULL_DATE = re.compile(
    r"(?:(?P<era>令和|平成)\s*(?P<ey>\d{1,2}|元)\s*年\s*(?:[(（]\s*\d{4}\s*年?\s*[)）]\s*)?"
    r"|(?P<y>20\d{2})\s*年\s*(?:[(（]\s*(?:令和|平成)\s*(?:\d{1,2}|元)\s*年?\s*[)）]\s*)?"
    r"|(?P<r>R)\s*(?P<ry>\d{1,2})\s*[./]\s*"
    r"|(?P<sy>20\d{2})\s*[./]\s*)"
    r"(?P<m>\d{1,2})\s*(?:月|[./])\s*(?P<d>\d{1,2})\s*日?"
)
# 年なし：11月30日
_MONTH_DAY = re.compile(r"(?<![\d年./])(?P<m>\d{1,2})\s*月\s*(?P<d>\d{1,2})\s*日")


def _safe_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def find_dates(text: str) -> list[tuple[int, date]]:
    """文章中の日付を (出現位置, date) で返す。

    年の省略された「6月12日」は、直前に出てきた年付き日付の年を引き継ぐ
    （例：「令和8年4月22日から6月12日まで」）。月が戻る場合は翌年とみなす。
    """
    s = unicodedata.normalize("NFKC", text or "")
    found: list[tuple[int, date]] = []
    spans: list[tuple[int, int]] = []
    for m in _FULL_DATE.finditer(s):
        if m.group("era"):
            ey = m.group("ey")
            y = ERA_BASE[m.group("era")] + (1 if ey == "元" else int(ey))
        elif m.group("y"):
            y = int(m.group("y"))
        elif m.group("r"):
            y = ERA_BASE["令和"] + int(m.group("ry"))
        else:
            y = int(m.group("sy"))
        dt = _safe_date(y, int(m.group("m")), int(m.group("d")))
        if dt:
            found.append((m.start(), dt))
            spans.append((m.start(), m.end()))

    def covered(pos: int) -> bool:
        return any(a <= pos < b for a, b in spans)

    for m in _MONTH_DAY.finditer(s):
        if covered(m.start()):
            continue
        prev = [(pos, d) for pos, d in found if pos < m.start() and m.start() - pos < 120]
        if not prev:
            continue
        base = max(prev, key=lambda pd: pd[0])[1]  # 位置がいちばん近い日付
        mm, dd = int(m.group("m")), int(m.group("d"))
        y = base.year + (1 if mm < base.month else 0)
        dt = _safe_date(y, mm, dd)
        if dt:
            found.append((m.start(), dt))
    found.sort()
    return found


DEADLINE_HINT = re.compile(r"締切|締め切|期限|受付|募集|公募|申請|必着|提出")
# 申請の締切ではない日付（事業の実施期間・実績報告の期限など）
NOT_DEADLINE = re.compile(r"実績報告|事業完了|完了日|完了期限|完了予定|交付決定|事業期間|実施期間|対象期間|利用分|支払|開催|説明会|更新日")


def guess_deadline(text: str) -> date | None:
    """申請の受付期間・締切らしき文脈にある日付のうち最も遅いものを返す（推定）。

    ページ本文の書き方は部署ごとにまちまちなので、あくまで推定値として扱う。
    """
    s = unicodedata.normalize("NFKC", text or "")
    best: date | None = None
    for pos, dt in find_dates(s):
        # 同じ行の、日付より前の部分（見出し語）と直後の数文字を文脈とみなす
        line_start = s.rfind("\n", 0, pos) + 1
        before = s[max(line_start, pos - 40) : pos]
        after = s[pos : pos + 35].split("\n", 1)[0]
        context = before + after
        if NOT_DEADLINE.search(context):
            continue
        if DEADLINE_HINT.search(context) or re.search(r"^[^\n]{0,30}(まで|迄)", after):
            if best is None or dt > best:
                best = dt
    return best


def iso_to_jst_date(value: str | None) -> str | None:
    """'2027-02-26T08:00Z' → '2027-02-26'（JST の日付）。"""
    if not value:
        return None
    v = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(JST).date().isoformat()


def iso_to_jst(value: str | None) -> str | None:
    """'2027-02-26T08:00Z' → '2027-02-26T17:00+09:00'。"""
    if not value:
        return None
    v = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(JST).isoformat(timespec="minutes")
