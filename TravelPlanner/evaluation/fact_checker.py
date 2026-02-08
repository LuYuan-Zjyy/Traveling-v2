#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TravelPlanner 事实准确度验证模块

通过联网搜索验证计划中的景点、餐厅、住宿是否真实存在，并验证城市匹配。

支持的搜索引擎:
- DuckDuckGo (免费)
- SerpAPI
- Bing Search API
"""

import os
import sys
import re
import json
import time
import warnings
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
from enum import Enum

warnings.filterwarnings('ignore')

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class SearchEngine(Enum):
    SERPAPI = "serpapi"
    BING = "bing"
    DUCKDUCKGO = "duckduckgo"


@dataclass
class FactClaim:
    """可验证的事实声明"""
    category: str        # restaurant, attraction, accommodation
    subject: str         # 名称
    city: str            # 城市
    day: int             # 第几天
    claim_type: str      # exists


@dataclass
class VerificationResult:
    """验证结果"""
    claim: FactClaim
    is_verified: bool
    confidence: float
    source: str
    explanation: str


class SearchClient:
    """搜索客户端"""
    
    def __init__(self, api_key: str = None, engine: SearchEngine = SearchEngine.DUCKDUCKGO):
        self.api_key = api_key or os.getenv('SEARCH_API')
        self.engine = engine
        self.request_count = 0
        self.last_request_time = 0
    
    def _rate_limit(self):
        """速率限制"""
        current = time.time()
        if current - self.last_request_time < 2:
            time.sleep(2)
        self.last_request_time = time.time()
        self.request_count += 1
    
    def search(self, query: str, num_results: int = 3) -> List[Dict]:
        """执行搜索"""
        self._rate_limit()
        
        if self.engine == SearchEngine.DUCKDUCKGO:
            return self._search_duckduckgo(query, num_results)
        elif self.engine == SearchEngine.SERPAPI:
            return self._search_serpapi(query, num_results)
        elif self.engine == SearchEngine.BING:
            return self._search_bing(query, num_results)
        return []
    
    def _search_duckduckgo(self, query: str, num_results: int) -> List[Dict]:
        """DuckDuckGo 搜索"""
        try:
            try:
                from ddgs import DDGS
            except ImportError:
                from duckduckgo_search import DDGS
            
            with DDGS() as ddgs:
                results = []
                for attempt in range(3):
                    try:
                        for r in ddgs.text(query, max_results=num_results):
                            results.append({
                                'title': r.get('title', ''),
                                'snippet': r.get('body', ''),
                                'url': r.get('href', '')
                            })
                        if results:
                            break
                    except:
                        time.sleep(1)
                return results
        except:
            return []
    
    def _search_serpapi(self, query: str, num_results: int) -> List[Dict]:
        """SerpAPI 搜索"""
        import requests
        try:
            url = "https://serpapi.com/search"
            params = {"q": query, "api_key": self.api_key, "num": num_results}
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return [
                    {'title': r.get('title', ''), 'snippet': r.get('snippet', ''), 'url': r.get('link', '')}
                    for r in data.get('organic_results', [])[:num_results]
                ]
        except:
            pass
        return []
    
    def _search_bing(self, query: str, num_results: int) -> List[Dict]:
        """Bing 搜索"""
        import requests
        try:
            url = "https://api.bing.microsoft.com/v7.0/search"
            headers = {"Ocp-Apim-Subscription-Key": self.api_key}
            params = {"q": query, "count": num_results}
            response = requests.get(url, headers=headers, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return [
                    {'title': r.get('name', ''), 'snippet': r.get('snippet', ''), 'url': r.get('url', '')}
                    for r in data.get('webPages', {}).get('value', [])[:num_results]
                ]
        except:
            pass
        return []


class TravelPlannerFactChecker:
    """TravelPlanner 事实验证器"""
    
    def __init__(self, api_key: str = None, search_engine: str = "duckduckgo", use_local: bool = True):
        engine = SearchEngine(search_engine) if search_engine in [e.value for e in SearchEngine] else SearchEngine.DUCKDUCKGO
        self.search_client = SearchClient(api_key, engine)
        self.use_local = use_local
        self.cache = {}
        
        # 加载本地数据
        self.local_restaurants = set()
        self.local_attractions = set()
        self.local_accommodations = set()
        self.city_data = {}
        
        if use_local:
            self._load_local_data()
    
    def _load_local_data(self):
        """加载本地数据库"""
        import pandas as pd
        
        db_path = os.path.join(os.path.dirname(__file__), '..', 'database')
        
        try:
            # 餐厅
            rest_path = os.path.join(db_path, 'restaurants', 'clean_restaurant_2022.csv')
            if os.path.exists(rest_path):
                df = pd.read_csv(rest_path)
                for _, row in df.iterrows():
                    name = str(row.get('Name', '')).lower()
                    city = str(row.get('City', '')).lower()
                    self.local_restaurants.add(name)
                    if city not in self.city_data:
                        self.city_data[city] = {'restaurants': set(), 'attractions': set(), 'accommodations': set()}
                    self.city_data[city]['restaurants'].add(name)
            
            # 景点
            attr_path = os.path.join(db_path, 'attractions', 'attractions.csv')
            if os.path.exists(attr_path):
                df = pd.read_csv(attr_path)
                for _, row in df.iterrows():
                    name = str(row.get('Name', '')).lower()
                    city = str(row.get('City', '')).lower()
                    self.local_attractions.add(name)
                    if city not in self.city_data:
                        self.city_data[city] = {'restaurants': set(), 'attractions': set(), 'accommodations': set()}
                    self.city_data[city]['attractions'].add(name)
            
            # 住宿
            acc_path = os.path.join(db_path, 'accommodations', 'clean_accommodations_2022.csv')
            if os.path.exists(acc_path):
                df = pd.read_csv(acc_path)
                for _, row in df.iterrows():
                    name = str(row.get('NAME', '')).lower()
                    city = str(row.get('city', '')).lower()
                    self.local_accommodations.add(name)
                    if city not in self.city_data:
                        self.city_data[city] = {'restaurants': set(), 'attractions': set(), 'accommodations': set()}
                    self.city_data[city]['accommodations'].add(name)
            
            total = len(self.local_restaurants) + len(self.local_attractions) + len(self.local_accommodations)
            if total > 0:
                print(f"   已加载本地数据: {len(self.local_restaurants)} 餐厅, {len(self.local_attractions)} 景点, {len(self.local_accommodations)} 住宿")
        except Exception as e:
            print(f"   加载本地数据失败: {e}")
    
    def _extract_name_city(self, text: str) -> Tuple[str, str]:
        """从文本中提取名称和城市"""
        if not text or text == '-':
            return '', ''
        
        # 格式: "Name, City" 或 "Name (City)"
        if '(' in text and ')' in text:
            match = re.match(r'(.+?)\s*\(([^)]+)\)', text)
            if match:
                return match.group(1).strip(), match.group(2).strip()
        
        if ',' in text:
            parts = text.rsplit(',', 1)
            if len(parts) == 2:
                return parts[0].strip(), parts[1].strip()
        
        return text.strip(), ''
    
    def extract_claims(self, plan: List[Dict]) -> List[FactClaim]:
        """从计划中提取可验证的事实声明"""
        claims = []
        
        for day_idx, day_plan in enumerate(plan):
            day = day_idx + 1
            
            # 餐厅
            for meal in ['breakfast', 'lunch', 'dinner']:
                if meal in day_plan and day_plan[meal] and day_plan[meal] != '-':
                    name, city = self._extract_name_city(day_plan[meal])
                    if name:
                        claims.append(FactClaim(
                            category='restaurant',
                            subject=name,
                            city=city,
                            day=day,
                            claim_type='exists'
                        ))
            
            # 景点
            if 'attraction' in day_plan and day_plan['attraction'] and day_plan['attraction'] != '-':
                attractions = day_plan['attraction'].split(';')
                for attr in attractions:
                    attr = attr.strip()
                    if attr:
                        name, city = self._extract_name_city(attr)
                        if name:
                            claims.append(FactClaim(
                                category='attraction',
                                subject=name,
                                city=city,
                                day=day,
                                claim_type='exists'
                            ))
            
            # 住宿
            if 'accommodation' in day_plan and day_plan['accommodation'] and day_plan['accommodation'] != '-':
                name, city = self._extract_name_city(day_plan['accommodation'])
                if name:
                    claims.append(FactClaim(
                        category='accommodation',
                        subject=name,
                        city=city,
                        day=day,
                        claim_type='exists'
                    ))
        
        return claims
    
    def verify_claim(self, claim: FactClaim) -> VerificationResult:
        """验证单个声明"""
        cache_key = f"{claim.subject}_{claim.city}_{claim.category}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        subject_lower = claim.subject.lower()
        city_lower = claim.city.lower() if claim.city else ''
        
        # 本地验证
        if self.use_local:
            result = self._verify_local(claim, subject_lower, city_lower)
            if result.is_verified:
                self.cache[cache_key] = result
                return result
        
        # 联网验证
        result = self._verify_online(claim)
        self.cache[cache_key] = result
        return result
    
    def _verify_local(self, claim: FactClaim, subject_lower: str, city_lower: str) -> VerificationResult:
        """本地数据库验证"""
        from fuzzywuzzy import fuzz
        
        # 选择数据集
        if claim.category == 'restaurant':
            dataset = self.local_restaurants
            city_dataset = self.city_data.get(city_lower, {}).get('restaurants', set()) if city_lower else set()
        elif claim.category == 'attraction':
            dataset = self.local_attractions
            city_dataset = self.city_data.get(city_lower, {}).get('attractions', set()) if city_lower else set()
        else:
            dataset = self.local_accommodations
            city_dataset = self.city_data.get(city_lower, {}).get('accommodations', set()) if city_lower else set()
        
        # 精确匹配
        if subject_lower in dataset:
            # 检查城市
            if city_lower and city_dataset and subject_lower not in city_dataset:
                return VerificationResult(
                    claim=claim,
                    is_verified=False,
                    confidence=0.0,
                    source="本地数据库",
                    explanation=f"城市不匹配: '{claim.subject}' 不在 {claim.city}"
                )
            return VerificationResult(
                claim=claim,
                is_verified=True,
                confidence=1.0,
                source="本地数据库",
                explanation=f"精确匹配: '{claim.subject}'"
            )
        
        # 模糊匹配
        best_match = None
        best_score = 0
        for item in dataset:
            score = fuzz.ratio(subject_lower, item)
            if score > best_score:
                best_score = score
                best_match = item
        
        if best_score >= 85:
            return VerificationResult(
                claim=claim,
                is_verified=True,
                confidence=best_score / 100.0,
                source="本地数据库",
                explanation=f"模糊匹配: '{claim.subject}' → '{best_match}' ({best_score}%)"
            )
        
        return VerificationResult(
            claim=claim,
            is_verified=False,
            confidence=0.0,
            source="本地数据库",
            explanation=f"未找到: '{claim.subject}'"
        )
    
    def _verify_online(self, claim: FactClaim) -> VerificationResult:
        """联网验证"""
        query = f"{claim.subject} {claim.city} {claim.category}"
        results = self.search_client.search(query, num_results=3)
        
        if not results:
            return VerificationResult(
                claim=claim,
                is_verified=False,
                confidence=0.0,
                source="联网搜索",
                explanation="搜索无结果"
            )
        
        # 分析搜索结果
        subject_lower = claim.subject.lower()
        for result in results:
            combined = (result.get('title', '') + ' ' + result.get('snippet', '')).lower()
            if subject_lower in combined or any(word in combined for word in subject_lower.split()[:2]):
                return VerificationResult(
                    claim=claim,
                    is_verified=True,
                    confidence=0.7,
                    source=result.get('url', '联网搜索'),
                    explanation=f"搜索验证: 找到 '{claim.subject}'"
                )
        
        return VerificationResult(
            claim=claim,
            is_verified=False,
            confidence=0.0,
            source="联网搜索",
            explanation=f"未找到匹配: '{claim.subject}'"
        )
    
    def verify_plan(self, plan: List[Dict], max_checks: int = 10) -> Dict:
        """验证整个计划"""
        claims = self.extract_claims(plan)
        
        if not claims:
            return {
                'total_claims': 0,
                'verified': 0,
                'accuracy': 1.0,
                'details': []
            }
        
        # 限制检查数量
        claims_to_check = claims[:max_checks]
        
        results = []
        verified_count = 0
        
        for claim in claims_to_check:
            result = self.verify_claim(claim)
            results.append({
                'subject': claim.subject,
                'city': claim.city,
                'category': claim.category,
                'day': claim.day,
                'is_verified': result.is_verified,
                'confidence': result.confidence,
                'explanation': result.explanation
            })
            if result.is_verified:
                verified_count += 1
        
        return {
            'total_claims': len(claims),
            'checked': len(claims_to_check),
            'verified': verified_count,
            'accuracy': verified_count / len(claims_to_check) if claims_to_check else 1.0,
            'details': results
        }


if __name__ == '__main__':
    # 测试
    print("TravelPlanner 事实验证器测试")
    checker = TravelPlannerFactChecker(search_engine="duckduckgo")
    
    # 测试计划
    test_plan = [
        {
            'current_city': 'New York',
            'transportation': '-',
            'breakfast': 'Katz\'s Delicatessen, New York',
            'attraction': 'Central Park, New York;Statue of Liberty, New York;',
            'lunch': 'Joe\'s Pizza, New York',
            'dinner': 'Peter Luger Steak House, New York',
            'accommodation': 'The Plaza Hotel, New York'
        }
    ]
    
    result = checker.verify_plan(test_plan, max_checks=5)
    print(f"\n验证结果: {result['verified']}/{result['checked']} 通过")
    print(f"准确度: {result['accuracy']*100:.1f}%")
    for d in result['details']:
        status = "✓" if d['is_verified'] else "✗"
        print(f"  {status} [{d['category']}] {d['subject']}: {d['explanation']}")



