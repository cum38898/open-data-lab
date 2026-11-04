"""北海道の市町村名の検出。"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

_PATH = Path(__file__).with_name("municipalities.json")


@lru_cache(maxsize=1)
def municipalities() -> list[dict]:
    with _PATH.open(encoding="utf-8") as f:
        return json.load(f)["municipalities"]


@lru_cache(maxsize=1)
def _pattern() -> re.Pattern:
    # 長い名前から先に試す（例：「北広島市」を「広島…」より先に）
    names = sorted((m["name"] for m in municipalities()), key=len, reverse=True)
    # 「宿泊村」のような語の一部に誤一致しないよう、直前が漢字の場合は除外する。
    # ただし「北海道小樽市」「道北・稚内市」のように都道府県名や記号の直後は許可する。
    return re.compile(r"(?:(?<=北海道)|(?<![一-鿿々]))(" + "|".join(map(re.escape, names)) + ")")


def detect_municipality(text: str) -> str | None:
    """文中で最初に現れる北海道の市町村名を返す。札幌市の区は札幌市にまとめる。"""
    s = unicodedata.normalize("NFKC", text or "")
    m = _pattern().search(s)
    return m.group(1) if m else None


def all_names() -> list[str]:
    return [m["name"] for m in municipalities()]
