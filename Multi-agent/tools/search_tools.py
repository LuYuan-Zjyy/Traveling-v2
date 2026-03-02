"""
网络搜索工具 - 获取主题相关的实时旅游资讯
支持 DuckDuckGo (无需 API Key，开箱即用)
可扩展为 Bing Search API / SerpAPI / Tavily

典型用途：
  - 搜索小红书/马蜂窝对特定主题景点的网友推荐
  - 获取实时活动/展览信息（高德 API 无法覆盖）
  - 验证冷门主题与景点的匹配关系
"""

import json
import time
import urllib.request
import urllib.parse
from typing import List, Dict, Any, Optional


class DuckDuckGoSearch:
    """
    DuckDuckGo 即时答案 + 网页搜索（无需 API Key）
    使用 DuckDuckGo HTML 接口 + Instant Answer API
    """

    INSTANT_URL = "https://api.duckduckgo.com/"
    TIMEOUT = 8  # 秒

    def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """
        搜索并返回结果列表
        每个结果：{"title": str, "snippet": str, "url": str}
        """
        results = []

        # 方法 1: DuckDuckGo Instant Answer API（结构化，稳定）
        try:
            params = urllib.parse.urlencode({
                "q": query,
                "format": "json",
                "no_html": "1",
                "skip_disambig": "1",
            })
            url = f"{self.INSTANT_URL}?{params}"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "TravelPlanner/1.0 (research tool)"},
            )
            with urllib.request.urlopen(req, timeout=self.TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            # AbstractText
            if data.get("AbstractText"):
                results.append({
                    "title": data.get("Heading", query),
                    "snippet": data["AbstractText"][:300],
                    "url": data.get("AbstractURL", ""),
                    "source": "ddg_instant",
                })

            # RelatedTopics
            for topic in data.get("RelatedTopics", [])[:max_results]:
                if isinstance(topic, dict) and topic.get("Text"):
                    results.append({
                        "title": topic.get("Text", "")[:60],
                        "snippet": topic.get("Text", "")[:300],
                        "url": topic.get("FirstURL", ""),
                        "source": "ddg_related",
                    })

        except Exception as e:
            print(f"[Search] DuckDuckGo Instant API 失败: {e}")

        # 方法 2: DuckDuckGo Lite HTML（兜底，获取网页摘要）
        if len(results) < 2:
            try:
                params = urllib.parse.urlencode({"q": query, "kl": "cn-zh"})
                url = f"https://html.duckduckgo.com/html/?{params}"
                req = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                                      "Chrome/120.0.0.0 Safari/537.36",
                        "Accept-Language": "zh-CN,zh;q=0.9",
                    },
                )
                with urllib.request.urlopen(req, timeout=self.TIMEOUT) as resp:
                    html = resp.read().decode("utf-8", errors="replace")

                # 简单提取搜索摘要（避免引入 BeautifulSoup 依赖）
                import re
                snippets = re.findall(
                    r'class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL
                )
                titles = re.findall(
                    r'class="result__a"[^>]*>(.*?)</a>', html, re.DOTALL
                )
                urls = re.findall(
                    r'class="result__url"[^>]*>(.*?)</a>', html, re.DOTALL
                )
                for i, snippet in enumerate(snippets[:max_results]):
                    clean = re.sub(r"<[^>]+>", "", snippet).strip()
                    if clean:
                        results.append({
                            "title": re.sub(r"<[^>]+>", "", titles[i]).strip() if i < len(titles) else "",
                            "snippet": clean[:300],
                            "url": urls[i].strip() if i < len(urls) else "",
                            "source": "ddg_html",
                        })

            except Exception as e:
                print(f"[Search] DuckDuckGo HTML 失败: {e}")

        return results[:max_results]

    def search_travel_theme(
        self,
        destination: str,
        theme: str,
        max_results: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        专为旅行主题优化的搜索：自动构建多个查询，汇总结果。
        示例：destination="重庆", theme="仙剑奇侠传3"
          → 搜索 "重庆 仙侠风 推荐景点"
              "重庆 古风 神秘 适合拍照"
              "重庆 类似仙剑 景点 网友推荐"
        """
        # 衍生查询列表
        queries = [
            f"{destination} {theme} 推荐景点",
            f"{destination} {theme} 打卡地 小红书",
            f"{destination} 仙侠 古风 神秘 适合 景点",
        ]

        seen_snippets: set = set()
        all_results: List[Dict[str, Any]] = []

        for q in queries:
            if len(all_results) >= max_results:
                break
            for r in self.search(q, max_results=3):
                key = r["snippet"][:80]
                if key not in seen_snippets:
                    seen_snippets.add(key)
                    r["query"] = q
                    all_results.append(r)
            time.sleep(0.3)  # 礼貌性延迟，避免触发限流

        return all_results[:max_results]

    def extract_poi_names_from_results(
        self,
        results: List[Dict[str, Any]],
        destination: str,
    ) -> List[str]:
        """
        从搜索结果的文本中提取疑似景点名称。
        使用简单正则（不依赖 LLM），供快速过滤使用。
        """
        import re

        text = " ".join(r.get("snippet", "") + " " + r.get("title", "") for r in results)

        # 提取「XX景区 / XX古镇 / XX寺 / XX山 / XX洞」等中文地名
        patterns = [
            r"[\u4e00-\u9fff]{2,8}(?:景区|公园|古镇|老街|遗址|博物馆|纪念馆|寺|道观|山|峡|洞|湖|瀑布|步道)",
            r"[\u4e00-\u9fff]{2,6}(?:文化街区|历史街区|风貌区|文创园|观景台)",
        ]

        names = []
        for pat in patterns:
            names.extend(re.findall(pat, text))

        # 去重、去掉与目的地无关的常见词
        blacklist = {"公共汽车", "地铁", "火车站"}
        seen = set()
        unique = []
        for n in names:
            if n not in seen and n not in blacklist:
                seen.add(n)
                unique.append(n)

        return unique[:10]


# ── Bing Search API（可选，需 BING_SEARCH_API_KEY 环境变量）──────────────

class BingSearch:
    """
    Bing Web Search API v7
    需要在 .env 中配置 BING_SEARCH_API_KEY
    每月 1000 次免费（F1 tier）
    升级替换 DuckDuckGoSearch 即可，接口兼容。
    """

    BASE_URL = "https://api.bing.microsoft.com/v7.0/search"

    def __init__(self, api_key: Optional[str] = None):
        import os
        self.api_key = api_key or os.getenv("BING_SEARCH_API_KEY", "")

    def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        if not self.api_key:
            print("[BingSearch] 未配置 BING_SEARCH_API_KEY，跳过")
            return []
        try:
            params = urllib.parse.urlencode({
                "q": query,
                "count": max_results,
                "mkt": "zh-CN",
                "responseFilter": "Webpages",
            })
            url = f"{self.BASE_URL}?{params}"
            req = urllib.request.Request(
                url,
                headers={"Ocp-Apim-Subscription-Key": self.api_key},
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            results = []
            for item in data.get("webPages", {}).get("value", [])[:max_results]:
                results.append({
                    "title": item.get("name", ""),
                    "snippet": item.get("snippet", "")[:300],
                    "url": item.get("url", ""),
                    "source": "bing",
                })
            return results
        except Exception as e:
            print(f"[BingSearch] 请求失败: {e}")
            return []

    def search_travel_theme(
        self, destination: str, theme: str, max_results: int = 5
    ) -> List[Dict[str, Any]]:
        return self.search(f"{destination} {theme} 推荐景点 攻略", max_results)

    def extract_poi_names_from_results(
        self, results: List[Dict[str, Any]], destination: str
    ) -> List[str]:
        return DuckDuckGoSearch().extract_poi_names_from_results(results, destination)


def get_search_tool():
    """
    工厂函数：优先使用 Bing（有 Key 时），否则降级到 DuckDuckGo。
    在 orchestrator 里调用此函数即可，无需关心底层实现。
    """
    import os
    bing_key = os.getenv("BING_SEARCH_API_KEY", "")
    if bing_key:
        print("[SearchTool] 使用 Bing Search API")
        return BingSearch(api_key=bing_key)
    print("[SearchTool] 使用 DuckDuckGo（无需 API Key）")
    return DuckDuckGoSearch()
