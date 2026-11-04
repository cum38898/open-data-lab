"""ETL の解析処理のテスト。  python -m unittest discover -s etl/tests -t .  （subsidy-finder/ で実行）"""

import unittest
from datetime import date

from etl.common import find_dates, guess_deadline, html_to_text, iso_to_jst, iso_to_jst_date, sanitize_html
from etl.hokkaido_pref import BODY_CLOSED, CLOSED_TITLE, is_subsidy_title, parse_list, summarize
from etl.jgrants import is_hokkaido_eligible, split_list
from etl.municipalities import all_names, detect_municipality


class DateTests(unittest.TestCase):
    def test_wareki_with_western_year_and_range(self):
        dates = [d for _, d in find_dates("令和8年(2026年）4月22日（水）から6月12日（金）まで")]
        self.assertEqual(dates, [date(2026, 4, 22), date(2026, 6, 12)])

    def test_fullwidth_digits(self):
        self.assertEqual([d for _, d in find_dates("令和８年１１月２日")], [date(2026, 11, 2)])

    def test_gannen(self):
        self.assertEqual([d for _, d in find_dates("令和元年5月1日")], [date(2019, 5, 1)])

    def test_month_day_rolls_over_year(self):
        dates = [d for _, d in find_dates("令和8年12月1日から1月15日まで")]
        self.assertEqual(dates, [date(2026, 12, 1), date(2027, 1, 15)])

    def test_month_day_without_anchor_is_ignored(self):
        self.assertEqual(find_dates("毎年11月30日に締め切ります"), [])

    def test_invalid_date_is_skipped(self):
        self.assertEqual(find_dates("2026年2月30日"), [])

    def test_iso_to_jst(self):
        self.assertEqual(iso_to_jst("2027-02-26T08:00Z"), "2027-02-26T17:00+09:00")
        self.assertEqual(iso_to_jst_date("2026-11-30T15:30:00.000Z"), "2026-12-01")
        self.assertIsNone(iso_to_jst(None))


class DeadlineTests(unittest.TestCase):
    def test_application_period(self):
        self.assertEqual(guess_deadline("【公募期間】令和8年4月22日から6月12日まで"), date(2026, 6, 12))

    def test_ignores_project_completion_and_report(self):
        text = "申請受付：令和8年11月2日～12月11日\n実績報告期限：令和9年3月10日\n事業完了期限：令和9年2月28日"
        self.assertEqual(guess_deadline(text), date(2026, 12, 11))

    def test_ignores_usage_period(self):
        self.assertIsNone(guess_deadline("令和8年7月から令和8年9月利用分の電気料金"))

    def test_made_suffix_without_keyword(self):
        self.assertEqual(guess_deadline("2026年12月29日(火)まで"), date(2026, 12, 29))


class HtmlTests(unittest.TestCase):
    def test_sanitize_drops_scripts_attrs_and_images(self):
        out = sanitize_html('<p style="x" onclick="y">本文<script>alert(1)</script><img src=x></p>')
        self.assertEqual(out, "<p>本文</p>")

    def test_sanitize_resolves_relative_links(self):
        out = sanitize_html('<a href="/a.pdf">要領</a>', "https://www.pref.hokkaido.lg.jp/kz/")
        self.assertIn('href="https://www.pref.hokkaido.lg.jp/a.pdf"', out)
        self.assertIn('rel="noopener nofollow"', out)

    def test_sanitize_drops_javascript_links(self):
        out = sanitize_html('<a href="javascript:alert(1)">x</a>')
        self.assertEqual(out, "x")

    def test_headings_are_demoted(self):
        self.assertEqual(sanitize_html("<h2>見出し</h2>"), "<h3>見出し</h3>")

    def test_html_to_text(self):
        self.assertEqual(html_to_text("<p>a</p><p>b<br>c</p>"), "a\nb\nc")


class MunicipalityTests(unittest.TestCase):
    def test_count(self):
        self.assertEqual(len(all_names()), 179)

    def test_detects(self):
        self.assertEqual(detect_municipality("小樽市省エネルギー診断補助金"), "小樽市")
        self.assertEqual(detect_municipality("北海道北広島市の事業者"), "北広島市")
        self.assertEqual(detect_municipality("札幌市中央区内の店舗"), "札幌市")

    def test_no_false_positive_inside_word(self):
        self.assertIsNone(detect_municipality("宿泊村の体験"))
        self.assertIsNone(detect_municipality("全道の中小企業"))


class HokkaidoPrefTests(unittest.TestCase):
    def test_parse_news_list(self):
        html = (
            '<article class="item-272793 "> <header> <time datetime="2026-10-30">2026年10月30日</time> '
            '<h2><a href="/kz/csk/272793.html">特別高圧電力利用事業者緊急支援事業</a></h2> </header> </article>'
        )
        self.assertEqual(
            parse_list(html),
            [{"updated": "2026-10-30", "url": "https://www.pref.hokkaido.lg.jp/kz/csk/272793.html",
              "title": "特別高圧電力利用事業者緊急支援事業"}],
        )

    def test_parse_category_list(self):
        html = (
            '<article class="272793"> <header> <time>2026年10月3日</time> <h2><a href="/kz/csk/272793.html">'
            "特別高圧電力利用事業者緊急支援事業<span>経済部中小企業課</span></a></h2> </header> </article>"
        )
        rows = parse_list(html)
        self.assertEqual(rows[0]["updated"], "2026-10-03")
        self.assertEqual(rows[0]["title"], "特別高圧電力利用事業者緊急支援事業")

    def test_title_filter(self):
        self.assertTrue(is_subsidy_title("ヒグマ対策事業補助金について"))
        self.assertFalse(is_subsidy_title("令和8年度補助金所要額調査"))
        self.assertFalse(is_subsidy_title("経営課題から考えるSDGs実践ワークショップ"))

    def test_closed_detection(self):
        self.assertTrue(CLOSED_TITLE.search("【募集終了】令和 8 年度 省エネルギー設備導入支援事業費補助金"))
        self.assertTrue(CLOSED_TITLE.search("[令和７年度] 補助金（第２回）：公募（第２回）は終了しました。"))
        self.assertFalse(CLOSED_TITLE.search("特別高圧電力利用事業者緊急支援事業"))
        self.assertTrue(BODY_CLOSED.search("更新情報\n・令和8年10月3日 申請受付を終了しました。"))

    def test_summary_skips_title_restatement(self):
        body = "令和8年度 新商品トライアル制度の募集について\n道内の中小企業が開発した新商品を道が試験的に購入し評価します。"
        self.assertEqual(summarize(body, "令和8年度 新商品トライアル制度の募集について"),
                         "道内の中小企業が開発した新商品を道が試験的に購入し評価します。")


class JgrantsTests(unittest.TestCase):
    def test_split_list(self):
        self.assertEqual(split_list("北海道 / 青森県"), ["北海道", "青森県"])
        self.assertEqual(split_list(None), [])

    def test_eligibility(self):
        self.assertTrue(is_hokkaido_eligible({"target_area_search": "北海道"}))
        self.assertTrue(is_hokkaido_eligible({"target_area_search": "全国"}))
        self.assertTrue(is_hokkaido_eligible({"target_area_search": "全国 / 北海道 / 青森県"}))
        self.assertFalse(is_hokkaido_eligible({"target_area_search": "福島県"}))
        self.assertFalse(is_hokkaido_eligible({"target_area_search": None}))


if __name__ == "__main__":
    unittest.main()
