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
                '--force-device-scale-factor=1',  # 强制 100% 缩放
            ]
        )
        context = browser.new_context(
            user_agent=self.headers["User-Agent"],
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=1,  # 设备缩放因子设为 1
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
        """从笔记详情页获取数据（基于 F12 看到的精确选择器）"""
        try:
            # 等待页面加载完成
            try:
                page.wait_for_url(f"*{note_id}*", timeout=5000)
            except:
                pass
            
            # 等待笔记内容加载
            try:
                page.wait_for_selector('#detail-title', timeout=3000)
            except:
                pass
            
            # 滚动到顶部确保互动数据加载
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(1500)
            
            # 等待互动数据加载（等待点赞数出现）
            try:
                page.wait_for_selector('.engage-bar span.count, [class*="interact"] span.count', timeout=3000)
            except:
                pass
            
            page.wait_for_timeout(1000)

            # 从 DOM 元素直接提取（根据 F12 截图的精确选择器）
            note_info = page.evaluate("""
                () => {
                    // 标题：div#detail-title.title
                    const titleEl = document.querySelector('#detail-title');
                    
                    // 描述：div#detail-desc.desc 或内部的 span
                    const descEl = document.querySelector('#detail-desc');
                    
                    // 作者：在 author-container 内
                    const authorEl = document.querySelector('.author-container .username, .author .username, [class*="user-name"]');
                    
                    // 互动数据：.engage-bar 内的 span.count（这是笔记本身的点赞/收藏/评论）
                    // 使用 querySelectorAll 获取所有 count，然后按顺序取
                    const engageBar = document.querySelector('.engage-bar');
                    const countEls = engageBar ? engageBar.querySelectorAll('span.count') : [];
                    
                    // 获取主图
                    const imgEl = document.querySelector('.img-container img, .swiper-slide-active img, article img');
                    
                    // 视频封面
                    const videoEl = document.querySelector('video');
                    
                    const getText = (el) => {
                        if (!el) return '';
                        return el.textContent?.trim() || '';
                    };
                    
                    const getNumber = (el) => {
                        const text = getText(el);
                        // 处理带"万"的数字，如 "1.2 万" = 12000
                        if (text.includes('万')) {
                            const wanMatch = text.match(/([\\d.]+)\\s*万/);
                            if (wanMatch) {
                                return Math.round(parseFloat(wanMatch[1]) * 10000);
                            }
                        }
                        // 处理普通数字，去除逗号
                        const num = text.match(/[\\d,]+/);
                        return num ? parseInt(num[0].replace(/,/g, '')) : 0;
                    };
                    
                    const title = getText(titleEl);
                    // 描述可能包含多个 span，取所有文本
                    const desc = descEl ? descEl.textContent?.trim() || '' : '';
                    const author = getText(authorEl);
                    
                    // 按顺序获取点赞、收藏、评论数（从 engage-bar 获取，确保是笔记本身的）
                    const likeCount = countEls.length > 0 ? getNumber(countEls[0]) : 0;
                    const collectCount = countEls.length > 1 ? getNumber(countEls[1]) : 0;
                    const commentCount = countEls.length > 2 ? getNumber(countEls[2]) : 0;
                    
                    // 获取封面
                    let cover = '';
                    if (imgEl) {
                        cover = imgEl.src || imgEl.getAttribute('src') || '';
                    } else if (videoEl) {
                        cover = videoEl.poster || '';
                    }
                    
                    if (!title && !author) return null;
                    
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
            
            if note_info and any(note_info.get(field) for field in ("author", "title", "desc", "cover", "likeCount")):
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
                
                # 设置页面缩放为 100%
                page.evaluate("document.body.style.zoom = '1'")
                
                # 访问搜索页面
                url = f"{CRAWLER_CONFIG['BASE_URL']}/search_result?keyword={keyword}&source=web_explore_feed"
                logger.info(f"访问搜索页面：{url}")
                page.goto(url, timeout=60000)
                page.wait_for_timeout(5000)
                
                # 设置页面缩放为 100%
                page.evaluate("document.documentElement.style.zoom = '1'")
                
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
                failed_counts = {}  # 记录每个 ID 的失败次数
                consecutive_failures = 0  # 连续失败次数
                max_consecutive_failures = 10  # 最大连续失败次数
                scroll_count = 0  # 滚动次数
                max_scroll_count = 20  # 最大滚动次数
                
                while len(notes) < limit:
                    if not cards:
                        logger.warning("没有找到更多笔记")
                        break
                    
                    # 检查连续失败次数
                    if consecutive_failures >= max_consecutive_failures:
                        logger.warning(f"连续失败 {consecutive_failures} 次，停止爬取")
                        break
                    
                    # 检查滚动次数
                    if scroll_count >= max_scroll_count:
                        logger.warning(f"已达到最大滚动次数 {max_scroll_count}，停止爬取")
                        break
                    
                    # 逐个点击笔记
                    for card in cards:
                        if len(notes) >= limit:
                            break
                        
                        if card['id'] in crawled_ids:
                            continue
                        
                        # 如果这个 ID 已经失败过 3 次，跳过
                        if failed_counts.get(card['id'], 0) >= 3:
                            logger.info(f"ID {card['id']} 已失败 3 次，跳过")
                            crawled_ids.add(card['id'])
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
                                failed_counts[card['id']] = failed_counts.get(card['id'], 0) + 1
                                consecutive_failures += 1
                                crawled_ids.add(card['id'])
                                continue
                            
                            page.wait_for_timeout(3000)
                            
                            # 设置详情页缩放为 100%
                            page.evaluate("document.body.style.zoom = '1'")
                            page.evaluate("document.documentElement.style.zoom = '1'")
                            page.wait_for_timeout(500)
                            
                            # 获取详情
                            detail = self._get_note_detail_from_page(page, card['id'])
                            
                            if detail:
                                detail["序号"] = len(notes) + 1
                                notes.append(detail)
                                crawled_ids.add(card['id'])
                                consecutive_failures = 0  # 重置连续失败计数
                                logger.info(f"成功获取笔记：{detail['标题'][:20] if detail['标题'] else '无标题'}... | 点赞：{detail['点赞数']}")
                            else:
                                logger.warning(f"无法获取笔记详情：{card['id']}")
                                failed_counts[card['id']] = failed_counts.get(card['id'], 0) + 1
                                consecutive_failures += 1
                                crawled_ids.add(card['id'])
                            
                            # 返回搜索结果页
                            page.go_back()
                            page.wait_for_timeout(2000)
                            
                        except Exception as e:
                            failed_counts[card['id']] = failed_counts.get(card['id'], 0) + 1
                            consecutive_failures += 1
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
                    scroll_count += 1
                    
                    cards = self._extract_note_cards(page)
                    if not cards:
                        cards = self._extract_note_cards_from_html(page.content())
                    
                    # 如果没有新笔记，停止爬取
                    if not cards:
                        logger.warning("没有更多笔记了")
                        break
                    
                    # 检查是否还有未爬取的笔记
                    remaining_cards = [c for c in cards if c['id'] not in crawled_ids]
                    if not remaining_cards:
                        logger.info("当前页面没有更多未爬取的笔记")
                
                logger.info(f"爬取完成，共获取 {len(notes)} 篇笔记")
                browser.close()
                return notes
                
        except Exception as e:
            logger.error(f"爬取失败：{e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
