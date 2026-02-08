#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
事实准确度验证模块 - 通过联网搜索验证 AI 生成内容的真实性

功能：
1. 从旅行计划中提取可验证的事实声明
2. 使用搜索 API 进行联网验证
3. 计算事实准确度得分

支持的搜索 API：
- SerpAPI (Google Search)
- Bing Search API
- 通用兼容接口

使用方法：
    from fact_checker import FactChecker
    
    checker = FactChecker(api_key="your_key", search_engine="serpapi")
    result = checker.verify_plan(plan_json, destination_city)
"""

import os
import re
import json
import time
import requests
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))


class SearchEngine(Enum):
    """支持的搜索引擎"""
    SERPAPI = "serpapi"      # SerpAPI (Google Search)
    BING = "bing"            # Bing Search API
    GOOGLE = "google"        # Google Custom Search API
    DUCKDUCKGO = "duckduckgo"  # DuckDuckGo (免费)


@dataclass
class FactClaim:
    """可验证的事实声明"""
    category: str        # 类别: attraction, restaurant, hotel, transportation
    subject: str         # 主体: 景点名/餐厅名等
    claim_type: str      # 声明类型: exists, location, feature, price
    claim_text: str      # 声明文本
    source_field: str    # 来源字段
    expected_city: str = ""  # 期望的城市 (用于城市匹配验证)
    

@dataclass
class VerificationResult:
    """验证结果"""
    claim: FactClaim
    is_verified: bool    # 是否验证通过
    confidence: float    # 置信度 0-1
    source_url: str      # 来源URL
    source_snippet: str  # 来源摘要
    explanation: str     # 说明


class SearchClient:
    """搜索 API 客户端"""
    
    def __init__(self, api_key: str = None, engine: SearchEngine = SearchEngine.SERPAPI, base_url: str = None):
        """
        初始化搜索客户端
        
        Args:
            api_key: API 密钥
            engine: 搜索引擎类型
            base_url: API 基础 URL (可选)
        """
        self.api_key = api_key or os.getenv('SEARCH_API') or os.getenv('SERPAPI_KEY')
        self.engine = engine
        self.base_url = base_url
        self.request_count = 0
        self.max_requests_per_minute = 30
        self.last_request_time = 0
        
    def search(self, query: str, num_results: int = 3) -> List[Dict]:
        """
        执行搜索
        
        Args:
            query: 搜索查询
            num_results: 返回结果数量
            
        Returns:
            搜索结果列表
        """
        # 速率限制
        self._rate_limit()
        
        try:
            if self.engine == SearchEngine.SERPAPI:
                return self._search_serpapi(query, num_results)
            elif self.engine == SearchEngine.BING:
                return self._search_bing(query, num_results)
            elif self.engine == SearchEngine.GOOGLE:
                return self._search_google(query, num_results)
            elif self.engine == SearchEngine.DUCKDUCKGO:
                return self._search_duckduckgo(query, num_results)
            else:
                return self._search_generic(query, num_results)
        except Exception as e:
            print(f"搜索出错: {e}")
            return []
    
    def _rate_limit(self):
        """速率限制"""
        current_time = time.time()
        if current_time - self.last_request_time < 60 / self.max_requests_per_minute:
            time.sleep(60 / self.max_requests_per_minute)
        self.last_request_time = time.time()
        self.request_count += 1
    
    def _search_serpapi(self, query: str, num_results: int) -> List[Dict]:
        """使用 SerpAPI 搜索"""
        url = "https://serpapi.com/search"
        params = {
            "q": query,
            "api_key": self.api_key,
            "num": num_results,
            "hl": "zh-CN"  # 中文结果
        }
        
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            results = []
            for item in data.get('organic_results', [])[:num_results]:
                results.append({
                    'title': item.get('title', ''),
                    'snippet': item.get('snippet', ''),
                    'url': item.get('link', '')
                })
            return results
        return []
    
    def _search_bing(self, query: str, num_results: int) -> List[Dict]:
        """使用 Bing Search API 搜索"""
        url = self.base_url or "https://api.bing.microsoft.com/v7.0/search"
        headers = {"Ocp-Apim-Subscription-Key": self.api_key}
        params = {"q": query, "count": num_results, "mkt": "zh-CN"}
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            results = []
            for item in data.get('webPages', {}).get('value', [])[:num_results]:
                results.append({
                    'title': item.get('name', ''),
                    'snippet': item.get('snippet', ''),
                    'url': item.get('url', '')
                })
            return results
        return []
    
    def _search_google(self, query: str, num_results: int) -> List[Dict]:
        """使用 Google Custom Search API 搜索"""
        url = "https://www.googleapis.com/customsearch/v1"
        cx = os.getenv('GOOGLE_CX', '')
        params = {
            "key": self.api_key,
            "cx": cx,
            "q": query,
            "num": num_results
        }
        
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            results = []
            for item in data.get('items', [])[:num_results]:
                results.append({
                    'title': item.get('title', ''),
                    'snippet': item.get('snippet', ''),
                    'url': item.get('link', '')
                })
            return results
        return []
    
    def _search_duckduckgo(self, query: str, num_results: int) -> List[Dict]:
        """使用 DuckDuckGo 搜索 (免费)"""
        import warnings
        warnings.filterwarnings('ignore', category=RuntimeWarning)
        
        try:
            # 尝试新包名
            try:
                from ddgs import DDGS
            except ImportError:
                from duckduckgo_search import DDGS
            
            with DDGS() as ddgs:
                results = []
                # 添加重试机制
                for attempt in range(3):
                    try:
                        for r in ddgs.text(query, max_results=num_results, region='cn-zh'):
                            results.append({
                                'title': r.get('title', ''),
                                'snippet': r.get('body', ''),
                                'url': r.get('href', '')
                            })
                        if results:
                            break
                    except Exception:
                        time.sleep(1)
                        continue
                return results
        except ImportError:
            print("需要安装 duckduckgo-search: pip install ddgs")
            return []
        except Exception as e:
            # 静默处理错误，返回空结果
            return []
    
    def _search_generic(self, query: str, num_results: int) -> List[Dict]:
        """通用搜索接口 (兼容自定义 API)"""
        if not self.base_url:
            return []
        
        try:
            response = requests.post(
                self.base_url,
                json={"query": query, "num_results": num_results},
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10
            )
            if response.status_code == 200:
                return response.json().get('results', [])
        except Exception as e:
            print(f"通用搜索出错: {e}")
        return []


class FactChecker:
    """事实准确度验证器"""
    
    def __init__(self, api_key: str = None, search_engine: str = "serpapi", base_url: str = None, 
                 llm_client = None, local_data_path: str = None, use_local_fallback: bool = True):
        """
        初始化事实验证器
        
        Args:
            api_key: 搜索 API 密钥
            search_engine: 搜索引擎类型
            base_url: API 基础 URL
            llm_client: LLM 客户端 (用于智能验证)
            local_data_path: 本地数据路径 (用于后备验证)
            use_local_fallback: 当联网搜索失败时是否使用本地数据验证
        """
        engine = SearchEngine(search_engine) if search_engine in [e.value for e in SearchEngine] else SearchEngine.SERPAPI
        self.search_client = SearchClient(api_key, engine, base_url)
        self.llm_client = llm_client
        self.verification_cache = {}  # 缓存验证结果
        self.use_local_fallback = use_local_fallback
        
        # 加载本地数据作为后备验证
        self.local_attractions = set()
        self.local_restaurants = set()
        self.local_hotels = set()
        
        if local_data_path or use_local_fallback:
            self._load_local_data(local_data_path)
    
    def _load_local_data(self, data_path: str = None):
        """加载本地数据用于后备验证 - 包含城市信息"""
        import pandas as pd
        
        if data_path is None:
            data_path = os.path.join(os.path.dirname(__file__), '..', '..', 'data')
        
        try:
            # 加载景点数据 (包含城市信息)
            attractions_file = os.path.join(data_path, 'attractions.csv')
            if os.path.exists(attractions_file):
                df = pd.read_csv(attractions_file, encoding='utf-8')
                name_cols = ['poiName', 'Attraction', 'name', 'Name']
                name_col = next((c for c in name_cols if c in df.columns), df.columns[0])
                city_col = 'city' if 'city' in df.columns else None
                
                self.local_attractions = set(df[name_col].astype(str).str.lower().dropna())
                # 存储 name -> city 映射
                self.attractions_city_map = {}
                if city_col:
                    for _, row in df.iterrows():
                        name = str(row[name_col]).lower()
                        city = str(row[city_col]).lower() if pd.notna(row[city_col]) else ''
                        self.attractions_city_map[name] = city
            
            # 加载餐厅数据 (包含城市信息)
            restaurants_file = os.path.join(data_path, 'restaurants.csv')
            if os.path.exists(restaurants_file):
                df = pd.read_csv(restaurants_file, encoding='utf-8')
                name_col = df.columns[0]  # 第一列是名称
                city_col = df.columns[1] if len(df.columns) > 1 else None  # 第二列通常是城市
                
                self.local_restaurants = set(df[name_col].astype(str).str.lower().dropna())
                self.restaurants_city_map = {}
                if city_col:
                    for _, row in df.iterrows():
                        name = str(row[name_col]).lower()
                        city = str(row[city_col]).lower() if pd.notna(row[city_col]) else ''
                        self.restaurants_city_map[name] = city
            
            # 加载酒店数据 (包含城市信息)
            hotels_file = os.path.join(data_path, 'accommodations.csv')
            if os.path.exists(hotels_file):
                df = pd.read_csv(hotels_file, encoding='utf-8')
                name_col = df.columns[0]
                city_col = df.columns[1] if len(df.columns) > 1 else None
                
                self.local_hotels = set(df[name_col].astype(str).str.lower().dropna())
                self.hotels_city_map = {}
                if city_col:
                    for _, row in df.iterrows():
                        name = str(row[name_col]).lower()
                        city = str(row[city_col]).lower() if pd.notna(row[city_col]) else ''
                        self.hotels_city_map[name] = city
            
            total = len(self.local_attractions) + len(self.local_restaurants) + len(self.local_hotels)
            if total > 0:
                print(f"   📂 已加载本地数据: {len(self.local_attractions)} 景点, {len(self.local_restaurants)} 餐厅, {len(self.local_hotels)} 酒店")
        except Exception as e:
            print(f"   ⚠️ 加载本地数据失败: {e}")
        
    def extract_claims(self, plan: Dict, destination_city: str) -> List[FactClaim]:
        """
        从旅行计划中提取可验证的事实声明
        
        Args:
            plan: 旅行计划 JSON
            destination_city: 目的地城市
            
        Returns:
            事实声明列表
        """
        claims = []
        
        # 1. 提取景点相关声明
        if 'itinerary' in plan:
            for day_key, activities in plan['itinerary'].items():
                for activity in activities:
                    if activity.get('action') == 'sightseeing':
                        location = activity.get('location', '')
                        if location:
                            # 景点存在性 (包含城市信息)
                            claims.append(FactClaim(
                                category='attraction',
                                subject=location,
                                claim_type='exists',
                                claim_text=f"{location} 是 {destination_city} 的一个景点",
                                source_field=f"itinerary.{day_key}",
                                expected_city=destination_city
                            ))
                            
                            # 景点描述（如果有）
                            description = activity.get('description', '')
                            if description and len(description) > 20:
                                claims.append(FactClaim(
                                    category='attraction',
                                    subject=location,
                                    claim_type='feature',
                                    claim_text=f"{location}: {description[:100]}",
                                    source_field=f"itinerary.{day_key}.description",
                                    expected_city=destination_city
                                ))
                    
                    # 餐厅信息
                    elif activity.get('action') == 'dining':
                        location = activity.get('location', '')
                        if location:
                            claims.append(FactClaim(
                                category='restaurant',
                                subject=location,
                                claim_type='exists',
                                claim_text=f"{location} 是 {destination_city} 的一家餐厅",
                                source_field=f"itinerary.{day_key}",
                                expected_city=destination_city
                            ))
        
        # 2. 提取酒店相关声明
        if 'hotel' in plan and plan['hotel']:
            for hotel in plan['hotel']:
                hotel_name = hotel.get('name', '')
                if hotel_name:
                    claims.append(FactClaim(
                        category='hotel',
                        subject=hotel_name,
                        claim_type='exists',
                        claim_text=f"{hotel_name} 是 {destination_city} 的一家酒店",
                        source_field='hotel',
                        expected_city=destination_city
                    ))
        
        return claims
    
    def verify_claim(self, claim: FactClaim) -> VerificationResult:
        """
        验证单个事实声明
        
        Args:
            claim: 事实声明
            
        Returns:
            验证结果
        """
        # 检查缓存
        cache_key = f"{claim.subject}_{claim.claim_type}"
        if cache_key in self.verification_cache:
            return self.verification_cache[cache_key]
        
        # 首先尝试本地数据验证 (快速且可靠)
        if self.use_local_fallback and claim.claim_type == 'exists':
            local_result = self._verify_with_local_data(claim)
            if local_result.is_verified:
                self.verification_cache[cache_key] = local_result
                return local_result
        
        # 构造搜索查询
        if claim.claim_type == 'exists':
            if claim.category == 'attraction':
                query = f"{claim.subject} 景点 旅游"
            elif claim.category == 'restaurant':
                query = f"{claim.subject} 餐厅 美食"
            elif claim.category == 'hotel':
                query = f"{claim.subject} 酒店 住宿"
            else:
                query = claim.subject
        else:
            query = claim.claim_text
        
        # 执行搜索
        search_results = self.search_client.search(query, num_results=3)
        
        if not search_results:
            # 联网搜索失败时，使用本地数据作为后备
            if self.use_local_fallback:
                local_result = self._verify_with_local_data(claim)
                self.verification_cache[cache_key] = local_result
                return local_result
            
            result = VerificationResult(
                claim=claim,
                is_verified=False,
                confidence=0.0,
                source_url='',
                source_snippet='无法获取搜索结果',
                explanation='搜索失败或无结果'
            )
            self.verification_cache[cache_key] = result
            return result
        
        # 验证结果
        is_verified, confidence, best_result = self._analyze_search_results(claim, search_results)
        
        result = VerificationResult(
            claim=claim,
            is_verified=is_verified,
            confidence=confidence,
            source_url=best_result.get('url', '') if best_result else '',
            source_snippet=best_result.get('snippet', '') if best_result else '',
            explanation=self._generate_explanation(claim, is_verified, confidence, search_results)
        )
        
        self.verification_cache[cache_key] = result
        return result
    
    def _verify_with_local_data(self, claim: FactClaim) -> VerificationResult:
        """使用本地数据验证 - 严格模式 (包含城市匹配)"""
        from fuzzywuzzy import fuzz
        
        subject_lower = claim.subject.lower()
        # 清理名称：移除括号内的备注
        subject_clean = subject_lower.split('(')[0].strip()
        expected_city = claim.expected_city.lower() if claim.expected_city else ""
        
        is_verified = False
        confidence = 0.0
        source = "本地数据库"
        match_type = "未匹配"
        matched_name = ""
        city_match_info = ""
        
        # 根据类别选择数据集和城市映射
        if claim.category == 'attraction':
            dataset = self.local_attractions
            city_map = getattr(self, 'attractions_city_map', {})
        elif claim.category == 'restaurant':
            dataset = self.local_restaurants
            city_map = getattr(self, 'restaurants_city_map', {})
        elif claim.category == 'hotel':
            dataset = self.local_hotels
            city_map = getattr(self, 'hotels_city_map', {})
        else:
            dataset = set()
            city_map = {}
        
        # 1. 精确匹配 (最严格)
        matched_key = None
        if subject_lower in dataset:
            matched_key = subject_lower
        elif subject_clean in dataset:
            matched_key = subject_clean
        
        if matched_key:
            # 检查城市匹配
            actual_city = city_map.get(matched_key, "")
            
            if expected_city and actual_city:
                # 城市匹配检查
                city_score = fuzz.ratio(expected_city, actual_city)
                if city_score >= 80:  # 城市名称匹配
                    is_verified = True
                    confidence = 1.0
                    match_type = "精确匹配"
                    city_match_info = f" [城市: {actual_city} ✓]"
                else:
                    # 名称存在但城市不匹配 - 这是严重错误！
                    is_verified = False
                    confidence = 0.0
                    match_type = "城市不匹配"
                    city_match_info = f" [期望: {expected_city}, 实际: {actual_city} ✗]"
            else:
                # 没有城市信息，视为精确匹配
                is_verified = True
                confidence = 1.0
                match_type = "精确匹配"
                city_match_info = " [城市: 未知]"
            
            matched_name = matched_key
        else:
            # 2. 严格模糊匹配
            best_match = None
            best_score = 0
            best_city = ""
            
            for item in dataset:
                # 使用多种匹配策略，取加权平均
                ratio_score = fuzz.ratio(subject_clean, item)
                partial_score = fuzz.partial_ratio(subject_clean, item)
                token_score = fuzz.token_sort_ratio(subject_clean, item)
                
                # 加权计算: ratio 权重最高
                if ratio_score >= 70:
                    weighted_score = ratio_score * 0.5 + partial_score * 0.3 + token_score * 0.2
                else:
                    weighted_score = ratio_score * 0.7 + token_score * 0.3
                
                # 长度惩罚
                len_ratio = min(len(subject_clean), len(item)) / max(len(subject_clean), len(item)) if max(len(subject_clean), len(item)) > 0 else 0
                if len_ratio < 0.5:
                    weighted_score *= len_ratio * 1.5
                
                if weighted_score > best_score:
                    best_score = weighted_score
                    best_match = item
                    best_city = city_map.get(item, "")
            
            # 严格阈值
            if best_score >= 92:
                # 检查城市匹配
                if expected_city and best_city:
                    city_score = fuzz.ratio(expected_city, best_city)
                    if city_score >= 80:
                        is_verified = True
                        confidence = best_score / 100.0
                        match_type = "高置信度模糊匹配"
                        city_match_info = f" [城市: {best_city} ✓]"
                    else:
                        is_verified = False
                        confidence = 0.0
                        match_type = "城市不匹配"
                        city_match_info = f" [期望: {expected_city}, 实际: {best_city} ✗]"
                else:
                    is_verified = True
                    confidence = best_score / 100.0
                    match_type = "高置信度模糊匹配"
                    city_match_info = " [城市: 未知]"
                matched_name = best_match
            elif best_score >= 85:
                # 85-92% 之间：检查城市后再决定
                if expected_city and best_city:
                    city_score = fuzz.ratio(expected_city, best_city)
                    if city_score >= 80:
                        is_verified = True
                        confidence = (best_score / 100.0) * 0.5
                        match_type = "低置信度模糊匹配"
                        city_match_info = f" [城市: {best_city} ✓]"
                    else:
                        is_verified = False
                        confidence = 0.0
                        match_type = "城市不匹配"
                        city_match_info = f" [期望: {expected_city}, 实际: {best_city} ✗]"
                else:
                    is_verified = True
                    confidence = (best_score / 100.0) * 0.5
                    match_type = "低置信度模糊匹配"
                    city_match_info = " [城市: 未知]"
                matched_name = best_match
            else:
                is_verified = False
                confidence = 0.0
                match_type = "未匹配"
                matched_name = f"最佳候选: {best_match} ({best_score:.0f}%)" if best_match else ""
        
        explanation = (
            f"{match_type}: '{claim.subject}' → '{matched_name}'{city_match_info} (置信度: {confidence:.2f})"
            if is_verified or "城市不匹配" in match_type else
            f"未通过验证: '{claim.subject}' {matched_name}"
        )
        
        return VerificationResult(
            claim=claim,
            is_verified=is_verified,
            confidence=confidence,
            source_url=source,
            source_snippet=f"本地数据库验证 - {claim.category} - {match_type}",
            explanation=explanation
        )
    
    def _analyze_search_results(self, claim: FactClaim, results: List[Dict]) -> Tuple[bool, float, Dict]:
        """
        分析搜索结果判断事实真伪
        
        Args:
            claim: 事实声明
            results: 搜索结果
            
        Returns:
            (是否验证通过, 置信度, 最佳匹配结果)
        """
        subject_lower = claim.subject.lower()
        best_match = None
        max_score = 0.0
        
        for result in results:
            title = result.get('title', '').lower()
            snippet = result.get('snippet', '').lower()
            combined = title + ' ' + snippet
            
            # 计算匹配分数
            score = 0.0
            
            # 检查主体是否出现在结果中
            if subject_lower in combined:
                score += 0.5
            elif any(word in combined for word in subject_lower.split()):
                score += 0.3
            
            # 检查类别相关词
            category_keywords = {
                'attraction': ['景点', '旅游', '游览', 'attraction', 'tourist', '参观', '景区'],
                'restaurant': ['餐厅', '美食', '菜', 'restaurant', 'dining', '用餐', '饭店'],
                'hotel': ['酒店', '住宿', 'hotel', 'accommodation', '宾馆', '旅馆']
            }
            
            keywords = category_keywords.get(claim.category, [])
            if any(kw in combined for kw in keywords):
                score += 0.3
            
            # 检查是否有否定词
            negative_words = ['不存在', '已关闭', '已停业', 'closed', 'does not exist', '虚假', '假的']
            if any(neg in combined for neg in negative_words):
                score -= 0.5
            
            # 官方来源加分
            official_domains = ['baidu.com', 'meituan.com', 'ctrip.com', 'dianping.com', 'tripadvisor']
            if any(domain in result.get('url', '') for domain in official_domains):
                score += 0.2
            
            if score > max_score:
                max_score = score
                best_match = result
        
        # 归一化置信度
        confidence = min(max(max_score, 0.0), 1.0)
        is_verified = confidence >= 0.5
        
        return is_verified, confidence, best_match
    
    def _generate_explanation(self, claim: FactClaim, is_verified: bool, confidence: float, results: List[Dict]) -> str:
        """生成验证说明"""
        if is_verified:
            return f"已验证: 在搜索结果中找到关于 '{claim.subject}' 的相关信息 (置信度: {confidence:.2f})"
        else:
            return f"未验证: 未能在搜索结果中确认 '{claim.subject}' 的存在 (置信度: {confidence:.2f})"
    
    def verify_plan(self, plan: Dict, destination_city: str, max_checks: int = 10) -> Dict:
        """
        验证整个旅行计划的事实准确度
        
        Args:
            plan: 旅行计划 JSON
            destination_city: 目的地城市
            max_checks: 最大验证数量
            
        Returns:
            验证结果汇总
        """
        # 提取声明
        claims = self.extract_claims(plan, destination_city)
        
        if not claims:
            return {
                'total_claims': 0,
                'verified_claims': 0,
                'accuracy': 1.0,  # 没有声明视为满分
                'details': [],
                'category_scores': {}
            }
        
        # 限制验证数量
        claims_to_verify = claims[:max_checks]
        
        # 验证每个声明
        results = []
        category_results = {}
        
        for claim in claims_to_verify:
            result = self.verify_claim(claim)
            results.append(result)
            
            # 按类别统计
            if claim.category not in category_results:
                category_results[claim.category] = {'verified': 0, 'total': 0}
            category_results[claim.category]['total'] += 1
            if result.is_verified:
                category_results[claim.category]['verified'] += 1
        
        # 计算总体准确度
        verified_count = sum(1 for r in results if r.is_verified)
        total_count = len(results)
        accuracy = verified_count / total_count if total_count > 0 else 1.0
        
        # 计算加权准确度 (景点权重更高)
        category_weights = {
            'attraction': 0.5,
            'restaurant': 0.25,
            'hotel': 0.25
        }
        
        weighted_score = 0.0
        total_weight = 0.0
        for category, stats in category_results.items():
            weight = category_weights.get(category, 0.25)
            cat_accuracy = stats['verified'] / stats['total'] if stats['total'] > 0 else 1.0
            weighted_score += weight * cat_accuracy
            total_weight += weight
        
        weighted_accuracy = weighted_score / total_weight if total_weight > 0 else accuracy
        
        # 构建详细结果
        details = []
        for result in results:
            details.append({
                'subject': result.claim.subject,
                'category': result.claim.category,
                'claim_type': result.claim.claim_type,
                'is_verified': result.is_verified,
                'confidence': result.confidence,
                'source_url': result.source_url,
                'source_snippet': result.source_snippet[:200] if result.source_snippet else '',
                'explanation': result.explanation
            })
        
        # 类别得分
        category_scores = {}
        for category, stats in category_results.items():
            category_scores[category] = {
                'verified': stats['verified'],
                'total': stats['total'],
                'accuracy': stats['verified'] / stats['total'] if stats['total'] > 0 else 1.0
            }
        
        return {
            'total_claims': len(claims),
            'verified_claims': verified_count,
            'checked_claims': total_count,
            'accuracy': accuracy,
            'weighted_accuracy': weighted_accuracy,
            'details': details,
            'category_scores': category_scores
        }


def test_fact_checker():
    """测试事实验证器"""
    print("=" * 60)
    print("  事实准确度验证器测试")
    print("=" * 60)
    
    # 测试数据
    test_plan = {
        "hotel": [{"name": "全季酒店"}],
        "itinerary": {
            "day1": [
                {"action": "sightseeing", "location": "外滩"},
                {"action": "dining", "location": "南京路步行街"}
            ],
            "day2": [
                {"action": "sightseeing", "location": "东方明珠"},
                {"action": "sightseeing", "location": "城隍庙"}
            ]
        }
    }
    
    # 初始化验证器 (使用 DuckDuckGo 免费搜索)
    checker = FactChecker(search_engine="duckduckgo")
    
    # 提取声明
    claims = checker.extract_claims(test_plan, "上海")
    print(f"\n📋 提取到 {len(claims)} 个可验证的事实声明:")
    for i, claim in enumerate(claims, 1):
        print(f"   {i}. [{claim.category}] {claim.claim_text}")
    
    # 验证计划
    print("\n⏳ 正在联网验证...")
    result = checker.verify_plan(test_plan, "上海", max_checks=5)
    
    print(f"\n📊 验证结果:")
    print(f"   总声明数: {result['total_claims']}")
    print(f"   已验证数: {result['checked_claims']}")
    print(f"   通过数: {result['verified_claims']}")
    print(f"   准确度: {result['accuracy']*100:.1f}%")
    print(f"   加权准确度: {result['weighted_accuracy']*100:.1f}%")
    
    print("\n📝 详细结果:")
    for detail in result['details']:
        status = "✅" if detail['is_verified'] else "❌"
        print(f"   {status} {detail['subject']} - {detail['explanation']}")
    
    print("\n" + "=" * 60)


if __name__ == '__main__':
    test_fact_checker()

