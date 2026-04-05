# tests/test_crawler.py

import unittest
from unittest.mock import Mock, patch
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import parse_cookie, format_number, clean_text
from crawler import XiaohongshuCrawler


class TestParseCookie(unittest.TestCase):

    def test_simple_cookie(self):
        cookie_str = "a=1; b=2"
        result = parse_cookie(cookie_str)
        self.assertEqual(result, {"a": "1", "b": "2"})

    def test_empty_cookie(self):
        result = parse_cookie("")
        self.assertEqual(result, {})

    def test_cookie_with_spaces(self):
        cookie_str = "  key1 = value1 ; key2 = value2  "
        result = parse_cookie(cookie_str)
        self.assertEqual(result, {"key1": "value1", "key2": "value2"})


class TestFormatNumber(unittest.TestCase):

    def test_plain_number(self):
        self.assertEqual(format_number("100"), 100)

    def test_wan(self):
        self.assertEqual(format_number("1.2 万"), 12000)

    def test_k(self):
        self.assertEqual(format_number("1.5k"), 1500)

    def test_empty(self):
        self.assertEqual(format_number(""), 0)


class TestCleanText(unittest.TestCase):

    def test_html_tags(self):
        text = "<p>Hello <b>World</b></p>"
        result = clean_text(text)
        self.assertEqual(result, "Hello World")

    def test_multiple_spaces(self):
        text = "Hello    World"
        result = clean_text(text)
        self.assertEqual(result, "Hello World")

    def test_empty(self):
        self.assertEqual(clean_text(""), "")


class TestSearchResultCardExtraction(unittest.TestCase):

    def test_extract_note_cards_from_html_supports_current_search_result_urls(self):
        html = """
        <section class="note-item">
            <a href="/explore/67174698000000001402e218" style="display: none;"></a>
            <a class="cover mask ld" href="/search_result/67174698000000001402e218?xsec_token=abc&amp;xsec_source="></a>
        </section>
        <section class="note-item">
            <a href="/explore/69cf3020000000001f007426" style="display: none;"></a>
            <a class="cover mask ld" href="/search_result/69cf3020000000001f007426?xsec_token=def&amp;xsec_source="></a>
        </section>
        """

        crawler = XiaohongshuCrawler({})
        cards = crawler._extract_note_cards_from_html(html)

        self.assertEqual(
            cards,
            [
                {
                    "id": "67174698000000001402e218",
                    "href": "/search_result/67174698000000001402e218?xsec_token=abc&amp;xsec_source=",
                },
                {
                    "id": "69cf3020000000001f007426",
                    "href": "/search_result/69cf3020000000001f007426?xsec_token=def&amp;xsec_source=",
                },
            ],
        )


class TestNoteStateParsing(unittest.TestCase):

    def test_parse_note_info_from_state_reads_note_detail_map(self):
        note_state = {
            "currentNoteId": "abc123",
            "noteDetailMap": {
                "abc123": {
                    "note": {
                        "title": "claude code 3小时速通避坑demo",
                        "desc": "把协议设计流程图丢给claude",
                        "interactInfo": {
                            "likedCount": "666",
                            "collectedCount": "85",
                            "commentCount": "99",
                        },
                        "imageList": [{"urlDefault": "https://example.com/cover.jpg"}],
                        "time": 1743811200000,
                    },
                    "user": {
                        "nickname": "王子烧大王",
                    },
                }
            },
        }

        crawler = XiaohongshuCrawler({})
        note_info = crawler._parse_note_info_from_state(note_state, "abc123")

        self.assertEqual(note_info["author"], "王子烧大王")
        self.assertEqual(note_info["title"], "claude code 3小时速通避坑demo")
        self.assertEqual(note_info["desc"], "把协议设计流程图丢给claude")
        self.assertEqual(note_info["cover"], "https://example.com/cover.jpg")

    def test_parse_note_info_from_state_ignores_empty_note_module(self):
        note_state = {
            "prevRouteData": {},
            "currentNoteId": None,
            "noteDetailMap": {
                "undefined": {
                    "comments": {
                        "list": [],
                    },
                    "note": {},
                }
            },
        }

        crawler = XiaohongshuCrawler({})
        note_info = crawler._parse_note_info_from_state(note_state, "missing")

        self.assertIsNone(note_info)


if __name__ == "__main__":
    unittest.main()
