"""
增量知识库系统
持续学习和积累旅游规划知识
"""

import json
import threading
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
import hashlib


@dataclass
class Knowledge:
    """知识项"""
    id: str
    timestamp: str
    source_agent: str
    knowledge_type: str  # artifact, cultural, price, route, activity, etc.
    category: str  # destination, experience, cost, etc.
    content: Dict[str, Any]
    tags: List[str]
    confidence: float
    multimodal_data: Optional[Dict[str, Any]] = None
    related_to: Optional[List[str]] = None  # 关联的其他知识IDs

    def __post_init__(self):
        if self.related_to is None:
            self.related_to = []


class KnowledgeBaseManager:
    """知识库管理器 - 增量学习系统"""
    
    def __init__(self, kb_path: str = "data/knowledge_base"):
        self.kb_path = Path(kb_path)
        self.kb_path.mkdir(parents=True, exist_ok=True)

        # 索引文件路径
        self.index_path = self.kb_path / "index.json"
        self.knowledge_index: Dict[str, str] = self._load_index()

        # 并发写保护锁
        self._lock = threading.Lock()
    
    def learn_from_agent_output(self, agent_name: str, output: Dict[str, Any], 
                               knowledge_type: str = "artifact"):
        """
        从Agent的输出中学习
        
        Args:
            agent_name: Agent名称
            output: Agent的输出结果
            knowledge_type: 知识类型
        """
        # 提取可学习的知识
        learnings = self._extract_knowledge_from_output(agent_name, output, knowledge_type)
        
        # 存储每个知识项
        for learning in learnings:
            self.store_knowledge(learning)
    
    def store_knowledge(self, knowledge: Knowledge):
        """存储知识项（线程安全）"""
        with self._lock:
            # 生成知识ID
            knowledge.id = self._generate_knowledge_id(knowledge)

            # 创建分类目录
            category_dir = self.kb_path / knowledge.category
            category_dir.mkdir(exist_ok=True)

            # 保存知识文件
            file_path = category_dir / f"{knowledge.id}.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(asdict(knowledge), f, ensure_ascii=False, indent=2)

            # 更新索引
            self.knowledge_index[knowledge.id] = str(file_path)
            self._save_index()

        print(f"✓ 知识已保存: {knowledge.id} ({knowledge.knowledge_type})")
    
    def retrieve_knowledge(self, query: str, 
                          knowledge_type: Optional[str] = None,
                          category: Optional[str] = None,
                          limit: int = 5) -> List[Knowledge]:
        """
        查询知识库
        
        Args:
            query: 查询关键词
            knowledge_type: 知识类型过滤
            category: 分类过滤
            limit: 返回数量限制
        """
        results = []
        
        for file_path_str in self.knowledge_index.values():
            file_path = Path(file_path_str)
            if not file_path.exists():
                continue
            
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                knowledge = Knowledge(**data)
            
            # 应用过滤条件
            if knowledge_type and knowledge.knowledge_type != knowledge_type:
                continue
            if category and knowledge.category != category:
                continue
            
            # 检查查询关键词匹配
            if self._match_query(knowledge, query):
                results.append(knowledge)
        
        # 按时间排序,最新的在前
        results.sort(key=lambda k: k.timestamp, reverse=True)
        return results[:limit]
    
    def get_destination_knowledge(self, destination: str,
                                  knowledge_type: Optional[str] = None,
                                  limit: int = 10) -> List[Dict[str, Any]]:
        """
        供 Agent 在规划前检索已有目的地知识。

        通过复用已积累的文化、路线、价格等知识，减少 LLM 重复调用
        和幻觉风险。

        Args:
            destination: 目的地名称（关键词匹配）
            knowledge_type: 知识类型过滤，如 "cultural_insight"、"price_info"、
                            "route_pattern" 等；None 表示不过滤
            limit: 返回数量上限

        Returns:
            匹配的知识列表，每项为 {"type", "content", "confidence", "timestamp"}
        """
        results = self.retrieve_knowledge(
            query=destination,
            knowledge_type=knowledge_type,
            limit=limit,
        )
        return [
            {
                "type": k.knowledge_type,
                "content": k.content,
                "confidence": k.confidence,
                "timestamp": k.timestamp,
                "tags": k.tags,
            }
            for k in results
        ]

    def learn_from_user_correction(self, original: Dict[str, Any], 
                                  correction: Dict[str, Any]):
        """从用户纠正中学习"""
        knowledge = Knowledge(
            id="",
            timestamp=datetime.now().isoformat(),
            source_agent="user_feedback",
            knowledge_type="correction",
            category="user_corrections",
            content={
                "original": original,
                "correction": correction
            },
            tags=["corrected", "verified"],
            confidence=1.0  # 用户反馈最可信
        )
        self.store_knowledge(knowledge)
    
    def learn_from_multimodal(self, agent_name: str, data: Dict[str, Any]):
        """从多模态数据中学习 (图片、视频等)"""
        knowledge = Knowledge(
            id="",
            timestamp=datetime.now().isoformat(),
            source_agent=agent_name,
            knowledge_type="multimodal",
            category="media",
            content={"description": data.get("description", "")},
            tags=data.get("tags", ["multimodal"]),
            confidence=data.get("confidence", 0.8),
            multimodal_data=data
        )
        self.store_knowledge(knowledge)
    
    def get_kb_statistics(self) -> Dict[str, Any]:
        """获取知识库统计信息"""
        stats = {
            "total_knowledge": len(self.knowledge_index),
            "by_type": {},
            "by_category": {},
            "last_updated": None
        }
        
        for file_path_str in self.knowledge_index.values():
            file_path = Path(file_path_str)
            if not file_path.exists():
                continue
            
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            k_type = data["knowledge_type"]
            category = data["category"]
            
            stats["by_type"][k_type] = stats["by_type"].get(k_type, 0) + 1
            stats["by_category"][category] = stats["by_category"].get(category, 0) + 1
            
            if not stats["last_updated"] or data["timestamp"] > stats["last_updated"]:
                stats["last_updated"] = data["timestamp"]
        
        return stats
    
    def export_knowledge(self, destination: str, knowledge_type: Optional[str] = None):
        """导出知识库"""
        export_path = Path(destination)
        export_path.mkdir(parents=True, exist_ok=True)
        
        all_knowledge = []
        for file_path_str in self.knowledge_index.values():
            file_path = Path(file_path_str)
            if not file_path.exists():
                continue
            
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            if knowledge_type and data["knowledge_type"] != knowledge_type:
                continue
            
            all_knowledge.append(data)
        
        # 保存为单个JSON文件
        export_file = export_path / f"knowledge_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(export_file, "w", encoding="utf-8") as f:
            json.dump(all_knowledge, f, ensure_ascii=False, indent=2)
        
        print(f"✓ 知识库已导出到: {export_file}")
    
    def _extract_knowledge_from_output(self, agent_name: str, output: Dict[str, Any], 
                                      knowledge_type: str) -> List[Knowledge]:
        """从Agent输出中提取可学习的知识"""
        learnings = []
        
        if agent_name == "culture_agent":
            # 从文化Agent学习文化知识
            if "cultural_background" in output:
                for poi_id, background in output["cultural_background"].items():
                    knowledge = Knowledge(
                        id="",
                        timestamp=datetime.now().isoformat(),
                        source_agent=agent_name,
                        knowledge_type="cultural_insight",
                        category="cultural",
                        content={"poi_id": poi_id, "background": background},
                        tags=["culture", "artifact"],
                        confidence=0.85
                    )
                    learnings.append(knowledge)
        
        elif agent_name == "budget_agent":
            # 从预算Agent学习价格知识
            if "cost_details" in output:
                for cost in output["cost_details"]:
                    knowledge = Knowledge(
                        id="",
                        timestamp=datetime.now().isoformat(),
                        source_agent=agent_name,
                        knowledge_type="price_info",
                        category="pricing",
                        content=cost,
                        tags=["price", "cost"],
                        confidence=0.8
                    )
                    learnings.append(knowledge)
        
        elif agent_name == "route_agent":
            # 从路由Agent学习路线知识
            if "routes" in output:
                knowledge = Knowledge(
                    id="",
                    timestamp=datetime.now().isoformat(),
                    source_agent=agent_name,
                    knowledge_type="route_pattern",
                    category="routing",
                    content={"routes": output["routes"]},
                    tags=["route", "navigation"],
                    confidence=0.9
                )
                learnings.append(knowledge)
        
        return learnings
    
    def _match_query(self, knowledge: Knowledge, query: str) -> bool:
        """检查知识是否匹配查询"""
        query_lower = query.lower()
        
        # 检查标签
        for tag in knowledge.tags:
            if query_lower in tag.lower():
                return True
        
        # 检查内容
        content_str = json.dumps(knowledge.content, ensure_ascii=False).lower()
        if query_lower in content_str:
            return True
        
        return False
    
    def _generate_knowledge_id(self, knowledge: Knowledge) -> str:
        """生成知识ID"""
        content_str = json.dumps(knowledge.content, sort_keys=True)
        timestamp = knowledge.timestamp[:10]  # YYYY-MM-DD
        
        hash_obj = hashlib.md5((content_str + timestamp).encode())
        hash_str = hash_obj.hexdigest()[:8]
        
        return f"{knowledge.knowledge_type}_{hash_str}_{timestamp.replace('-', '')}"
    
    def _load_index(self) -> Dict[str, str]:
        """加载索引"""
        if self.index_path.exists():
            with open(self.index_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    
    def _save_index(self):
        """保存索引"""
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(self.knowledge_index, f, ensure_ascii=False, indent=2)
