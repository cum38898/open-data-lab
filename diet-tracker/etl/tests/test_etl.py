"""python -m unittest discover -s etl/tests -t .  （diet-tracker/ で実行）"""

import json
import tempfile
import unittest
from pathlib import Path

from etl.common import write_json
from etl.kokkai import SNIPPET_AFTER, SNIPPET_BEFORE, make_snippet, speech_url, to_row


class SnippetTests(unittest.TestCase):
    def test_cuts_around_term_and_drops_speaker_label(self):
        text = "○山田委員　" + "あ" * 200 + "インボイス制度について" + "い" * 200
        s = make_snippet(text, ["インボイス"])
        self.assertIn("インボイス", s)
        self.assertNotIn("山田委員", s)
        self.assertTrue(s.startswith("…") and s.endswith("…"))
        self.assertLessEqual(len(s), SNIPPET_BEFORE + SNIPPET_AFTER + 2)

    def test_fullwidth_text_matches_halfwidth_query(self):
        s = make_snippet("○佐藤委員　次に、ＪＲ北海道の経営について伺います。", ["JR北海道"])
        self.assertIn("ＪＲ北海道", s)

    def test_uses_earliest_of_several_terms(self):
        s = make_snippet("ヒグマの出没が増え、クマ被害が深刻です。", ["クマ被害", "ヒグマ"])
        self.assertTrue(s.startswith("ヒグマ"))

    def test_short_text_has_no_ellipsis(self):
        self.assertEqual(make_snippet("生成AIの活用", ["生成AI"]), "生成AIの活用")


class RecordTests(unittest.TestCase):
    def test_speech_url(self):
        self.assertEqual(speech_url("122104319X01320260722_017"),
                         "https://kokkai.ndl.go.jp/txt/122104319X01320260722/17")

    def test_to_row(self):
        rec = {"speechID": "x_001", "date": "2026-07-22", "nameOfHouse": "衆議院", "nameOfMeeting": "国土交通委員会",
               "speaker": "金子　恭之", "speakerGroup": "自由民主党・無所属の会", "speakerPosition": "国土交通大臣"}
        self.assertEqual(to_row(rec), ["x_001", "2026-07-22", "衆", "国土交通委員会", "金子 恭之",
                                       "自由民主党・無所属の会", "国土交通大臣"])


class WriteJsonTests(unittest.TestCase):
    def test_rows_are_one_line_each_and_roundtrip(self):
        obj = {"rows": [["a,\"b", "2026-01-01", None, 3], ["c", "2026-01-02", "衆", 4]], "n": 1}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.json"
            write_json(p, obj)
            text = p.read_text(encoding="utf-8")
            self.assertEqual(json.loads(text), obj)
            self.assertIn('["c", "2026-01-02", "衆", 4]', text)


if __name__ == "__main__":
    unittest.main()
