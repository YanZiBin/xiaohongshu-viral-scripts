# api_analyzer.py
"""
用于分析小红书 API 的辅助脚本

使用方法：
1. 运行此脚本，启动本地代理服务器
2. 在浏览器中操作小红书搜索
3. 脚本会捕获并分析 API 请求
"""

import json
from mitmproxy import http, ctx


class APIAnalyzer:
    def __init__(self):
        self.api_calls = []

    def request(self, flow: http.HTTPFlow):
        # 只关注小红书 API 请求
        if "xiaohongshu.com" in flow.request.host:
            if "/api" in flow.request.path or "search" in flow.request.path:
                self.api_calls.append({
                    "method": flow.request.method,
                    "url": flow.request.url,
                    "headers": dict(flow.request.headers),
                    "body": flow.request.body,
                })
                ctx.logger.info(f"Captured: {flow.request.url}")

    def response(self, flow: http.HTTPFlow):
        if flow.response and "xiaohongshu.com" in flow.request.host:
            try:
                data = json.loads(flow.response.body)
                ctx.logger.info(f"Response keys: {list(data.keys()) if isinstance(data, dict) else 'array'}")
            except:
                pass


addons = [APIAnalyzer()]
