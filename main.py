# main.py

import sys
import traceback
from config import CRAWLER_CONFIG
from input import get_keyword, get_cookie, validate_inputs
from utils import parse_cookie, setup_logger
from storage import create_logs_dir
from crawler import XiaohongshuCrawler
from storage import save_to_csv, create_output_dir

# 配置日志
logger = setup_logger("main")


def main():
    """主函数"""
    print("=" * 60)
    print("小红书爆款笔记爬取器")
    print("=" * 60)

    try:
        # Step 1: 获取用户输入
        keyword = get_keyword()
        cookie_str = get_cookie()

        # Step 2: 解析 Cookie
        cookie = parse_cookie(cookie_str)

        # Step 3: 验证输入
        if not validate_inputs(keyword, cookie):
            logger.error("输入验证失败，程序退出")
            sys.exit(1)

        # Step 4: 创建输出目录
        create_output_dir()
        create_logs_dir()

        # Step 5: 初始化爬虫
        logger.info("初始化爬虫...")
        crawler = XiaohongshuCrawler(cookie)

        # Step 6: 执行爬取
        print("\n开始爬取...")
        notes = crawler.crawl(keyword, CRAWLER_CONFIG["LIMIT"])

        if not notes:
            logger.warning("未爬取到任何数据")
            sys.exit(0)

        # Step 7: 保存数据
        filepath = save_to_csv(notes, keyword)

        # Step 8: 输出统计
        success_count = sum(1 for n in notes if n.get("状态") == "成功")
        fail_count = len(notes) - success_count

        print("\n" + "=" * 60)
        print("爬取完成!")
        print(f"  总计：{len(notes)} 篇")
        print(f"  成功：{success_count} 篇")
        print(f"  失败：{fail_count} 篇")
        print(f"  文件：{filepath}")
        print("=" * 60)

    except KeyboardInterrupt:
        logger.error("用户中断程序")
        sys.exit(1)
    except Exception as e:
        logger.error(f"程序异常：{e}")
        logger.debug(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
