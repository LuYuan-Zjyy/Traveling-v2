#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
步骤1: 用浏览器手动通过验证码，然后自动导出 Cookie

运行后会打开一个浏览器窗口:
1. 会自动访问马蜂窝
2. 手动完成滑块验证码
3. 页面正常加载后，按回车键导出 Cookie
"""

import json
import os
from playwright.sync_api import sync_playwright

COOKIE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mfw_cookies.json")


def main():
    print("=" * 60)
    print("  马蜂窝 Cookie 导出工具")
    print("=" * 60)
    print()
    print("  浏览器即将打开，请手动完成滑块验证码。")
    print("  验证通过页面正常显示后，回到这里按回车。")
    print()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
        )
        page = ctx.new_page()

        print("  正在打开马蜂窝...")
        page.goto("https://www.mafengwo.cn/travel-scenic-spot/mafengwo/12058.html", timeout=60000)

        input("\n>>> 验证码通过、页面加载完成后，按回车键导出 Cookie <<<\n")

        # 导出 cookies
        cookies = ctx.cookies()
        with open(COOKIE_FILE, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)

        print(f"  Cookie 已保存到: {COOKIE_FILE}")
        print(f"  共 {len(cookies)} 条 Cookie")

        browser.close()

    print("\n  现在可以运行爬虫了:")
    print("    python run_all.py --only 2")
    print("    python run_all.py --only 3")


if __name__ == "__main__":
    main()
