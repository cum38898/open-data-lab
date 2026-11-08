"""python -m unittest discover -s etl/tests -t .  （diet-tracker/ で実行）"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from etl import kokkai
from etl.common import write_json
from etl.kokkai import SNIPPET_AFTER, SNIPPET_BEFORE, is_chair, make_snippet, speech_url, to_row


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
                                       "自由民主党・無所属の会", "国土交通大臣", 0])

    def test_chair_detected_from_speaker_label(self):
        self.assertTrue(is_chair("○坂本委員長\u3000これより会議を開きます。"))
        self.assertTrue(is_chair("○議長（額賀福志郎君）\u3000日程第一を議題といたします。"))
        self.assertTrue(is_chair("○田中委員長代理\u3000次に、山田君。"))
        self.assertTrue(is_chair("○鈴木会長\u3000これより調査会を開会いたします。"))
        self.assertFalse(is_chair("○長友委員\u3000総理、ありがとうございます。"))
        self.assertFalse(is_chair("○金子国務大臣\u3000お答えいたします。"))
        self.assertFalse(is_chair("○稲葉参考人\u3000日本放送協会会長の稲葉でございます。"))
        self.assertFalse(is_chair(""))


def _rec(sid, day, text="○山田委員\u3000インボイスについて伺います。"):
    return {"speechID": sid, "date": day, "nameOfHouse": "衆議院", "nameOfMeeting": "財務金融委員会",
            "speaker": "山田", "speakerGroup": "無所属", "speakerPosition": None, "speech": text, "speechOrder": 1}


class IncrementalTests(unittest.TestCase):
    def test_refreshed_window_replaces_cached_rows(self):
        """取り直す期間の発言は、今回の結果にないものを消す（会議録の訂正などへの追従）"""
        topic = {"id": "t", "label": "t", "queries": ["インボイス"]}
        with tempfile.TemporaryDirectory() as d, mock.patch.object(kokkai, "TOPIC_DIR", Path(d)):
            first = [_rec("old_001", "2026-01-10"), _rec("gone_001", "2026-06-20"), _rec("keep_001", "2026-06-25")]
            with mock.patch.object(kokkai, "search_speeches", lambda q, since: iter([(len(first), first)])):
                kokkai.fetch_topic(topic, "2023-01-01")
            # 2回目：直近60日（2026-04-26〜）を取り直したら gone_001 は返ってこなかった
            second = [_rec("keep_001", "2026-06-25"), _rec("new_001", "2026-06-30")]
            seen_since = []

            def fake(q, since):
                seen_since.append(since)
                return iter([(len(second), second)])

            with mock.patch.object(kokkai, "search_speeches", fake):
                out = kokkai.fetch_topic(topic, "2023-01-01")
            ids = [r[0] for r in out["rows"]]
            self.assertEqual(seen_since, ["2026-04-26"])
            self.assertEqual(ids, ["new_001", "keep_001", "old_001"])
            self.assertNotIn("gone_001", out["snippets"])

    def test_failed_refresh_keeps_previous_file(self):
        topic = {"id": "t", "label": "t", "queries": ["インボイス"]}
        with tempfile.TemporaryDirectory() as d, mock.patch.object(kokkai, "TOPIC_DIR", Path(d)):
            with mock.patch.object(kokkai, "search_speeches", lambda q, since: iter([(1, [_rec("a_001", "2026-06-25")])])):
                kokkai.fetch_topic(topic, "2023-01-01")

            def boom(q, since):
                raise RuntimeError("network")
                yield  # noqa: unreachable  ジェネレーターにするため

            with mock.patch.object(kokkai, "search_speeches", boom):
                with self.assertRaises(RuntimeError):
                    kokkai.fetch_topic(topic, "2023-01-01")
            saved = json.loads((Path(d) / "t.json").read_text(encoding="utf-8"))
            self.assertEqual([r[0] for r in saved["rows"]], ["a_001"])

    def test_column_change_triggers_full_refetch(self):
        topic = {"id": "t", "label": "t", "queries": ["インボイス"]}
        with tempfile.TemporaryDirectory() as d, mock.patch.object(kokkai, "TOPIC_DIR", Path(d)):
            (Path(d) / "t.json").write_text(json.dumps({
                "queries": ["インボイス"], "since": "2023-01-01", "columns": ["id", "date"],
                "rows": [["a_001", "2026-06-25"]], "snippets": {}}), encoding="utf-8")
            seen = []

            def fake(q, since):
                seen.append(since)
                return iter([(0, [])])

            with mock.patch.object(kokkai, "search_speeches", fake):
                kokkai.fetch_topic(topic, "2023-01-01")
            self.assertEqual(seen, ["2023-01-01"])


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
