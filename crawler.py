# crawler.py

import time
import json
import re
import requests
from typing import Optional
from playwright.sync_api import sync_playwright
from config import CRAWLER_CONFIG, CSV_FIELDS
from utils import build_headers, clean_text, setup_logger, format_number

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
        self.cookie_str = "; ".join([f"{k}={v}" for k, v in cookie.items()])

    def search_notes(self, keyword: str, limit: int = 30) -> list:
        """
        搜索笔记（使用 Playwright 模拟真实浏览器）

        Args:
            keyword: 搜索关键词
            limit: 返回数量限制

        Returns:
            笔记 ID 列表
        """
        logger.info(f"开始搜索关键词：{keyword}")

        try:
            with sync_playwright() as p:
                # 启动浏览器（有头模式，便于调试）
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                    ]
                )
                context = browser.new_context(
                    user_agent=self.headers["User-Agent"],
                    viewport={"width": 1920, "height": 1080},
                )
                
                # 设置 Cookie
                context.add_cookies([{
                    "name": k,
                    "value": v,
                    "domain": ".xiaohongshu.com",
                    "path": "/",
                } for k, v in self.cookie.items()])
                
                page = context.new_page()
                
                # 访问搜索页面
                url = f"{CRAWLER_CONFIG['BASE_URL']}/search_result?keyword={keyword}&source=web_explore_feed"
                logger.info(f"访问搜索页面：{url}")
                page.goto(url, timeout=60000)
                
                # 等待页面初始加载
                page.wait_for_timeout(5000)
                
                # 滚动页面加载更多内容
                logger.info("滚动页面加载数据...")
                for i in range(5):
                    page.evaluate("window.scrollBy(0, 500)")
                    page.wait_for_timeout(1500)
                
                # 从 DOM 提取笔记卡片信息
                logger.info("从 DOM 提取笔记数据...")
                note_data = page.evaluate("""
                    () => {
                        // 查找所有笔记卡片
                        const cards = document.querySelectorAll('[class*="note-card"], [class*="note-item"], [class*="feed-item"]');
                        console.log('找到卡片数量:', cards.length);
                        
                        const notes = [];
                        cards.forEach((card, index) => {
                            // 提取笔记 ID
                            const link = card.querySelector('a[href*="/discovery/item/"]');
                            const href = link ? link.href : '';
                            const idMatch = href.match(/\\/discovery\\/item\\/([a-zA-Z0-9]+)/);
                            const id = idMatch ? idMatch[1] : null;
                            
                            if (id) {
                                notes.push({ id });
                            }
                        });
                        
                        console.log('提取到的笔记 ID 数量:', notes.length);
                        return notes;
                    }
                """)
                
                browser.close()
                
                if note_data:
                    note_ids = [item["id"] for item in note_data if item.get("id")]
                    # 去重
                    note_ids = list(dict.fromkeys(note_ids))
                    logger.info(f"从 DOM 提取到 {len(note_ids)} 篇笔记")
                    return note_ids[:limit]
                
                logger.warning("未能从 DOM 提取到笔记 ID")
                return []
                
        except Exception as e:
            logger.error(f"搜索失败：{e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def _extract_note_ids_from_html(self, html: str) -> list:
        """
        从 HTML 中提取笔记 ID
        
        Args:
            html: 页面 HTML
        
        Returns:
            笔记 ID 列表
        """
        try:
            # 调试：保存 HTML 到文件以便分析
            with open("debug_page.html", "w", encoding="utf-8") as f:
                f.write(html[:100000])  # 只保存前 100KB
            logger.info("已保存页面 HTML 到 debug_page.html")
            
            note_ids = []
            
            # 方法 1：从 URL 中提取笔记 ID
            # 模式：/discovery/item/69cb9e60000000001f001c90
            pattern = r'/discovery/item/([a-zA-Z0-9]{24,})'
            matches = re.findall(pattern, html)
            if matches:
                note_ids = list(dict.fromkeys(matches))
                logger.info(f"从 URL 提取到 {len(note_ids)} 篇笔记")
                return note_ids[:30]
            
            # 方法 2：从 JSON 数据中提取
            # 查找 "noteId":"xxx" 或 "note_id":"xxx"
            json_pattern = r'"(?:noteId|note_id)"\s*:\s*"([a-zA-Z0-9]+)"'
            matches = re.findall(json_pattern, html)
            if matches:
                note_ids = list(dict.fromkeys(matches))
                logger.info(f"从 JSON 提取到 {len(note_ids)} 篇笔记")
                return note_ids[:30]
            
            # 方法 3：从 INITIAL_STATE 提取（如果存在）
            pattern = r'window\.__INITIAL_STATE__\s*=\s*({.+?})\s*;</script>'
            match = re.search(pattern, html, re.DOTALL)

            if match:
                json_str = match.group(1)
                logger.info(f"找到 INITIAL_STATE，长度：{len(json_str)}")
                data = self._safe_parse_json(json_str)
                if data:
                    note_ids = self._extract_note_ids_from_state(data)
                    if note_ids:
                        logger.info(f"从 INITIAL_STATE 提取到 {len(note_ids)} 篇笔记")
                        return note_ids

            logger.warning("未找到任何笔记 ID")
            return []

        except Exception as e:
            logger.warning(f"提取笔记 ID 失败：{e}")
            import traceback
            logger.warning(traceback.format_exc())
            return []

    def _safe_parse_json(self, json_str: str) -> Optional[dict]:
        """
        安全地解析 JSON 字符串，处理可能的格式问题
        
        Args:
            json_str: JSON 字符串
        
        Returns:
            解析后的字典，失败返回 None
        """
        try:
            # 首先尝试直接解析
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON 直接解析失败：{e}")
            # 尝试找到 JSON 的实际结束位置
            # 小红书的数据可能包含 </script> 之前的多余内容
            try:
                # 计算大括号匹配
                brace_count = 0
                end_pos = 0
                in_string = False
                escape_next = False
                
                for i, char in enumerate(json_str):
                    if escape_next:
                        escape_next = False
                        continue
                    
                    if char == '\\':
                        escape_next = True
                        continue
                    
                    if char == '"' and not escape_next:
                        in_string = not in_string
                        continue
                    
                    if not in_string:
                        if char == '{':
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                end_pos = i + 1
                                break
                
                if end_pos > 0:
                    fixed_json = json_str[:end_pos]
                    return json.loads(fixed_json)
            except Exception as e:
                logger.warning(f"JSON 修复失败：{e}")
                return None
        
        return None

    def _extract_notes_from_feeds(self, data: dict) -> list:
        """
        从 feed 数据中提取笔记信息
        
        Args:
            data: 页面状态数据
        
        Returns:
            笔记 ID 列表
        """
        note_ids = []
        
        try:
            # 尝试从 feed 中提取
            if "feed" in data:
                feed_data = data["feed"]
                feeds = feed_data.get("feeds", [])
                
                # 处理可能的 _rawValue 或 _value
                if isinstance(feeds, dict):
                    feeds = feeds.get("_rawValue") or feeds.get("_value") or []
                
                for item in feeds:
                    if isinstance(item, dict) and "id" in item:
                        note_ids.append(item["id"])
        except Exception as e:
            logger.warning(f"从 feed 提取笔记 ID 失败：{e}")
        
        return note_ids

    def _extract_note_ids_from_state(self, data: dict) -> list:
        """
        从 INITIAL_STATE 中提取笔记 ID

        Args:
            data: 页面状态数据

        Returns:
            笔记 ID 列表
        """
        note_ids = []

        # 首先尝试从 feed 提取（搜索结果页的主要数据结构）
        note_ids = self._extract_notes_from_feeds(data)
        if note_ids:
            return note_ids

        # 备用方案：searchResult -> notes
        try:
            if "searchResult" in data:
                notes = data["searchResult"].get("notes", [])
                note_ids = [note.get("id", "") for note in notes if note.get("id")]
        except Exception as e:
            logger.warning(f"解析 searchResult 失败：{e}")

        # 再备用：explore -> items
        try:
            if "explore" in data:
                notes = data["explore"].get("items", [])
                note_ids = [note.get("id", "") for note in notes if note.get("id")]
        except Exception as e:
            logger.warning(f"解析 explore 失败：{e}")

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
        try:
            # 查找页面数据
            pattern = r'window\.__INITIAL_STATE__\s*=\s*({.+?})\s*;</script>'
            match = re.search(pattern, html, re.DOTALL)

            if not match:
                logger.warning(f"未找到 __INITIAL_STATE__ 数据：{note_id}")
                return None

            json_str = match.group(1)
            data = self._safe_parse_json(json_str)
            
            if not data:
                logger.warning(f"无法解析 JSON 数据：{note_id}")
                return None

            # 提取笔记数据 - 尝试多个可能的路径
            note_data = None
            for key in ["note", "noteDetail", "noteDetailTab"]:
                if key in data:
                    note_data = data[key]
                    break

            if not note_data:
                logger.warning(f"未找到笔记数据：{note_id}")
                return None

            # 提取字段 - 根据实际数据结构
            # 可能是 note.note 或 noteDetail.note
            note_info = note_data.get("note", {}) if isinstance(note_data, dict) else note_data
            
            # 作者信息
            user_info = note_data.get("user", {})
            if not user_info and isinstance(note_info, dict):
                user_info = note_info.get("user", {})
            
            author = user_info.get("nickname", "") if isinstance(user_info, dict) else ""
            if not author:
                author = user_info.get("nickName", "")

            # 标题和正文
            title = note_info.get("title", "") if isinstance(note_info, dict) else ""
            content = note_info.get("desc", "") if isinstance(note_info, dict) else ""

            # 互动数据 - 尝试不同的字段名格式（驼峰和下划线）
            interactions = note_info.get("interactInfo", {}) if isinstance(note_info, dict) else {}
            if not interactions:
                interactions = note_info.get("interact_info", {})
            
            like_count = interactions.get("likedCount") or interactions.get("liked_count", 0)
            collect_count = interactions.get("collectedCount") or interactions.get("collected_count", 0)
            comment_count = interactions.get("commentCount") or interactions.get("comment_count", 0)

            # 封面 - 尝试不同的字段名
            images = note_info.get("imageList", []) if isinstance(note_info, dict) else []
            if not images:
                images = note_info.get("image_list", [])
            
            cover_url = ""
            if images and isinstance(images, list) and len(images) > 0:
                first_image = images[0] if isinstance(images[0], dict) else {}
                cover_url = first_image.get("urlDefault", "") or first_image.get("url_default", "") or first_image.get("url", "")
            
            # 如果没有图片，检查是否是视频
            if not cover_url:
                video_info = note_info.get("video", {}) if isinstance(note_info, dict) else {}
                cover_url = video_info.get("coverUrl", "") or video_info.get("cover_url", "")

            # 发布时间
            time_info = note_info.get("time", "")
            if isinstance(time_info, (int, float)) and time_info > 0:
                # 时间戳转换为日期字符串
                try:
                    from datetime import datetime
                    publish_time = datetime.fromtimestamp(time_info / 1000).strftime("%Y-%m-%d %H:%M:%S")
                except:
                    publish_time = str(time_info)
            elif isinstance(time_info, str):
                publish_time = time_info
            else:
                publish_time = ""

            return {
                "序号": 0,  # 由调用方设置
                "作者": clean_text(author),
                "标题": clean_text(title),
                "点赞数": format_number(str(like_count)) if like_count else 0,
                "收藏数": format_number(str(collect_count)) if collect_count else 0,
                "评论数": format_number(str(comment_count)) if comment_count else 0,
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
