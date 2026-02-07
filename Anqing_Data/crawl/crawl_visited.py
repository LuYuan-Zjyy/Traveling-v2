#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
爬虫脚本3: 爬取马蜂窝安庆景点信息
使用 undetected-chromedriver 绕过反爬

将景点信息保存到 Anqing_Data/visited/
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
SPOTS_URL = "https://www.mafengwo.cn/jd/12058/gonglve.html"

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "visited")

DELAY_MIN = 8.0
DELAY_MAX = 15.0
MAX_PAGES = 20
WAF_PAUSE = 300


def random_delay(lo=DELAY_MIN, hi=DELAY_MAX):
    time.sleep(random.uniform(lo, hi))


def create_driver():
    options = uc.ChromeOptions()
    options.add_argument("--lang=zh-CN")
    options.add_argument("--window-size=1920,1080")
    driver = uc.Chrome(options=options, version_main=144)

    print("  Checking login status...")
    driver.get("https://www.mafengwo.cn")
    time.sleep(3)
    html = driver.page_source
    if "退出" not in html and "passport.mafengwo" not in html:
        print("  *** 未检测到登录状态 ***")
        print("  请在浏览器中登录马蜂窝（推荐微信扫码登录）")
        input("  >>> 登录完成后按回车继续 <<<")
        time.sleep(2)

    return driver


def wait_for_page(driver, timeout=15):
    for _ in range(timeout):
        time.sleep(1)
        title = driver.title or ""
        html_len = len(driver.page_source or "")
        if "WAF" in title or "验证" in title or "拦截" in title or html_len < 3000:
            continue
        if html_len > 5000:
            return True
    title = driver.title or ""
    if "WAF" in title or "验证" in title or "拦截" in title:
        print("  *** 请在浏览器中手动完成验证码 ***")
        input("  >>> 完成后按回车继续 <<<")
        time.sleep(2)
    return True


# ============================================================
# 爬虫逻辑
# ============================================================

def collect_spot_links(driver):
    all_links = {}

    for pg in range(1, MAX_PAGES + 1):
        if pg == 1:
            url = SPOTS_URL
        else:
            url = f"https://www.mafengwo.cn/jd/12058/gonglve.html?page={pg}"

        print(f"  Page {pg}: {url}")
        driver.get(url)
        wait_for_page(driver)
        random_delay(3, 5)

        html = driver.page_source
        poi_links = re.findall(r'href=["\']([^"\']*?/poi/(\d+)\.html)["\']', html)
        new_count = 0
        for href, pid in poi_links:
            full_url = href if href.startswith("http") else BASE_URL + href
            if full_url not in all_links:
                all_links[full_url] = ""
                new_count += 1

        try:
            for a in driver.find_elements(By.CSS_SELECTOR, 'a[href*="/poi/"]'):
                href = a.get_attribute("href") or ""
                if re.search(r'/poi/\d+\.html', href):
                    full_url = href if href.startswith("http") else BASE_URL + href
                    if full_url not in all_links:
                        title = a.text.strip() if a.text else ""
                        if title and len(title) < 50:
                            all_links[full_url] = title
                            new_count += 1
        except:
            pass

        print(f"    +{new_count} new (total: {len(all_links)})")
        if new_count == 0 and pg > 2:
            print(f"    Stopping pagination")
            break

    return [{"url": u, "title": t} for u, t in all_links.items()]


def scrape_spot(driver, url):
    driver.get(url)
    wait_for_page(driver)
    random_delay(2, 3)

    spot = {}
    match = re.search(r'/poi/(\d+)\.html', url)
    spot["poi_id"] = match.group(1) if match else ""

    spot["name"] = driver.title or ""
    spot["name"] = re.sub(r'\s*[-–—]\s*马蜂窝.*$', '', spot["name"])
    spot["name"] = re.sub(r'\s*[-–—]\s*安庆.*$', '', spot["name"])

    try:
        h1 = driver.find_element(By.TAG_NAME, "h1")
        if h1 and h1.text:
            spot["name"] = h1.text.strip()
    except:
        pass

    html = driver.page_source

    # 评分
    score_match = re.search(r'class=["\'][^"\']*score[^"\']*["\'][^>]*>([^<]+)', html)
    spot["rating"] = score_match.group(1).strip() if score_match else ""

    # 精确提取景点介绍内容
    content_html = ""
    for sel in ["div.mod-detail", "div.summary", "div.poi-info", "div.intro", "article"]:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            if el:
                content_html = el.get_attribute("innerHTML")
                break
        except:
            continue

    paragraphs = []
    source = content_html or html
    p_texts = re.findall(r'<p[^>]*>(.*?)</p>', source, re.S)
    for pt in p_texts:
        clean = re.sub(r'<[^>]+>', '', pt).strip()
        if clean and len(clean) > 10:
            paragraphs.append(clean)

    # 过滤噪音
    noise_keywords = ['马蜂窝', '免责声明', '版权', '广告', '下载APP', '扫码', '客服', '相关推荐', '热门目的地']
    seen = set()
    unique = []
    for p in paragraphs:
        if p in seen or any(kw in p for kw in noise_keywords):
            continue
        seen.add(p)
        unique.append(p)
    spot["detail_text"] = "\n\n".join(unique[:50])

    # 评论 (精确定位)
    comments = []
    for sel in ["div.rev-txt", "div.comment-txt", "p.rev-txt", "div.review-content"]:
        try:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in els[:20]:
                text = el.text.strip()
                if text and len(text) > 10:
                    comments.append(text)
        except:
            continue
    spot["comments"] = comments

    # 图片
    imgs = re.findall(r'data-original=["\']([^"\']+)["\']', html)
    if not imgs:
        imgs = re.findall(r'data-src=["\']([^"\']+\.(?:jpg|jpeg|png|webp))["\']', html)
    spot["image_urls"] = imgs[:15]

    # 下载图片到本地
    spot_img_dir = os.path.join(OUTPUT_DIR, "images", f"poi_{spot['poi_id']}")
    os.makedirs(spot_img_dir, exist_ok=True)
    local_images = []
    for idx, img_url in enumerate(spot["image_urls"]):
        try:
            if not img_url.startswith("http"):
                img_url = "https:" + img_url if img_url.startswith("//") else BASE_URL + img_url
            ext = ".jpg"
            for e in [".png", ".webp", ".jpeg", ".gif"]:
                if e in img_url.lower():
                    ext = e
                    break
            local_path = os.path.join(spot_img_dir, f"{idx:03d}{ext}")
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
    spot["local_images"] = local_images
    print(f"      Text: {len(spot.get('detail_text',''))} chars, Images: {len(local_images)} downloaded")

    spot["url"] = url
    spot["crawl_time"] = datetime.now().isoformat()
    return spot


# ============================================================
# 主程序
# ============================================================

def main():
    print("=" * 60)
    print("  Crawler: Mafengwo Anqing Scenic Spots")
    print("  (undetected-chromedriver)")
    print("=" * 60)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    driver = create_driver()

    try:
        links = collect_spot_links(driver)
        print(f"\nTotal unique spot links: {len(links)}")

        links_file = os.path.join(OUTPUT_DIR, "spot_links.json")
        with open(links_file, "w", encoding="utf-8") as f:
            json.dump(links, f, ensure_ascii=False, indent=2)

        if not links:
            print("No links found.")
            return

        crawled_ids = set()
        all_spots_file = os.path.join(OUTPUT_DIR, "all_spots.json")
        existing = []
        if os.path.exists(all_spots_file):
            with open(all_spots_file, "r", encoding="utf-8") as f:
                existing = json.load(f)
            crawled_ids = {s["poi_id"] for s in existing if s.get("poi_id")}
            print(f"  Resuming: {len(crawled_ids)} already crawled")

        spots = list(existing)
        new_count = 0

        for i, link in enumerate(links):
            match = re.search(r'/poi/(\d+)\.html', link["url"])
            poi_id = match.group(1) if match else ""
            if poi_id in crawled_ids:
                continue

            print(f"  [{i+1}/{len(links)}] {link.get('title', '')[:30] or link['url'][-20:]}...")
            try:
                spot = scrape_spot(driver, link["url"])
                if spot:
                    spots.append(spot)
                    crawled_ids.add(poi_id)
                    new_count += 1

                    sf = os.path.join(OUTPUT_DIR, f"poi_{poi_id}.json")
                    with open(sf, "w", encoding="utf-8") as f:
                        json.dump(spot, f, ensure_ascii=False, indent=2)

                    if new_count % 5 == 0:
                        with open(all_spots_file, "w", encoding="utf-8") as f:
                            json.dump(spots, f, ensure_ascii=False, indent=2)
                        print(f"    Saved: {len(spots)} spots")
            except Exception as e:
                print(f"    Error: {e}")

            random_delay()

    finally:
        driver.quit()

    with open(all_spots_file, "w", encoding="utf-8") as f:
        json.dump(spots, f, ensure_ascii=False, indent=2)

    summary = {
        "total_spots": len(spots), "new_spots": new_count,
        "spots_list": [{"poi_id": s.get("poi_id", ""), "name": s.get("name", "")} for s in spots],
        "crawl_time": datetime.now().isoformat()
    }
    with open(os.path.join(OUTPUT_DIR, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\nDone! {len(spots)} spots ({new_count} new) -> {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
