import logging
import os
import re
from datetime import datetime
from config import HEADERS, OUTPUT_CONFIG


def parse_cookie(cookie_str: str) -> dict:
    """
    将 Cookie 字符串解析为字典
    
    Args:
        cookie_str: Cookie 字符串，格式如 "key1=value1; key2=value2"
    
    Returns:
        Cookie 字典
    """
    cookie_dict = {}
    if not cookie_str:
        return cookie_dict
    
    pairs = cookie_str.split(";")
    for pair in pairs:
        pair = pair.strip()
        if "=" in pair:
            key, value = pair.split("=", 1)
            cookie_dict[key.strip()] = value.strip()
    
    return cookie_dict


def build_headers(cookie: dict) -> dict:
    """
    构造完整的请求头
    
    Args:
        cookie: Cookie 字典
    
    Returns:
        完整的请求头字典
    """
    headers = HEADERS.copy()
    cookie_str = "; ".join([f"{k}={v}" for k, v in cookie.items()])
    headers["Cookie"] = cookie_str
    return headers


def clean_text(text: str) -> str:
    """
    清洗文本，去除 HTML 标签和多余空白
    
    Args:
        text: 原始文本
    
    Returns:
        清洗后的文本
    """
    if not text:
        return ""
    
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def format_number(num_str: str) -> int:
    """
    格式化数字字符串（如 "1.2 万" -> 12000）
    
    Args:
        num_str: 数字字符串
    
    Returns:
        整数
    """
    if not num_str:
        return 0
    
    num_str = str(num_str).strip()
    
    if "万" in num_str:
        num = float(num_str.replace("万", ""))
        return int(num * 10000)
    
    if "k" in num_str.lower():
        num = float(num_str.lower().replace("k", ""))
        return int(num * 1000)
    
    try:
        return int(num_str)
    except ValueError:
        return 0


def setup_logger(name: str = "crawler") -> logging.Logger:
    """
    配置日志记录器
    
    Args:
        name: 日志记录器名称
    
    Returns:
        日志记录器
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    if logger.handlers:
        return logger
    
    # 控制台 handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)
    
    # 文件 handler
    logs_dir = OUTPUT_CONFIG["LOGS_DIR"]
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)
    
    date_str = datetime.now().strftime("%Y%m%d")
    log_file = os.path.join(logs_dir, f"{name}_{date_str}.log")
    
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(file_format)
    logger.addHandler(file_handler)
    
    return logger
