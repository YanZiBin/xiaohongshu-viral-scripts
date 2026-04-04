# input.py

from utils import parse_cookie, setup_logger

logger = setup_logger("input")


def get_keyword() -> str:
    """
    获取用户输入的搜索关键词

    Returns:
        关键词字符串
    """
    while True:
        keyword = input("请输入搜索关键词：").strip()
        if keyword:
            return keyword
        logger.warning("关键词不能为空，请重新输入")


def get_cookie() -> str:
    """
    获取用户输入的 Cookie

    Returns:
        Cookie 字符串
    """
    print("\n请复制小红书网页版的 Cookie：")
    print("1. 打开浏览器，访问 https://www.xiaohongshu.com/explore")
    print("2. 登录账号")
    print("3. 按 F12 打开开发者工具")
    print("4. 切换到 Network 标签，刷新页面")
    print("5. 点击任意请求，复制 Request Headers 中的完整 Cookie")
    print("6. 粘贴到下方输入框\n")

    while True:
        cookie_str = input("请输入 Cookie: ").strip()
        if cookie_str and "=" in cookie_str:
            return cookie_str
        logger.warning("Cookie 格式不正确，请确保包含 key=value 格式")


def validate_inputs(keyword: str, cookie: dict) -> bool:
    """
    验证输入的有效性

    Args:
        keyword: 关键词
        cookie: Cookie 字典

    Returns:
        是否有效
    """
    if not keyword:
        logger.error("关键词不能为空")
        return False

    if not cookie:
        logger.error("Cookie 不能为空")
        return False

    # 检查关键 Cookie 字段
    key_cookies = ["web_session", "a1", "webId"]
    missing = [k for k in key_cookies if k not in cookie]

    if missing:
        logger.warning(f"Cookie 可能不完整，缺少字段：{missing}")
        logger.info("继续尝试，如失败请重新获取 Cookie")

    return True
