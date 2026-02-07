#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
爬虫脚本2: 爬取马蜂窝安庆旅游帖子
使用 undetected-chromedriver 绕过反爬

将帖子内容保存到 Anqing_Data/tiezi/
"""

import os
import re
import json
import time
import random
from datetime import datetime

import requests as req_lib
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By

# ============================================================
# 配置
# ============================================================

BASE_URL = "https://www.mafengwo.cn"
DEST_URL = "https://www.mafengwo.cn/travel-scenic-spot/mafengwo/12058.html"
YOJI_URL_TPL = "https://www.mafengwo.cn/yj/12058/1-0-{page}.html"

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tiezi")

DELAY_MIN = 8.0
DELAY_MAX = 15.0
MAX_PAGES = 30
WAF_PAUSE = 300  # 被封后等5分钟


def random_delay(lo=DELAY_MIN, hi=DELAY_MAX):
    time.sleep(random.uniform(lo, hi))


def create_driver():
    """创建反检测浏览器"""
    options = uc.ChromeOptions()
    options.add_argument("--lang=zh-CN")
    options.add_argument("--window-size=1920,1080")
    driver = uc.Chrome(options=options, version_main=144)

    # 先登录马蜂窝 —— 首次运行需要手动登录
    print("  Checking login status...")
    driver.get("https://www.mafengwo.cn")
    time.sleep(3)
    html = driver.page_source
    # 检查是否已登录（页面中有"退出"或用户头像表示已登录）
    if "退出" not in html and "passport.mafengwo" not in html:
        print("  *** 未检测到登录状态 ***")
        print("  请在浏览器中登录马蜂窝（推荐微信扫码登录）")
        print("  登录成功后页面会显示你的头像/昵称")
        input("  >>> 登录完成后按回车继续 <<<")
        time.sleep(2)

    return driver


# ============================================================
# 爬虫逻辑
# ============================================================

def is_blocked(driver):
    """检测是否被 WAF 拦截"""
    title = driver.title or ""
    html = driver.page_source or ""
    return ("WAF" in title or "验证" in title or "拦截" in title
            or "请求已中断" in html or "安全验证" in html
            or len(html) < 3000)


def wait_for_page(driver, timeout=20):
    """等待页面加载，被封时自动等待"""
    for _ in range(timeout):
        time.sleep(1)
        if not is_blocked(driver) and len(driver.page_source or "") > 5000:
            return True
    if is_blocked(driver):
        print(f"  *** WAF 拦截！自动等待 {WAF_PAUSE}s 后重试 ***")
        print(f"  (也可以在浏览器中手动完成验证码后按回车跳过等待)")
        try:
            import select
            time.sleep(WAF_PAUSE)
        except:
            time.sleep(WAF_PAUSE)
        return True
    return True


def collect_post_links(driver):
    """收集帖子链接"""
    all_links = {}

    # 1) 目的地主页
    print(f"  Loading: {DEST_URL}")
    driver.get(DEST_URL)
    wait_for_page(driver)
    random_delay(3, 5)

    html = driver.page_source
    i_links = re.findall(r'href=["\']([^"\']*?/i/(\d+)\.html)["\']', html)
    for href, pid in i_links:
        url = href if href.startswith("http") else BASE_URL + href
        all_links[url] = ""
    print(f"    Found {len(i_links)} links from main page")

    # 从元素提取带标题
    try:
        for a in driver.find_elements(By.CSS_SELECTOR, 'a[href*="/i/"]'):
            href = a.get_attribute("href") or ""
            if re.search(r'/i/\d+\.html', href):
                url = href if href.startswith("http") else BASE_URL + href
                title = a.text.strip() if a.text else ""
                all_links[url] = title
    except:
        pass

    # 2) 游记列表页翻页
    for pg in range(1, MAX_PAGES + 1):
        url = YOJI_URL_TPL.format(page=pg)
        print(f"  Page {pg}: {url}")
        driver.get(url)
        wait_for_page(driver)
        random_delay(2, 4)

        html = driver.page_source
        i_links = re.findall(r'href=["\']([^"\']*?/i/(\d+)\.html)["\']', html)
        new_count = 0
        for href, pid in i_links:
            full_url = href if href.startswith("http") else BASE_URL + href
            if full_url not in all_links:
                all_links[full_url] = ""
                new_count += 1

        try:
            for a in driver.find_elements(By.CSS_SELECTOR, 'a[href*="/i/"]'):
                href = a.get_attribute("href") or ""
                if re.search(r'/i/\d+\.html', href):
                    full_url = href if href.startswith("http") else BASE_URL + href
                    if full_url not in all_links:
                        all_links[full_url] = a.text.strip() if a.text else ""
                        new_count += 1
        except:
            pass

        print(f"    +{new_count} new (total: {len(all_links)})")
        if new_count == 0 and pg > 2:
            print(f"    Stopping pagination")
            break

    return [{"url": u, "title": t} for u, t in all_links.items()]


def scrape_post(driver, url):
    """爬取单篇游记"""
    driver.get(url)
    wait_for_page(driver)
    random_delay(2, 3)

    # 点击"展开全文"/"查看更多" 按钮（未登录时游记可能被截断）
    for selector in [
        "a.unfold", "a._j_unfold", "[class*='unfold']", "[class*='expand']",
        "a:contains('展开')", "a:contains('查看全文')", "a:contains('阅读全文')"
    ]:
        try:
            btns = driver.find_elements(By.CSS_SELECTOR, selector)
            for btn in btns:
                if btn.is_displayed():
                    btn.click()
                    time.sleep(2)
                    break
        except:
            pass

    # 滚动到底部触发懒加载
    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(2)
    except:
        pass

    post = {}
    match = re.search(r'/i/(\d+)\.html', url)
    post["post_id"] = match.group(1) if match else ""

    post["title"] = driver.title or ""
    post["title"] = re.sub(r'\s*[-–—,，]\s*安庆.*$', '', post["title"])
    post["title"] = re.sub(r'\s*[-–—]\s*马蜂窝.*$', '', post["title"])

    # 作者
    try:
        author = driver.find_element(By.CSS_SELECTOR, ".author-name, .name a, .user-name")
        post["author"] = author.text.strip()
    except:
        post["author"] = ""

    # === 正文提取 (精确定位内容区域，过滤无关内容) ===
    html = driver.page_source
    paragraphs = []

    # 尝试精确定位游记正文容器
    content_patterns = [
        r'<div[^>]*class="[^"]*_j_content_box[^"]*"[^>]*>(.*?)</div>\s*<div[^>]*class="[^"]*(?:relate|comment|footer)',
        r'<div[^>]*class="[^"]*_j_content[^"]*"[^>]*>(.*?)</div>\s*<div[^>]*class="[^"]*(?:relate|comment|footer)',
        r'<div[^>]*class="[^"]*travel-content[^"]*"[^>]*>(.*?)</div>\s*<div[^>]*class="[^"]*(?:relate|comment|footer)',
        r'<div[^>]*class="[^"]*article-content[^"]*"[^>]*>(.*)',
    ]

    content_html = ""
    for pat in content_patterns:
        m = re.search(pat, html, re.S)
        if m:
            content_html = m.group(1)
            break

    # 如果没找到精确容器，用 selenium 定位
    if not content_html:
        for sel in ["div._j_content_box", "div._j_content", "div.travel-content",
                     "div.article-content", "div.va_con", "article"]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if el:
                    content_html = el.get_attribute("innerHTML")
                    break
            except:
                continue

    # 从内容区域提取段落
    if content_html:
        # 先移除 HTML 注释 <!-- ... -->
        cleaned_html = re.sub(r'<!--.*?-->', '', content_html, flags=re.S)
        # 移除 style/script 标签及内容
        cleaned_html = re.sub(r'<(?:style|script)[^>]*>.*?</(?:style|script)>', '', cleaned_html, flags=re.S)

        p_texts = re.findall(r'<p[^>]*>(.*?)</p>', cleaned_html, re.S)
        for pt in p_texts:
            # 去除所有 HTML 标签
            clean = re.sub(r'<[^>]+>', '', pt)
            # 去除 --> 残留
            clean = clean.replace('-->', '').replace('<!--', '')
            # 合并连续空白
            clean = re.sub(r'\s+', ' ', clean).strip()
            if clean and len(clean) > 3:
                paragraphs.append(clean)

    # 去重 + 过滤噪音
    noise_keywords = [
        '马蜂窝', '免责声明', '版权', '关注我', '点赞', '收藏',
        '举报', '违规', '广告', '下载APP', '扫码', '客服',
        '相关推荐', '你可能感兴趣', '热门目的地', '蜂蜂',
        '登录后可查看', '注册', '还没有蜂', 'Copyright',
    ]
    seen = set()
    unique = []
    for p in paragraphs:
        if p in seen:
            continue
        if any(kw in p for kw in noise_keywords):
            continue
        if len(p) < 4:  # 过滤太短的
            continue
        seen.add(p)
        unique.append(p)
    post["content"] = "\n\n".join(unique)

    # === 图片提取 (只取真正的游记照片，过滤表情/图标) ===
    source_html = content_html or html
    # 马蜂窝游记照片通常在 data-original 属性，URL 包含 p1-q.mafengwo.net 或 n1-q.mafengwo.net
    imgs = re.findall(r'data-original=["\']([^"\']+)["\']', source_html)
    if not imgs:
        imgs = re.findall(r'data-src=["\']([^"\']+)["\']', source_html)

    # 过滤: 只保留真正的照片 URL，排除表情/图标/头像
    real_imgs = []
    for img_url in imgs:
        # 排除表情图标、头像小图
        if '/face/' in img_url or '/brands' in img_url or '/avatar/' in img_url:
            continue
        if 'emoji' in img_url or 'icon' in img_url:
            continue
        # 只保留看起来像照片的 URL (包含CDN域名且有图片扩展名或路径特征)
        if re.search(r'mafengwo\.net.*(?:\.jpg|\.jpeg|\.png|\.webp|/s\d+/|/M00/)', img_url):
            real_imgs.append(img_url)
    post["image_urls"] = real_imgs[:30]

    # 下载图片到本地
    post_img_dir = os.path.join(OUTPUT_DIR, "images", f"post_{post['post_id']}")
    os.makedirs(post_img_dir, exist_ok=True)
    local_images = []
    for idx, img_url in enumerate(post["image_urls"]):
        try:
            if not img_url.startswith("http"):
                img_url = "https:" + img_url if img_url.startswith("//") else BASE_URL + img_url
            ext = ".jpg"
            for e in [".png", ".webp", ".jpeg", ".gif"]:
                if e in img_url.lower():
                    ext = e
                    break
            local_path = os.path.join(post_img_dir, f"{idx:03d}{ext}")
            if not os.path.exists(local_path):
                resp = req_lib.get(img_url, timeout=15, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": "https://www.mafengwo.cn/"
                })
                if resp.status_code == 200 and len(resp.content) > 1000:
                    with open(local_path, "wb") as f:
                        f.write(resp.content)
                    local_images.append(local_path)
        except Exception:
            pass
    post["local_images"] = local_images
    print(f"      Text: {len(post['content'])} chars, Images: {len(local_images)} downloaded")

    post["url"] = url
    post["crawl_time"] = datetime.now().isoformat()
    return post


# ============================================================
# 主程序
# ============================================================

def main():
    print("=" * 60)
    print("  Crawler: Mafengwo Anqing Travel Posts")
    print("  (undetected-chromedriver)")
    print("=" * 60)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    driver = create_driver()

    try:
        # 收集链接
        links = collect_post_links(driver)
        print(f"\nTotal unique post links: {len(links)}")

        links_file = os.path.join(OUTPUT_DIR, "post_links.json")
        with open(links_file, "w", encoding="utf-8") as f:
            json.dump(links, f, ensure_ascii=False, indent=2)

        if not links:
            print("No links found.")
            return

        # 断点续爬
        crawled_ids = set()
        all_posts_file = os.path.join(OUTPUT_DIR, "all_posts.json")
        existing = []
        if os.path.exists(all_posts_file):
            with open(all_posts_file, "r", encoding="utf-8") as f:
                existing = json.load(f)
            crawled_ids = {p["post_id"] for p in existing if p.get("post_id")}
            print(f"  Resuming: {len(crawled_ids)} already crawled")

        posts = list(existing)
        new_count = 0

        for i, link in enumerate(links):
            match = re.search(r'/i/(\d+)\.html', link["url"])
            pid = match.group(1) if match else ""
            if pid in crawled_ids:
                continue

            print(f"  [{i+1}/{len(links)}] {link.get('title', '')[:40] or link['url'][-20:]}...")
            try:
                post = scrape_post(driver, link["url"])
                if post and post.get("content"):
                    posts.append(post)
                    crawled_ids.add(pid)
                    new_count += 1

                    pf = os.path.join(OUTPUT_DIR, f"post_{pid}.json")
                    with open(pf, "w", encoding="utf-8") as f:
                        json.dump(post, f, ensure_ascii=False, indent=2)

                    if new_count % 5 == 0:
                        with open(all_posts_file, "w", encoding="utf-8") as f:
                            json.dump(posts, f, ensure_ascii=False, indent=2)
                        print(f"    Saved: {len(posts)} posts")
            except Exception as e:
                print(f"    Error: {e}")

            random_delay()

    finally:
        driver.quit()

    with open(all_posts_file, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)

    summary = {"total_posts": len(posts), "new_posts": new_count, "crawl_time": datetime.now().isoformat()}
    with open(os.path.join(OUTPUT_DIR, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\nDone! {len(posts)} posts ({new_count} new) -> {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
