import unittest
from utils import parse_cookie, format_number, clean_text, build_headers, setup_logger


class TestParseCookie(unittest.TestCase):
    def test_parse_cookie_basic(self):
        """测试基本 Cookie 解析"""
        result = parse_cookie("a=1; b=2")
        self.assertEqual(result, {"a": "1", "b": "2"})

    def test_parse_cookie_empty(self):
        """测试空字符串"""
        result = parse_cookie("")
        self.assertEqual(result, {})

    def test_parse_cookie_none(self):
        """测试 None 输入"""
        result = parse_cookie(None)
        self.assertEqual(result, {})

    def test_parse_cookie_single(self):
        """测试单个键值对"""
        result = parse_cookie("key=value")
        self.assertEqual(result, {"key": "value"})


class TestFormatNumber(unittest.TestCase):
    def test_format_number_wan(self):
        """测试带'万'的数字"""
        result = format_number("1.2 万")
        self.assertEqual(result, 12000)

    def test_format_number_k(self):
        """测试带'k'的数字"""
        result = format_number("1.5k")
        self.assertEqual(result, 1500)

    def test_format_number_plain(self):
        """测试纯数字"""
        result = format_number("100")
        self.assertEqual(result, 100)

    def test_format_number_empty(self):
        """测试空字符串"""
        result = format_number("")
        self.assertEqual(result, 0)

    def test_format_number_none(self):
        """测试 None 输入"""
        result = format_number(None)
        self.assertEqual(result, 0)


class TestCleanText(unittest.TestCase):
    def test_clean_text_html_tags(self):
        """测试去除 HTML 标签"""
        result = clean_text("<p>Hello</p> <b>World</b>")
        self.assertEqual(result, "Hello World")

    def test_clean_text_whitespace(self):
        """测试去除多余空白"""
        result = clean_text("hello    world")
        self.assertEqual(result, "hello world")

    def test_clean_text_empty(self):
        """测试空字符串"""
        result = clean_text("")
        self.assertEqual(result, "")

    def test_clean_text_none(self):
        """测试 None 输入"""
        result = clean_text(None)
        self.assertEqual(result, "")


class TestBuildHeaders(unittest.TestCase):
    def test_build_headers_basic(self):
        """测试基本请求头构造"""
        cookie = {"a": "1", "b": "2"}
        result = build_headers(cookie)
        self.assertIn("Cookie", result)
        self.assertEqual(result["Cookie"], "a=1; b=2")

    def test_build_headers_contains_base_headers(self):
        """测试包含基础请求头"""
        cookie = {"key": "value"}
        result = build_headers(cookie)
        self.assertIn("User-Agent", result)
        self.assertIn("Referer", result)


class TestSetupLogger(unittest.TestCase):
    def test_setup_logger_basic(self):
        """测试基本日志器配置"""
        logger = setup_logger("test_logger")
        self.assertEqual(logger.name, "test_logger")
        self.assertEqual(logger.level, 20)  # logging.INFO


if __name__ == "__main__":
    unittest.main()
