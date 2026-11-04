"""北海道庁ホームページの「助成制度」新着一覧から、道の補助金・助成金ページを取得する。

一覧: https://www.pref.hokkaido.lg.jp/news/joseiseido/
北海道のホームページは、CC BY マークのあるページは CC BY 4.0（北海道オープンデータ利用規約）。
https://www.pref.hokkaido.lg.jp/kz/dxs/opendata/hokkaido_od_kiyaku.html

- CC BY マークのあるページだけ本文の抜粋を保存し、ないページはタイトルとリンクだけにする。
- 受付期間はページ本文から推定する（end_estimated=True）。正確な情報は必ずリンク先で確認してもらう。
- ページごとの取得結果は data/hokkaido_pref.json にキャッシュし、一覧の更新日が変わったものだけ取り直す。
"""

from __future__ import annotations

import re
import time
from datetime import date, timedelta

from .common import (
    DATA_DIR,
    guess_deadline,
    html_to_text,
    http_get,
    log,
    now_jst_iso,
    one_line,
    read_json,
    sanitize_html,
    today_jst,
    write_json,
)
from .municipalities import detect_municipality

BASE = "https://www.pref.hokkaido.lg.jp"
LIST_URL = BASE + "/news/joseiseido/"
CACHE = DATA_DIR / "hokkaido_pref.json"

MAX_LIST_PAGES = 15
KEEP_DAYS = 365        # 一覧の更新日がこの日数より古いページは対象外
MAX_PAGES_PER_RUN = 200
SLEEP = 1.0

CLOSED_TITLE = re.compile(r"【[^】]*(?:終了|締切|締め切り)[^】]*】|(?:募集|受付|公募)[^。、]{0,12}?(?:は|を)?終了")

BODY_CLOSED = re.compile(r"(?:募集|受付|公募|申請)[^。\n]{0,10}?(?:は|を)?終了(?:しました|いたしました)|※\s*終了しました")

# 部局 → 分野（サイトの絞り込み用）
DEPARTMENT_FIELDS = [
    ("経済部", "商工・経済"),
    ("農政部", "農業"),
    ("水産林務部", "水産・林業"),
    ("保健福祉部", "医療・福祉"),
    ("環境生活部", "環境・くらし"),
    ("建設部", "建設・住宅"),
    ("総合政策部", "地域・交通"),
    ("総務部", "地域・交通"),
    ("教育", "教育・文化"),
    ("振興局", "地域・交通"),
]

# 一覧ページ（新着順）。どれも「更新日・タイトル・リンク」が並ぶ形式で、カテゴリはページ送りがある。
LIST_SOURCES = [
    LIST_URL,                                  # 新着「助成制度」（全部局）
    BASE + "/category/d002/c005/s007/",        # カテゴリ「助成制度」
    BASE + "/category/d011/c067/s312/",        # カテゴリ「中小企業対策・支援」
]

# 一覧には告示・セミナー案内なども混ざるので、タイトルで補助金らしいものに絞る
TITLE_INCLUDE = re.compile(r"補助|助成|支援金|奨励金|給付|交付金|支援事業|募集|公募|利子補給")
TITLE_EXCLUDE = re.compile(
    r"告示|公表|に関すること|セミナー|説明会|開催|ワークショップ|表彰|審議会|部会|相談室|相談窓口|"
    r"意向調査|希望調査|所要額調査|選定結果|採択結果|交付決定|実績|報告書|入札|実施状況|効果検証"
)

_ITEM = re.compile(
    r'<article class="[^"]*">\s*<header>\s*<time(?: datetime="(?P<iso>\d{4}-\d{2}-\d{2})")?[^>]*>'
    r"(?P<jdate>[^<]*)</time>\s*<h2><a href=\"(?P<href>[^\"]+)\">(?P<title>.*?)(?:<span>(?P<dept>.*?)</span>)?</a></h2>",
    re.S,
)
_JDATE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")


def _clean(s: str) -> str:
    import html as _html

    return one_line(_html.unescape(re.sub(r"<[^>]+>", "", s)))


def parse_list(html: str) -> list[dict]:
    rows = []
    for m in _ITEM.finditer(html):
        updated = m["iso"]
        if not updated:
            jd = _JDATE.search(m["jdate"] or "")
            if not jd:
                continue
            updated = f"{int(jd[1]):04d}-{int(jd[2]):02d}-{int(jd[3]):02d}"
        href = m["href"]
        rows.append({
            "updated": updated,
            "url": BASE + href if href.startswith("/") else href,
            "title": _clean(m["title"]),
        })
    return rows


def is_subsidy_title(title: str) -> bool:
    return bool(TITLE_INCLUDE.search(title)) and not TITLE_EXCLUDE.search(title)


def fetch_list(keep_from: str) -> list[dict]:
    items: list[dict] = []
    for base_url in LIST_SOURCES:
        for page in range(1, MAX_LIST_PAGES + 1):
            url = base_url if page == 1 else f"{base_url}index.p{page}.html"
            try:
                html = http_get(url).decode("utf-8", "replace")
            except Exception as e:  # noqa: BLE001  2ページ目以降の 404 はページ送りの終わり
                if page == 1:
                    log(f"  list {url} failed: {e}")
                break
            rows = parse_list(html)
            log(f"  {url}: {len(rows)}")
            if not rows:
                break
            items.extend(rows)
            time.sleep(SLEEP)
            if rows[-1]["updated"] < keep_from:
                break
    # 同じページが複数の一覧に出るので URL で重複除去（更新日が新しい方を残す）
    seen: dict[str, dict] = {}
    for it in items:
        if it["url"] not in seen or it["updated"] > seen[it["url"]]["updated"]:
            seen[it["url"]] = it
    return [
        it for it in seen.values()
        if it["updated"] >= keep_from and it["url"].startswith(BASE) and is_subsidy_title(it["title"])
    ]


def parse_page(url: str, html: str) -> dict:
    title_tag = re.search(r"<title>(.*?)</title>", html, re.S)
    department = ""
    if title_tag:
        parts = _clean(title_tag.group(1)).rsplit(" - ", 1)
        if len(parts) == 2:
            department = parts[1]
    h1 = re.search(r'<h1 id="page-header"[^>]*>(.*?)</h1>', html, re.S)
    article = re.search(r'<article class="body">(.*?)</article>', html, re.S)
    contact = re.search(r'<footer class="contact">.*?<p class="group">(.*?)</p>', html, re.S)
    cc_by = "cc-by.png" in html or 'alt="cc-by"' in html
    body_raw = article.group(1) if article else ""
    body_text = html_to_text(body_raw)
    deadline = guess_deadline(body_text)
    return {
        "page_title": _clean(h1.group(1)) if h1 else None,
        "department": department,
        "contact": _clean(contact.group(1)) if contact else None,
        "cc_by": cc_by,
        # CC BY のページだけ本文を保持する
        "body_html": sanitize_html(body_raw, url) if cc_by else "",
        "body_text": body_text if cc_by else "",
        "deadline_guess": deadline.isoformat() if deadline else None,
    }


def field_of(department: str) -> str | None:
    for key, field in DEPARTMENT_FIELDS:
        if key in (department or ""):
            return field
    return None


def _core(s: str) -> str:
    return re.sub(r"[\s「」『』【】（）()\[\]、。・:：]", "", s)


def summarize(body_text: str, title: str) -> str:
    """本文から一覧用の一文を選ぶ。タイトルの言い換えや日付だけの行は飛ばす。"""
    t = _core(title)
    for ln in (body_text or "").split("\n"):
        c = _core(ln)
        if len(ln) < 15 or not c:
            continue
        if c in t or t in c or re.match(r"^(令和|平成|20\d\d)", c) and len(c) < 40:
            continue
        return one_line(ln, 160)
    return ""


def normalize_record(item: dict, page: dict | None, today: date) -> dict:
    page = page or {}
    title = page.get("page_title") or item["title"]
    body_text = page.get("body_text") or ""
    # タイトルか本文の冒頭に「終了しました」等があれば終了とみなす
    closed_hint = bool(
        CLOSED_TITLE.search(item["title"])
        or CLOSED_TITLE.search(title)
        or BODY_CLOSED.search((body_text or "")[:300])
    )
    end = page.get("deadline_guess")
    # 推定締切が更新日より大きく前なら、過去年度の記述を拾った可能性が高いので捨てる
    if end and end < (date.fromisoformat(item["updated"]) - timedelta(days=200)).isoformat():
        end = None
    summary = summarize(body_text, title)
    path = re.sub(r"\.html?$", "", item["url"].replace(BASE, ""))
    slug = re.sub(r"[^0-9A-Za-z]+", "-", path).strip("-")
    department = page.get("department") or ""
    return {
        "id": f"hk-{slug}",
        "source": "hokkaido_pref",
        "title": title,
        "summary": summary,
        "body_html": page.get("body_html") or "",
        "body_text": body_text,
        "url": item["url"],
        "organization": f"北海道 {department}".strip(),
        "program": None,
        "scope": "hokkaido",
        "municipality": detect_municipality(title),
        "areas": ["北海道"],
        "area_detail": "",
        "purposes": [],
        "industries": [],
        "field": field_of(department),
        "employees": None,
        "max_amount": None,
        "rate": None,
        "start": None,
        "end": f"{end}T23:59+09:00" if end else None,
        "end_estimated": bool(end),
        "closed_hint": closed_hint,
        "updated": item["updated"],
        "attachments": [],
        "has_detail": bool(page),
        "license": "cc-by-hokkaido" if page.get("cc_by") else "link-only",
        "contact": page.get("contact"),
        "number": None,
    }


def run() -> list[dict]:
    today = today_jst()
    keep_from = (today - timedelta(days=KEEP_DAYS)).isoformat()
    cache = {c["url"]: c for c in read_json(CACHE, {"items": []})["items"]}

    log("hokkaido_pref: fetching list")
    items = fetch_list(keep_from)
    if not items:
        raise RuntimeError("hokkaido_pref: list returned nothing")
    log(f"hokkaido_pref: {len(items)} pages within window")

    fetched = 0
    new_cache = {}
    for item in items:
        cached = cache.get(item["url"])
        page = cached.get("page") if cached else None
        if (page is None or cached.get("updated") != item["updated"]) and fetched < MAX_PAGES_PER_RUN:
            try:
                page = parse_page(item["url"], http_get(item["url"]).decode("utf-8", "replace"))
                fetched += 1
            except Exception as e:  # noqa: BLE001
                log(f"  page failed {item['url']}: {e}")
            time.sleep(SLEEP)
        new_cache[item["url"]] = {**item, "page": page}

    log(f"hokkaido_pref: fetched {fetched} pages")
    write_json(CACHE, {"generated": now_jst_iso(), "items": list(new_cache.values())})
    return [normalize_record(c, c["page"], today) for c in new_cache.values()]


def load_cached() -> list[dict]:
    today = today_jst()
    return [normalize_record(c, c["page"], today) for c in read_json(CACHE, {"items": []})["items"]]
