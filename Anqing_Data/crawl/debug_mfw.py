"""调试马蜂窝页面结构"""
from playwright.sync_api import sync_playwright
import time
import re

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        viewport={"width": 1920, "height": 1080},
        locale="zh-CN"
    )
    page = ctx.new_page()

    url = "https://www.mafengwo.cn/travel-scenic-spot/mafengwo/12058.html"
    print(f"Loading: {url}")
    page.goto(url, wait_until="networkidle", timeout=60000)
    time.sleep(8)

    print(f"TITLE: {page.title()}")
    print(f"FINAL URL: {page.url}")

    html = page.content()
    print(f"HTML length: {len(html)}")

    # 查找 /i/ 链接
    i_links = re.findall(r'href=["\']([^"\']*?/i/\d+\.html)["\']', html)
    print(f"\n/i/ links in HTML: {len(i_links)}")
    for m in i_links[:20]:
        print(f"  {m}")

    # 查找 /poi/ 链接
    poi_links = re.findall(r'href=["\']([^"\']*?/poi/\d+\.html)["\']', html)
    print(f"\n/poi/ links in HTML: {len(poi_links)}")
    for m in poi_links[:20]:
        print(f"  {m}")

    # 保存完整 HTML
    with open("debug_page.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nSaved full HTML to debug_page.html")

    # 截图
    page.screenshot(path="debug_screenshot.png", full_page=False)
    print("Saved screenshot to debug_screenshot.png")

    browser.close()
    print("Done.")
