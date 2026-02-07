#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
爬虫脚本1: 爬取安庆市政府网 - 黄梅戏专栏
https://www.anqing.gov.cn/zjaq/hmzx

子栏目: jbcs(基本常识), yy(音韵), fzls(发展历史) 等
每个栏目下有文章列表，点进去是长文本。
将所有文章以 JSON 格式保存到 Anqing_Data/huangmeixi/
"""

import os
import re
import json
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime

# ============================================================
# 配置
# ============================================================

BASE_URL = "https://www.anqing.gov.cn"
HMZX_URL = f"{BASE_URL}/zjaq/hmzx"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "huangmeixi")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.anqing.gov.cn/",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

DELAY = 1.5  # 请求间隔(秒)，避免被封


# ============================================================
# 工具函数
# ============================================================

def safe_request(url, retries=3):
    """带重试的请求"""
    for attempt in range(retries):
        try:
            resp = SESSION.get(url, timeout=15)
            resp.encoding = resp.apparent_encoding or 'utf-8'
            if resp.status_code == 200:
                return resp
            else:
                print(f"  HTTP {resp.status_code}: {url}")
        except Exception as e:
            print(f"  Request error (attempt {attempt+1}/{retries}): {e}")
            time.sleep(2)
    return None


def clean_text(text):
    """清理文本"""
    if not text:
        return ""
    # 去除多余空白
    text = re.sub(r'\s+', ' ', text).strip()
    # 去除特殊字符
    text = text.replace('\xa0', ' ').replace('\u3000', ' ')
    return text


# ============================================================
# 爬虫逻辑
# ============================================================

def discover_subcategories():
    """发现黄梅戏专栏下的所有子栏目"""
    print(f"Discovering subcategories from: {HMZX_URL}")
    resp = safe_request(HMZX_URL)
    if not resp:
        print("  Failed to load main page")
        return []

    soup = BeautifulSoup(resp.text, 'html.parser')
    subcategories = []

    # 查找栏目链接: /zjaq/hmzx/xxx 格式
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        # 匹配子栏目路径
        if re.match(r'/zjaq/hmzx/\w+/?$', href) or re.match(r'/zjaq/hmzx/\w+/index\.html$', href):
            full_url = urljoin(BASE_URL, href)
            name = a_tag.get_text(strip=True) or href.split('/')[-1]
            category_id = href.rstrip('/').split('/')[-1].replace('index.html', '').rstrip('/')
            if category_id and category_id != 'hmzx':
                subcategories.append({
                    'name': name,
                    'id': category_id,
                    'url': full_url
                })

    # 去重
    seen = set()
    unique = []
    for cat in subcategories:
        if cat['id'] not in seen:
            seen.add(cat['id'])
            unique.append(cat)
            print(f"  Found subcategory: {cat['name']} ({cat['id']}) -> {cat['url']}")

    # 如果没找到，手动添加已知栏目
    if not unique:
        known_cats = ['jbcs', 'yy', 'fzls', 'lsyg', 'zybs', 'cqxs']
        print("  No subcategories discovered via links, trying known categories...")
        for cat_id in known_cats:
            url = f"{HMZX_URL}/{cat_id}/"
            resp_test = safe_request(url)
            if resp_test and resp_test.status_code == 200:
                unique.append({'name': cat_id, 'id': cat_id, 'url': url})
                print(f"  Found: {cat_id} -> {url}")
            time.sleep(0.5)

    return unique


def get_article_links_from_list_page(list_url, category_id):
    """从栏目列表页获取所有文章链接（含翻页）"""
    all_links = []
    page = 1
    current_url = list_url

    while current_url:
        print(f"  [{category_id}] Page {page}: {current_url}")
        resp = safe_request(current_url)
        if not resp:
            break

        soup = BeautifulSoup(resp.text, 'html.parser')

        # 查找文章链接
        # 政府网站文章链接通常格式: /zjaq/hmzx/xxx/数字.html
        found_count = 0
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            # 匹配文章链接
            if re.search(r'/zjaq/hmzx/\w+/\d+\.html$', href):
                full_url = urljoin(BASE_URL, href)
                title = a_tag.get_text(strip=True)
                if full_url not in [l['url'] for l in all_links]:
                    all_links.append({'url': full_url, 'title': title})
                    found_count += 1
            # 也匹配可能的其他格式
            elif re.search(r'/zjaq/hmzx/.*\d+\.html$', href):
                full_url = urljoin(BASE_URL, href)
                title = a_tag.get_text(strip=True)
                if full_url not in [l['url'] for l in all_links]:
                    all_links.append({'url': full_url, 'title': title})
                    found_count += 1

        if found_count == 0 and page > 1:
            break

        # 查找下一页
        next_url = None
        for a_tag in soup.find_all('a', href=True):
            text = a_tag.get_text(strip=True)
            if text in ['下一页', '>', '>>', '下页']:
                next_href = a_tag['href']
                if next_href and next_href != '#' and next_href != 'javascript:;':
                    next_url = urljoin(current_url, next_href)
                    break

        # 也检查页码链接
        if not next_url:
            page_links = soup.find_all('a', href=re.compile(r'index_\d+\.html'))
            for pl in page_links:
                # 查找当前页+1的链接
                match = re.search(r'index_(\d+)\.html', pl['href'])
                if match and int(match.group(1)) == page:
                    next_url = urljoin(current_url, pl['href'])
                    break

        current_url = next_url
        page += 1
        time.sleep(DELAY)

    print(f"  [{category_id}] Total articles found: {len(all_links)}")
    return all_links


def scrape_article(url):
    """爬取单篇文章内容"""
    resp = safe_request(url)
    if not resp:
        return None

    soup = BeautifulSoup(resp.text, 'html.parser')

    article = {}

    # 标题
    title_tag = (
        soup.find('h1') or
        soup.find('div', class_=re.compile(r'title|article-title', re.I)) or
        soup.find('title')
    )
    article['title'] = clean_text(title_tag.get_text()) if title_tag else ""

    # 发布信息 (日期、来源等)
    info_div = soup.find('div', class_=re.compile(r'info|meta|source|pub', re.I))
    if info_div:
        article['publish_info'] = clean_text(info_div.get_text())

    # 正文内容
    # 政府网站通常用特定的 class 包裹正文
    content_div = (
        soup.find('div', class_=re.compile(r'article-content|content|TRS_Editor|text|main-content|article_content', re.I)) or
        soup.find('div', id=re.compile(r'content|article|zoom', re.I)) or
        soup.find('article')
    )

    if content_div:
        # 移除脚本和样式
        for tag in content_div.find_all(['script', 'style', 'iframe']):
            tag.decompose()

        # 只取 <p> 标签的文本，避免嵌套 div/span 导致重复
        paragraphs = []
        p_tags = content_div.find_all('p')
        if p_tags:
            for p in p_tags:
                text = clean_text(p.get_text())
                if text and len(text) > 5:
                    paragraphs.append(text)
        else:
            # 无 <p> 时降级取整段文本
            raw_text = content_div.get_text('\n')
            for line in raw_text.split('\n'):
                text = clean_text(line)
                if text and len(text) > 5:
                    paragraphs.append(text)

        # 去重保持顺序
        seen = set()
        unique_paragraphs = []
        for p in paragraphs:
            if p not in seen:
                seen.add(p)
                unique_paragraphs.append(p)

        # 过滤掉页面噪音文本
        noise_patterns = [
            r'^发布日期[：:]',
            r'^来源[：:]',
            r'^字号[：:]',
            r'^\[大\].*\[小\]',
            r'^视力保护色',
            r'^我要纠错',
            r'^打印本页',
            r'^扫一扫在手机打开当前页',
            r'^阅读[：:]',
        ]
        cleaned_paragraphs = []
        for p in unique_paragraphs:
            if not any(re.match(pat, p.strip()) for pat in noise_patterns):
                cleaned_paragraphs.append(p)

        article['content'] = '\n\n'.join(cleaned_paragraphs)
    else:
        # 降级: 取 body 中的主要文本
        body = soup.find('body')
        if body:
            article['content'] = clean_text(body.get_text())[:5000]
        else:
            article['content'] = ""

    article['url'] = url
    article['crawl_time'] = datetime.now().isoformat()

    # 从 URL 提取文章 ID
    match = re.search(r'/(\d+)\.html$', url)
    article['article_id'] = match.group(1) if match else ""

    return article


def crawl_category(category):
    """爬取一个栏目下的所有文章"""
    cat_id = category['id']
    cat_name = category['name']
    print(f"\n--- Crawling category: {cat_name} ({cat_id}) ---")

    # 获取文章列表
    links = get_article_links_from_list_page(category['url'], cat_id)

    articles = []
    for i, link in enumerate(links):
        print(f"  [{cat_id}] Scraping {i+1}/{len(links)}: {link['title'][:30]}...")
        article = scrape_article(link['url'])
        if article:
            article['category'] = cat_id
            article['category_name'] = cat_name
            if not article['title']:
                article['title'] = link['title']
            articles.append(article)
        time.sleep(DELAY)

    return articles


# ============================================================
# 主程序
# ============================================================

def main():
    print("=" * 60)
    print("  Crawler: Anqing Government - Huangmei Opera (黄梅戏)")
    print("=" * 60)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 发现子栏目
    subcategories = discover_subcategories()
    if not subcategories:
        print("\nNo subcategories found. Exiting.")
        return

    all_articles = []

    # 爬取每个栏目
    for category in subcategories:
        articles = crawl_category(category)
        all_articles.extend(articles)

        # 每个栏目单独保存
        if articles:
            cat_file = os.path.join(OUTPUT_DIR, f"{category['id']}.json")
            with open(cat_file, 'w', encoding='utf-8') as f:
                json.dump(articles, f, ensure_ascii=False, indent=2)
            print(f"  Saved {len(articles)} articles to {cat_file}")

    # 汇总保存
    if all_articles:
        all_file = os.path.join(OUTPUT_DIR, "all_articles.json")
        with open(all_file, 'w', encoding='utf-8') as f:
            json.dump(all_articles, f, ensure_ascii=False, indent=2)
        print(f"\nTotal: {len(all_articles)} articles saved to {all_file}")

        # 统计
        summary_file = os.path.join(OUTPUT_DIR, "summary.json")
        summary = {
            "total_articles": len(all_articles),
            "categories": {cat['id']: len([a for a in all_articles if a.get('category') == cat['id']])
                          for cat in subcategories},
            "crawl_time": datetime.now().isoformat()
        }
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\nDone! Output directory: {OUTPUT_DIR}")


if __name__ == '__main__':
    main()
