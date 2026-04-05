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
    NOTE_URL_PATTERNS = (
        "/search_result/",
        "/explore/",
        "/discovery/item/",
    )
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
                const seenIds = new Set();
                
                // 使用多种选择器匹配笔记卡片
                const selectors = [
                    'section.note-item',
                    'div[role="listitem"]',
                    'div.note-item',
                    'article[role="article"]',
                    'div[class*="note-item"]',
                    'div[class*="NoteItem"]',
                    'a[href*="/explore/"]',
                    'a[href*="/search_result/"]',
                    'a[href*="/discovery/item/"]'
                ];
                
                const elements = [];
                for (const selector of selectors) {
                    try {
                        const els = document.querySelectorAll(selector);
                        els.forEach(el => elements.push(el));
                    } catch (e) {}
                }
                
                elements.forEach(element => {
                    // 如果是 a 标签，直接使用
                    let linkElement = element.tagName === 'A' ? element : null;
                    
                    // 如果不是 a 标签，查找内部的 a 标签
                    if (!linkElement) {
                        linkElement = element.querySelector('a[href*="/explore/"], a[href*="/search_result/"], a[href*="/discovery/item/"]');
                    }
                    
                    if (!linkElement) return;
                    
                    const href = linkElement.getAttribute('href') || linkElement.href || '';
                    const idMatch = href.match(/\\/(?:search_result|explore|discovery\\/item)\\/([a-zA-Z0-9]+)/);
                    if (!idMatch) return;
                    
                    const noteId = idMatch[1];
                    if (seenIds.has(noteId)) return;
                    seenIds.add(noteId);
                    
                    // 检查元素是否可见
                    const style = window.getComputedStyle(element);
                    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return;
                    
                    const rect = element.getBoundingClientRect();
                    if (rect.width === 0 || rect.height === 0) return;
                    
                    cards.push({
                        id: noteId,
                        href: href,
                        top: rect.top,
                        left: rect.left
                    });
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

    def _extract_note_cards_from_html(self, html: str) -> list:
        """浠?HTML 蹇収涓彁鍙栫瑪璁?ID 鍜岄摼鎺ワ紝鐢ㄤ簬 DOM 鎻愬彇澶辫触鏃剁殑鍏滃簳"""
        cards_by_id = {}
        for href in re.findall(r'href="([^"]+)"', html):
            id_match = re.search(r'/(?:search_result|explore|discovery/item)/([a-zA-Z0-9]+)', href)
            if not id_match:
                continue

            note_id = id_match.group(1)
            current = cards_by_id.get(note_id)
            if current is None:
                cards_by_id[note_id] = {"id": note_id, "href": href}
                continue

            if "/search_result/" in href and "/search_result/" not in current["href"]:
                current["href"] = href

        return list(cards_by_id.values())

    def _find_card_element(self, page: Page, note_id: str):
        """鏍规嵁褰撳墠椤甸潰缁撴瀯瀵绘壘鍙偣鍑荤殑绗旇鍗＄墖鍏冪礌"""
        selectors = [
            f'a[href*="/search_result/{note_id}"]',
            f'a[href*="/explore/{note_id}"]',
            f'a[href*="/discovery/item/{note_id}"]',
        ]
        for selector in selectors:
            element = page.locator(selector).first
            if element.count() > 0:
                return element
        return None

    def _parse_note_info_from_state(self, note_state: dict, note_id: str) -> Optional[dict]:
        """Parse detail from the note store instead of treating the whole module as a note."""
        if not note_state:
            return None

        detail_map = note_state.get("noteDetailMap") or {}
        candidate_ids = [note_id, note_state.get("currentNoteId"), *detail_map.keys()]
        visited = set()

        for candidate_id in candidate_ids:
            if not candidate_id or candidate_id in visited:
                continue
            visited.add(candidate_id)

            detail_entry = detail_map.get(candidate_id)
            if not detail_entry:
                continue

            note = detail_entry.get("note") or detail_entry
            user = detail_entry.get("user") or note.get("user") or {}
            interact_info = note.get("interactInfo") or note.get("interact_info") or {}
            image_list = note.get("imageList") or note.get("image_list") or []
            video = note.get("video") or {}

            title = note.get("title") or ""
            desc = note.get("desc") or ""
            author = user.get("nickname") or user.get("nickName") or ""
            like_count = interact_info.get("likedCount") or interact_info.get("liked_count") or 0
            collect_count = interact_info.get("collectedCount") or interact_info.get("collected_count") or 0
            comment_count = interact_info.get("commentCount") or interact_info.get("comment_count") or 0

            cover = ""
            if image_list:
                first_image = image_list[0] or {}
                cover = (
                    first_image.get("urlDefault")
                    or first_image.get("url_default")
                    or first_image.get("url")
                    or ""
                )
            elif video.get("coverUrl") or video.get("cover_url"):
                cover = video.get("coverUrl") or video.get("cover_url") or ""

            if not any([title, desc, author, cover, like_count, collect_count, comment_count]):
                continue

            note_time = note.get("time") or detail_entry.get("currentTime") or ""
            if isinstance(note_time, (int, float)) and note_time > 0:
                note_time = time.strftime("%Y-%m-%d", time.localtime(note_time / 1000))

            return {
                "author": author,
                "title": title,
                "desc": desc,
                "likeCount": like_count,
                "collectCount": collect_count,
                "commentCount": comment_count,
                "cover": cover,
                "time": note_time,
            }

        return None

    def _scroll_to_element(self, page: Page, card: dict):
        """滚动到指定元素"""
        page.evaluate(f"""
            () => {{
                window.scrollTo(0, {max(0, int(card.get('top', 0) - 100))});
            }}
        """)
        page.wait_for_timeout(500)

    def _get_note_detail_from_page(self, page: Page, note_id: str) -> Optional[dict]:
        """从当前页面获取笔记详情"""
        try:
            # 等待页面加载完成（等待 URL 包含 note_id）
            try:
                page.wait_for_url(f"*{note_id}*", timeout=5000)
            except:
                pass
            
            # 等待笔记内容加载
            try:
                page.wait_for_selector('[class*="note"], article', timeout=3000)
            except:
                pass
            
            page.wait_for_timeout(2000)

            # 方法 1: 从 __INITIAL_STATE__ 获取数据（最可靠，在页面内先处理好）
            note_info = page.evaluate("""
                (noteId) => {
                    const state = window.__INITIAL_STATE__;
                    if (!state || !state.note) return null;
                    
                    const noteDetailMap = state.note.noteDetailMap || {};
                    // 优先使用 noteId 查找
                    let detailEntry = noteDetailMap[noteId];
                    
                    // 如果找不到，尝试使用当前 noteId
                    if (!detailEntry) {
                        const currentId = Object.keys(noteDetailMap)[0];
                        if (currentId) {
                            detailEntry = noteDetailMap[currentId];
                        }
                    }
                    
                    if (!detailEntry) return null;
                    
                    const note = detailEntry.note || detailEntry;
                    const user = detailEntry.user || note.user || {};
                    const interactInfo = note.interactInfo || note.interact_info || {};
                    const imageList = note.imageList || note.image_list || [];
                    const video = note.video || {};
                    
                    const title = note.title || '';
                    const desc = note.desc || '';
                    const author = user.nickname || user.nickName || '';
                    const likeCount = interactInfo.likedCount || interactInfo.liked_count || 0;
                    const collectCount = interactInfo.collectedCount || interactInfo.collected_count || 0;
                    const commentCount = interactInfo.commentCount || interactInfo.comment_count || 0;
                    
                    let cover = '';
                    if (imageList && imageList.length > 0) {
                        const firstImg = imageList[0];
                        cover = firstImg.urlDefault || firstImg.url_default || firstImg.url || '';
                    } else if (video.coverUrl || video.cover_url) {
                        cover = video.coverUrl || video.cover_url;
                    }
                    
                    let time = note.time || '';
                    if (typeof time === 'number' && time > 0) {
                        time = new Date(time).toLocaleDateString('zh-CN');
                    }
                    
                    if (!title && !desc && !author && !cover) return null;
                    
                    return {
                        author,
                        title,
                        desc,
                        likeCount,
                        collectCount,
                        commentCount,
                        cover,
                        time
                    };
                }
            """, note_id)
            
            if note_info and any(note_info.get(field) for field in ("author", "title", "desc", "cover")):
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
            
            # 方法 2: 从 DOM 元素直接提取作为兜底
            dom_info = page.evaluate("""
                () => {
                    // 使用更精确的选择器
                    const titleEl = document.querySelector('h1#detail-title, h1.title, div[class*="title"]:first-of-type');
                    const descEl = document.querySelector('#detail-desc, .desc, .content, [class*="desc"]');
                    const authorEl = document.querySelector('[class*="user-name"], [class*="nickname"], .user-name');
                    
                    // 获取互动数据 - 使用更具体的属性选择器
                    const likeEl = document.querySelector('[class*="like-count"] span, span.count:first-of-type');
                    const collectEl = document.querySelectorAll('span.count')[1];
                    const commentEl = document.querySelectorAll('span.count')[2];
                    
                    // 获取主图
                    const imgEl = document.querySelector('article img:first-of-type, .cover img, img[src*="xiaohongshu"]');
                    
                    const getText = (el) => el ? el.textContent?.trim() || '' : '';
                    const getNumber = (el) => {
                        const text = getText(el);
                        const num = text.match(/[\\d,]+/);
                        return num ? parseInt(num[0].replace(/,/g, '')) : 0;
                    };
                    
                    const title = getText(titleEl);
                    const desc = getText(descEl);
                    const author = getText(authorEl);
                    const likeCount = getNumber(likeEl);
                    const collectCount = getNumber(collectEl);
                    const commentCount = getNumber(commentEl);
                    const cover = imgEl?.src || imgEl?.getAttribute('src') || '';
                    
                    if (!title && !desc && !author) return null;
                    
                    return {
                        author,
                        title,
                        desc,
                        likeCount,
                        collectCount,
                        commentCount,
                        cover
                    };
                }
            """)
            
            if dom_info and any(dom_info.get(field) for field in ("author", "title", "desc")):
                return {
                    "序号": 0,
                    "作者": clean_text(dom_info.get("author", "")),
                    "标题": clean_text(dom_info.get("title", "")),
                    "点赞数": format_number(str(dom_info.get("likeCount", 0))),
                    "收藏数": format_number(str(dom_info.get("collectCount", 0))),
                    "评论数": format_number(str(dom_info.get("commentCount", 0))),
                    "封面 URL": dom_info.get("cover", ""),
                    "笔记链接": f"{CRAWLER_CONFIG['NOTE_DETAIL_URL']}{note_id}",
                    "正文内容": clean_text(dom_info.get("desc", "")),
                    "发布时间": "",
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
                
                # 先提取一次笔记（不筛选）
                logger.info("提取初始笔记列表...")
                cards = self._extract_note_cards(page)
                if not cards:
                    cards = self._extract_note_cards_from_html(page.content())
                logger.info(f"初始页面找到 {len(cards)} 篇笔记")
                
                # 如果没有笔记，尝试点击筛选
                if len(cards) == 0:
                    logger.info("尝试点击筛选...")
                    self._click_filter(page)
                    page.wait_for_timeout(3000)
                    
                    # 再次提取
                    cards = self._extract_note_cards(page)
                    if not cards:
                        cards = self._extract_note_cards_from_html(page.content())
                    logger.info(f"筛选后找到 {len(cards)} 篇笔记")
                
                # 如果还是没有，尝试直接滚动
                if len(cards) == 0:
                    logger.info("尝试滚动加载...")
                    for i in range(3):
                        page.evaluate("window.scrollBy(0, 500)")
                        page.wait_for_timeout(2000)
                        cards = self._extract_note_cards(page)
                        if not cards:
                            cards = self._extract_note_cards_from_html(page.content())
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
                            card_element = self._find_card_element(page, card["id"])
                            if card_element:
                                card_element.scroll_into_view_if_needed()
                                page.wait_for_timeout(300)
                                card_element.click()
                            else:
                                logger.warning(f"找不到笔记元素：{card['id']}")
                                crawled_ids.add(card['id'])
                                continue
                            
                            page.wait_for_timeout(3000)
                            
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
                            crawled_ids.add(card['id'])
                            logger.error(f"爬取笔记 {card['id']} 失败：{e}")
                            try:
                                page.go_back()
                                page.wait_for_timeout(2000)
                            except:
                                pass
                    
                    # 检查是否已达到目标数量
                    if len(notes) >= limit:
                        logger.info(f"已达到目标数量 {limit}，停止爬取")
                        break
                    
                    # 滚动页面，加载更多笔记
                    logger.info("滚动页面加载更多...")
                    page.evaluate("window.scrollBy(0, 1000)")
                    page.wait_for_timeout(2000)
                    cards = self._extract_note_cards(page)
                    if not cards:
                        cards = self._extract_note_cards_from_html(page.content())
                    
                    # 如果没有新笔记，停止爬取
                    if not cards:
                        logger.warning("没有更多笔记了")
                        break
                
                logger.info(f"爬取完成，共获取 {len(notes)} 篇笔记")
                browser.close()
                return notes
                
        except Exception as e:
            logger.error(f"爬取失败：{e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
