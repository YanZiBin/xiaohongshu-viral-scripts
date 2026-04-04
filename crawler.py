# crawler.py

import time
import json
import re
from typing import Optional
from playwright.sync_api import sync_playwright, Page
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
        self.cookie_str = "; ".join([f"{k}={v}" for k, v in cookie.items()])

    def _setup_browser(self, p):
        """设置浏览器"""
        browser = p.chromium.launch(
            headless=False,
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
        
        return browser, context

    def _click_filter(self, page: Page):
        """点击筛选按钮，选择'一周内'"""
        try:
            # 点击筛选按钮
            filter_btn = page.locator('button:has-text("筛选"), div:has-text("筛选"), span:has-text("筛选")').first
            if filter_btn.is_visible():
                filter_btn.click()
                page.wait_for_timeout(1000)
                
                # 点击"一周内"
                one_week_btn = page.locator('button:has-text("一周内"), div:has-text("一周内"), span:has-text("一周内")').first
                if one_week_btn.is_visible():
                    one_week_btn.click()
                    page.wait_for_timeout(2000)
                    logger.info("已筛选'一周内'")
        except Exception as e:
            logger.warning(f"筛选失败：{e}")

    def _extract_note_cards(self, page: Page) -> list:
        """获取当前页面所有笔记卡片的位置信息"""
        return page.evaluate("""
            () => {
                const cards = [];
                const links = document.querySelectorAll('a[href*="/discovery/item/"]');
                const seenIds = new Set();
                
                links.forEach(link => {
                    const href = link.href;
                    const idMatch = href.match(/\\/discovery\\/item\\/([a-zA-Z0-9]+)/);
                    if (idMatch && !seenIds.has(idMatch[1])) {
                        seenIds.add(idMatch[1]);
                        const rect = link.getBoundingClientRect();
                        cards.push({
                            id: idMatch[1],
                            href: href,
                            top: rect.top,
                            left: rect.left
                        });
                    }
                });
                
                // 按位置排序（从上到下，从左到右）
                cards.sort((a, b) => {
                    const rowDiff = Math.abs(a.top - b.top);
                    if (rowDiff < 50) {
                        return a.left - b.left;  // 同一行，按从左到右
                    }
                    return a.top - b.top;  // 不同行，按从上到下
                });
                
                return cards;
            }
        """)

    def _scroll_to_element(self, page: Page, card: dict):
        """滚动到指定元素"""
        page.evaluate(f"""
            () => {{
                window.scrollTo(0, {max(0, int(card['top'] - 100))});
            }}
        """)
        page.wait_for_timeout(500)

    def _get_note_detail_from_page(self, page: Page, note_id: str) -> Optional[dict]:
        """从当前页面获取笔记详情"""
        try:
            # 等待页面加载
            page.wait_for_timeout(3000)
            
            # 尝试从 __INITIAL_STATE__ 获取数据
            note_info = page.evaluate("""
                () => {
                    const state = window.__INITIAL_STATE__;
                    if (!state) return null;
                    
                    // 尝试多个可能的路径
                    let noteData = state.note || state.noteDetail || state.noteDetailTab;
                    if (!noteData) return null;
                    
                    // 获取笔记信息
                    const note = noteData.note || noteData;
                    const user = noteData.user || note.user || {};
                    const interactInfo = note.interactInfo || note.interact_info || {};
                    const imageList = note.imageList || note.image_list || [];
                    const video = note.video || {};
                    
                    // 获取标题和内容
                    let title = note.title || '';
                    let desc = note.desc || '';
                    
                    // 获取封面
                    let cover = '';
                    if (imageList.length > 0) {
                        cover = imageList[0].urlDefault || imageList[0].url_default || imageList[0].url || '';
                    } else if (video.coverUrl || video.cover_url) {
                        cover = video.coverUrl || video.cover_url;
                    }
                    
                    // 获取时间
                    let time = note.time || '';
                    if (typeof time === 'number' && time > 0) {
                        time = new Date(time).toLocaleDateString('zh-CN');
                    }
                    
                    return {
                        author: user.nickname || user.nickName || '',
                        title: title,
                        desc: desc,
                        likeCount: interactInfo.likedCount || interactInfo.liked_count || 0,
                        collectCount: interactInfo.collectedCount || interactInfo.collected_count || 0,
                        commentCount: interactInfo.commentCount || interactInfo.comment_count || 0,
                        cover: cover,
                        time: time
                    };
                }
            """)
            
            if note_info:
                return {
                    "序号": 0,
                    "作者": clean_text(note_info.get("author", "")),
                    "标题": clean_text(note_info.get("title", "")),
                    "点赞数": format_number(str(note_info.get("likeCount", 0))),
                    "收藏数": format_number(str(note_info.get("collectCount", 0))),
                    "评论数": format_number(str(note_info.get("commentCount", 0))),
                    "封面 URL": note_info.get("cover", ""),
                    "笔记链接": f"{CRAWLER_CONFIG['NOTE_DETAIL_URL']}{note_id}",
                    "正文内容": clean_text(note_info.get("desc", "")),
                    "发布时间": str(note_info.get("time", "")),
                    "状态": "成功",
                }
            
            return None
            
        except Exception as e:
            logger.error(f"获取笔记详情失败：{e}")
            return None

    def crawl(self, keyword: str, limit: int = 30) -> list:
        """
        爬取笔记（模拟真实用户操作）

        Args:
            keyword: 搜索关键词
            limit: 返回数量限制

        Returns:
            笔记详情列表
        """
        logger.info(f"开始爬取，关键词：{keyword}, 数量：{limit}")
        notes = []

        try:
            with sync_playwright() as p:
                browser, context = self._setup_browser(p)
                page = context.new_page()
                
                # 访问搜索页面
                url = f"{CRAWLER_CONFIG['BASE_URL']}/search_result?keyword={keyword}&source=web_explore_feed"
                logger.info(f"访问搜索页面：{url}")
                page.goto(url, timeout=60000)
                page.wait_for_timeout(5000)
                
                # 保存初始截图
                page.screenshot(path="debug_01_initial.png")
                logger.info("已保存初始截图")
                
                # 先提取一次笔记（不筛选）
                logger.info("提取初始笔记列表...")
                cards = self._extract_note_cards(page)
                logger.info(f"初始页面找到 {len(cards)} 篇笔记")
                
                # 如果没有笔记，尝试点击筛选
                if len(cards) == 0:
                    logger.info("尝试点击筛选...")
                    self._click_filter(page)
                    page.wait_for_timeout(3000)
                    page.screenshot(path="debug_02_filtered.png")
                    
                    # 再次提取
                    cards = self._extract_note_cards(page)
                    logger.info(f"筛选后找到 {len(cards)} 篇笔记")
                
                # 如果还是没有，尝试直接滚动
                if len(cards) == 0:
                    logger.info("尝试滚动加载...")
                    for i in range(3):
                        page.evaluate("window.scrollBy(0, 500)")
                        page.wait_for_timeout(2000)
                        page.screenshot(path=f"debug_03_scroll_{i}.png")
                        cards = self._extract_note_cards(page)
                        if cards:
                            logger.info(f"滚动后找到 {len(cards)} 篇笔记")
                            break
                
                # 开始爬取笔记
                crawled_ids = set()
                
                while len(notes) < limit:
                    if not cards:
                        logger.warning("没有找到更多笔记")
                        break
                    
                    # 逐个点击笔记
                    for card in cards:
                        if len(notes) >= limit:
                            break
                        
                        if card['id'] in crawled_ids:
                            continue
                        
                        logger.info(f"爬取笔记 {len(notes)+1}/{limit}: {card['id']}")
                        
                        try:
                            # 滚动到元素位置
                            self._scroll_to_element(page, card)
                            page.wait_for_timeout(500)
                            
                            # 点击笔记
                            card_element = page.locator(f'a[href*="/discovery/item/{card["id"]}"]').first
                            if card_element.is_visible():
                                card_element.click()
                            else:
                                logger.warning(f"找不到笔记元素：{card['id']}")
                                continue
                            
                            page.wait_for_timeout(3000)
                            page.screenshot(path=f"debug_note_{card['id']}.png")
                            
                            # 获取详情
                            detail = self._get_note_detail_from_page(page, card['id'])
                            
                            if detail:
                                detail["序号"] = len(notes) + 1
                                notes.append(detail)
                                crawled_ids.add(card['id'])
                                logger.info(f"成功获取笔记：{detail['标题'][:20] if detail['标题'] else '无标题'}...")
                            else:
                                logger.warning(f"无法获取笔记详情：{card['id']}")
                                notes.append({
                                    "序号": len(notes) + 1,
                                    "作者": "",
                                    "标题": "",
                                    "点赞数": 0,
                                    "收藏数": 0,
                                    "评论数": 0,
                                    "封面 URL": "",
                                    "笔记链接": f"{CRAWLER_CONFIG['NOTE_DETAIL_URL']}{card['id']}",
                                    "正文内容": "",
                                    "发布时间": "",
                                    "状态": "无法访问",
                                })
                                crawled_ids.add(card['id'])
                            
                            # 返回搜索结果页
                            page.go_back()
                            page.wait_for_timeout(2000)
                            
                        except Exception as e:
                            logger.error(f"爬取笔记 {card['id']} 失败：{e}")
                            try:
                                page.go_back()
                                page.wait_for_timeout(2000)
                            except:
                                pass
                    
                    # 滚动页面，加载更多笔记
                    logger.info("滚动页面加载更多...")
                    page.evaluate("window.scrollBy(0, 800)")
                    page.wait_for_timeout(3000)
                    cards = self._extract_note_cards(page)
                
                browser.close()
                return notes
                
        except Exception as e:
            logger.error(f"爬取失败：{e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
