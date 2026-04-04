# crawler.py

import time
import requests
from typing import Optional
from config import CRAWLER_CONFIG, CSV_FIELDS
from utils import build_headers, clean_text, setup_logger

logger = setup_logger("crawler")


class XiaohongshuCrawler:
    """小红书爬虫类"""

    def __init__(self, cookie: dict):
        """
        初始化爬虫

        Args:
            cookie: Cookie 字典
        """
        self.cookie = cookie
        self.headers = build_headers(cookie)
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def search_notes(self, keyword: str, limit: int = 30) -> list:
        """
        搜索笔记

        Args:
            keyword: 搜索关键词
            limit: 返回数量限制

        Returns:
            笔记 ID 列表
        """
        logger.info(f"开始搜索关键词：{keyword}")

        # 构造搜索 URL
        params = {
            "keyword": keyword,
            "source": "web_explore_feed",
        }

        url = f"{CRAWLER_CONFIG['BASE_URL']}/search_result"

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()

            # 尝试从页面提取笔记 ID
            # 小红书页面数据通常在 <script> 标签的 JSON 中
            import re
            html = response.text

            # 查找包含笔记数据的 JSON
            # 常见模式：<script>window.__INITIAL_STATE__={...}</script>
            pattern = r'window\.__INITIAL_STATE__\s*=\s*({.+?})</script>'
            match = re.search(pattern, html, re.DOTALL)

            if match:
                import json
                data = json.loads(match.group(1))
                # 根据实际数据结构提取笔记 ID
                note_ids = self._extract_note_ids_from_state(data)
                return note_ids

            # 备用方案：从 HTML 中提取笔记链接
            note_links = re.findall(r'/discovery/item/([a-zA-Z0-9]+)', html)
            return list(dict.fromkeys(note_links))  # 去重保持顺序

        except Exception as e:
            logger.error(f"搜索失败：{e}")
            return []

    def _extract_note_ids_from_state(self, data: dict) -> list:
        """
        从 INITIAL_STATE 中提取笔记 ID

        Args:
            data: 页面状态数据

        Returns:
            笔记 ID 列表
        """
        note_ids = []

        # 需要根据实际数据结构调整
        # 常见路径：searchResult -> notes 或 explore -> items
        try:
            if "searchResult" in data:
                notes = data["searchResult"].get("notes", [])
                note_ids = [note.get("id", "") for note in notes if note.get("id")]
            elif "explore" in data:
                notes = data["explore"].get("items", [])
                note_ids = [note.get("id", "") for note in notes if note.get("id")]
        except Exception as e:
            logger.warning(f"解析 INITIAL_STATE 失败：{e}")

        return note_ids

    def get_note_detail(self, note_id: str, retry: int = 3) -> Optional[dict]:
        """
        获取笔记详情

        Args:
            note_id: 笔记 ID
            retry: 重试次数

        Returns:
            笔记详情字典，失败返回 None
        """
        logger.info(f"获取笔记详情：{note_id}")

        for attempt in range(retry):
            try:
                url = f"{CRAWLER_CONFIG['NOTE_DETAIL_URL']}{note_id}"
                response = self.session.get(url, timeout=30)
                response.raise_for_status()

                html = response.text

                # 解析笔记详情
                detail = self._parse_note_detail(html, note_id)

                if detail:
                    return detail
                else:
                    logger.warning(f"无法解析笔记详情：{note_id}")
                    return None

            except requests.exceptions.RequestException as e:
                logger.warning(f"第 {attempt + 1} 次请求失败：{e}")
                if attempt < retry - 1:
                    delay = CRAWLER_CONFIG["RETRY_DELAY"] * (2 ** attempt)
                    time.sleep(delay)
                    continue
            except Exception as e:
                logger.error(f"解析错误：{e}")
                return None

        return None

    def _parse_note_detail(self, html: str, note_id: str) -> Optional[dict]:
        """
        解析笔记详情页面

        Args:
            html: 页面 HTML
            note_id: 笔记 ID

        Returns:
            笔记详情字典
        """
        import re
        import json

        try:
            # 查找页面数据
            pattern = r'window\.__INITIAL_STATE__\s*=\s*({.+?})</script>'
            match = re.search(pattern, html, re.DOTALL)

            if not match:
                return None

            data = json.loads(match.group(1))

            # 提取笔记数据
            note_data = None
            if "note" in data:
                note_data = data["note"]
            elif "noteDetail" in data:
                note_data = data["noteDetail"]

            if not note_data:
                return None

            # 提取字段
            note_info = note_data.get("note", {}) if isinstance(note_data, dict) else note_data

            # 作者信息
            user_info = note_data.get("user", {})
            author = user_info.get("nickname", "") if isinstance(user_info, dict) else ""

            # 标题和正文
            title = note_info.get("title", "")
            content = note_info.get("desc", "")

            # 互动数据
            interactions = note_info.get("interactInfo", {})
            like_count = interactions.get("likedCount", 0)
            collect_count = interactions.get("collectedCount", 0)
            comment_count = interactions.get("commentCount", 0)

            # 封面
            images = note_info.get("imageList", [])
            cover_url = images[0].get("url", "") if images else ""

            # 如果没有图片，检查是否是视频
            if not cover_url:
                video_info = note_info.get("video", {})
                cover_url = video_info.get("coverUrl", "") if isinstance(video_info, dict) else ""

            # 发布时间
            time_info = note_info.get("time", {})
            publish_time = time_info if isinstance(time_info, str) else ""

            return {
                "序号": 0,  # 由调用方设置
                "作者": clean_text(author),
                "标题": clean_text(title),
                "点赞数": int(like_count) if like_count else 0,
                "收藏数": int(collect_count) if collect_count else 0,
                "评论数": int(comment_count) if comment_count else 0,
                "封面 URL": cover_url,
                "笔记链接": f"{CRAWLER_CONFIG['NOTE_DETAIL_URL']}{note_id}",
                "正文内容": clean_text(content),
                "发布时间": publish_time,
                "状态": "成功",
            }

        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败：{e}")
            return None
        except Exception as e:
            logger.error(f"解析失败：{e}")
            return None

    def crawl(self, keyword: str, limit: int = 30) -> list:
        """
        执行完整爬取流程

        Args:
            keyword: 搜索关键词
            limit: 爬取数量限制

        Returns:
            笔记数据列表
        """
        logger.info(f"开始爬取，关键词：{keyword}, 数量：{limit}")

        # Step 1: 搜索获取笔记列表
        note_ids = self.search_notes(keyword, limit)

        if not note_ids:
            logger.error("未找到任何笔记")
            return []

        # Step 2: 获取每篇笔记详情
        notes = []
        for i, note_id in enumerate(note_ids[:limit], 1):
            logger.info(f"爬取进度：{i}/{limit}")
            detail = self.get_note_detail(note_id)

            if detail:
                notes.append(detail)
            else:
                # 标记为无法访问
                notes.append({
                    "序号": i,
                    "作者": "",
                    "标题": "",
                    "点赞数": 0,
                    "收藏数": 0,
                    "评论数": 0,
                    "封面 URL": "",
                    "笔记链接": f"{CRAWLER_CONFIG['NOTE_DETAIL_URL']}{note_id}",
                    "正文内容": "",
                    "发布时间": "",
                    "状态": "无法访问",
                })

        return notes
