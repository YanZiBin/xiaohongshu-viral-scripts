# tests/test_crawler.py

import unittest
from unittest.mock import Mock, patch
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import parse_cookie, format_number, clean_text


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


if __name__ == "__main__":
    unittest.main()
