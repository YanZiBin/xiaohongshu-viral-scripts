# config.py

# 爬虫配置
CRAWLER_CONFIG = {
    "BASE_URL": "https://www.xiaohongshu.com",
    "SEARCH_URL": "https://www.xiaohongshu.com/search_result",
    "NOTE_DETAIL_URL": "https://www.xiaohongshu.com/explore/",
    "LIMIT": 30,  # 默认爬取数量
    "MAX_RETRIES": 3,  # 最大重试次数
    "RETRY_DELAY": 1,  # 重试间隔（秒）
}

# 请求头配置
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.xiaohongshu.com/explore",
    "Origin": "https://www.xiaohongshu.com",
}

# 输出配置
OUTPUT_CONFIG = {
    "OUTPUT_DIR": "output",
    "LOGS_DIR": "logs",
    "FILE_PREFIX": "爆款笔记",
}

# CSV 字段名
CSV_FIELDS = [
    "序号",
    "作者",
    "标题",
    "点赞数",
    "收藏数",
    "评论数",
    "封面 URL",
    "笔记链接",
    "正文内容",
    "状态",
]
