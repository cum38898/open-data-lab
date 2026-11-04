"""総務省「全国地方公共団体コード」(xlsx) から北海道の市町村一覧 JSON を作る。

一度だけ手元で実行し、生成した etl/municipalities.json をコミットする想定。
（CI では xlsx 読み込みのための依存を持たない）

    pip install openpyxl
    curl -o /tmp/code.xlsx https://www.soumu.go.jp/main_content/000925835.xlsx
    python etl/tools/build_municipalities.py /tmp/code.xlsx > etl/municipalities.json

出典：総務省「全国地方公共団体コード」
"""

import json
import sys

import openpyxl

# 北方領土の6村（団体コード 016951〜017001）は事業者向け補助金の対象にならないため除外する
NORTHERN_TERRITORIES = {"016951", "016969", "016977", "016985", "016993", "017001"}


def main(path: str) -> None:
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))[1:]
    out = []
    for code, pref, city, _pref_kana, city_kana, *_ in rows:
        if pref != "北海道" or not city:
            continue
        if code in NORTHERN_TERRITORIES:
            continue
        out.append({"code": code, "name": city, "kana": city_kana})
    json.dump(
        {
            "source": "総務省「全国地方公共団体コード」",
            "source_url": "https://www.soumu.go.jp/denshijiti/code.html",
            "municipalities": out,
        },
        sys.stdout,
        ensure_ascii=False,
        indent=1,
    )
    print()


if __name__ == "__main__":
    main(sys.argv[1])
