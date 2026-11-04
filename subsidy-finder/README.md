# 北海道 補助金ファインダー

北海道の事業者が使える補助金・助成金を、公開データから毎日自動で集めて検索・可視化する静的サイトです。

- **探す**：キーワード、受付状況、制度の種類（国／北海道・道内市町村）、利用目的、業種、自社の従業員数で絞り込み。締切が近い順・上限額順に並べ替え。条件は URL に残るので共有できます。
- **傾向を見る**：今後12週間の締切、利用目的別の件数、補助上限額の分布、北海道庁の制度の分野別件数。
- **詳細ページ**：補助金ごとに静的ページを作るので、検索エンジンからも見つかります。

## データの出どころ

| データ源 | 取得方法 | 範囲 | 利用条件 |
|---|---|---|---|
| [Jグランツ公開API](https://developers.digital.go.jp/documents/jgrants/api/)（デジタル庁） | `etl/jgrants.py` | 対象地域に「北海道」か「全国」を含むもの。受付中・受付予定と、終了から180日以内 | 出典を明記 |
| [北海道ホームページ「助成制度」](https://www.pref.hokkaido.lg.jp/news/joseiseido/) ほかカテゴリ一覧 | `etl/hokkaido_pref.py` | タイトルが補助金らしいページ（更新から1年以内） | CC BY マークのあるページは [CC BY 4.0](https://www.pref.hokkaido.lg.jp/kz/dxs/opendata/hokkaido_od_kiyaku.html)。本文を抜粋・整形して掲載。マークがないページはタイトルとリンクのみ |
| [総務省「全国地方公共団体コード」](https://www.soumu.go.jp/denshijiti/code.html) | `etl/tools/build_municipalities.py`（手動で1回） | 道内179市町村 | 対象地域の判定に使用 |

### 注意点

- **北海道庁の締切は推定値**です。ページ本文から「受付」「締切」「必着」などの近くにある日付を拾っています（`etl/common.py` の `guess_deadline`）。事業完了期限・実績報告期限などは除外していますが、誤りうるのでサイト上でも「推定」と表示しています。
- Jグランツの詳細APIは公募要領などの添付ファイルを base64 で返し、1件で十数MBになることがあります。そのため詳細を取るのは受付中・受付予定・終了30日以内のものだけにし、取得結果を `data/jgrants.json` にキャッシュしています。受付中のものは7日ごとに取り直します。
- アクセス間隔は Jグランツ 1秒、北海道庁 1秒。429（アクセス過多）が返ったら待ってから再試行します。

### 使っていないデータ源（今後の候補）

- **J-Net21 支援情報ヘッドライン**（中小機構）：自治体・支援機関の補助金が都道府県別に載っていて有用ですが、[サイト利用条件](https://j-net21.smrj.go.jp/rule/index.html)で事前の承諾なしの転載・再利用が禁止されています。使うなら中小機構の承諾が必要です。
- **札幌市「事業者向け補助金等リスト」**（PDF）：表として抽出できますが、札幌市ホームページは複製・転用の前に所管課への相談が必要です（[リンク・著作権・免責事項](https://www.city.sapporo.jp/city/copyright/link.html)）。
- **道内各市町村のホームページ**：利用条件が市町村ごとに異なるため、CC BY などで公開しているところから順に追加するのが安全です。

## 構成

```
subsidy-finder/
├── etl/                 # Python（標準ライブラリのみ）
│   ├── jgrants.py       # Jグランツ取得・正規化
│   ├── hokkaido_pref.py # 北海道庁ページ取得・本文抜粋・締切推定
│   ├── build.py         # 統合して data/subsidies.json を出力
│   ├── common.py        # HTTP、HTML の安全化、和暦の日付解析
│   ├── municipalities.py / municipalities.json
│   └── tests/
├── data/
│   ├── jgrants.json        # 取得キャッシュ（コミットする）
│   ├── hokkaido_pref.json  # 取得キャッシュ（コミットする）
│   └── subsidies.json      # 生成物（コミットしない）
└── site/                # Astro の静的サイト
    ├── src/pages/       # 検索・詳細・傾向・このサイトについて、検索用 JSON
    ├── src/lib/         # 受付状態の判定など（ビルド時とブラウザで共用）
    └── tests/
```

検索はブラウザ内で行います（ビルド時に作る `data/search.json` を読み込み、部分一致で絞り込み）。件数が数千件までならサーバーは不要です。

## 手元で動かす

Python 3.11 以上と Node.js 22.23 以上が必要です。

```sh
cd subsidy-finder

# データ取得（初回は Jグランツの詳細取得に数分かかります）
python -m etl.build
# ネットワークに出ずにキャッシュから作り直すだけなら
python -m etl.build --offline

# サイト
cd site
npm ci
BASE_PATH=/ npm run dev      # http://localhost:4321/
BASE_PATH=/ npm run build    # dist/ に出力

# テスト
cd .. && python -m unittest discover -s etl/tests -t .
cd site && npm test
```

## 公開（GitHub Pages）

リポジトリ全体のワークフロー `.github/workflows/site.yml` で、毎日 05:17（日本時間）にデータを取得し、`https://<ユーザー名>.github.io/open-data-lab/subsidy-finder/` に公開します。詳しくはリポジトリ直下の README を見てください。
