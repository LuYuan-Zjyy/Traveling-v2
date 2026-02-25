"""
文化体验Agent - 为用户打造有灵魂的旅行体验
负责文化主题识别、文化景点筛选、故事生成等
这是系统的核心差异点！
"""

from typing import Dict, List, Any, Optional
from core.base_agent import TravelPlanningAgent
from core.planning_context import PlanningContext, POI
import json


class CultureAgent(TravelPlanningAgent):
    """
    文化体验Agent 【关键Agent】
    
    职责：
    • 文化主题识别 - 匹配用户偏好和目的地特色
    • 资源匹配 - 筛选最符合的文化景点
    • 活动规划 - 推荐文化活动和特色体验
    • 背景生成 - 为景点编写文化说明和故事
    • 体验设计 - 创意组合(如"沉浸式非遗体验")
    """
    
    def __init__(self, llm_client=None):
        super().__init__(name="culture_agent")
        self.llm_client = llm_client  # DeepSeek LLM客户端
        
        # 文化数据库 (企业级应该使用真实数据库)
        self.cultural_db = self._init_cultural_database()
    
    def _init_cultural_database(self) -> Dict[str, Any]:
        """初始化文化数据库"""
        return {
            "安庆": {
                "cultural_themes": ["黄梅戏", "乡村体验", "江南文化", "戏曲传承"],
                "heritage_items": [
                    {
                        "name": "黄梅戏",
                        "type": "非遗",
                        "category": "戏曲",
                        "story": "黄梅戏起源于安庆，是中国第五大戏曲，有600多年的历史。",
                        "related_pois": ["黄梅戏博物馆", "戏曲传承基地"],
                        "activities": ["观看演出", "学习基本动作", "演员互动"]
                    },
                    {
                        "name": "江南乡村文化",
                        "type": "民俗",
                        "category": "乡村体验",
                        "story": "安庆周边保留着传统的江南乡村风景，展现原汁原味的农业文明。",
                        "related_pois": ["乡村民宿", "农场体验基地"],
                        "activities": ["农田体验", "民宿住宿", "农民生活体验"]
                    }
                ],
                "scenic_spots_cultural_value": {
                    "黄梅戏博物馆": {"heritage_priority": 1, "must_visit": True},
                    "天柱山": {"heritage_priority": 2, "history_story": "道教文化圣地"},
                    "菱湖公园": {"heritage_priority": 3, "cultural_note": "江南园林风格"}
                }
            },
            "上海": {
                "cultural_themes": ["海派文化", "现代都市", "亲子科普", "工业遗存", "时尚艺术", "美食文化"],
                "pref_theme_map": {
                    "亲子": "亲子科普",
                    "美食": "美食文化",
                    "历史文化": "海派文化",
                    "自然风光": "现代都市",
                    "购物": "时尚艺术",
                    "户外运动": "滨江都市探索",
                },
                "scenic_spots_cultural_value": {
                    "外滩": {"heritage_priority": 1, "must_visit": True, "history_story": "万国建筑博览群，上海近代史缩影"},
                    "豫园": {"heritage_priority": 1, "must_visit": True, "history_story": "明代古典园林，老城厢文化核心"},
                    "上海博物馆": {"heritage_priority": 2, "history_story": "珍藏中国古代艺术珍品"},
                    "田子坊": {"heritage_priority": 3, "cultural_note": "石库门建筑群，创意艺术聚集地"},
                    "新天地": {"heritage_priority": 3, "cultural_note": "里弄文化与现代时尚融合"},
                }
            },
            "北京": {
                "cultural_themes": ["皇家文化", "四合院民俗", "历史文化", "胡同文化", "红色文化"],
                "pref_theme_map": {
                    "历史文化": "皇家文化",
                    "亲子": "历史文化",
                    "美食": "胡同文化",
                    "乡村体验": "四合院民俗",
                },
                "scenic_spots_cultural_value": {
                    "故宫": {"heritage_priority": 1, "must_visit": True},
                    "天安门": {"heritage_priority": 1, "must_visit": True},
                    "颐和园": {"heritage_priority": 2},
                    "南锣鼓巷": {"heritage_priority": 3, "cultural_note": "胡同文化代表"},
                }
            },
            "杭州": {
                "cultural_themes": ["西湖文化", "江南园林", "丝绸文化", "茶道文化", "南宋历史"],
                "pref_theme_map": {
                    "自然风光": "西湖文化",
                    "历史文化": "南宋历史",
                    "美食": "茶道文化",
                    "乡村体验": "江南园林",
                },
                "scenic_spots_cultural_value": {
                    "西湖": {"heritage_priority": 1, "must_visit": True},
                    "灵隐寺": {"heritage_priority": 2},
                    "西溪湿地": {"heritage_priority": 3},
                }
            },
            "成都": {
                "cultural_themes": ["巴蜀文化", "熊猫文化", "川菜文化", "三国文化", "道教文化"],
                "pref_theme_map": {
                    "美食": "川菜文化",
                    "亲子": "熊猫文化",
                    "历史文化": "三国文化",
                    "自然风光": "巴蜀文化",
                },
                "scenic_spots_cultural_value": {
                    "大熊猫繁育研究基地": {"heritage_priority": 1, "must_visit": True},
                    "宽窄巷子": {"heritage_priority": 2},
                    "武侯祠": {"heritage_priority": 2, "history_story": "三国蜀汉文化圣地"},
                    "锦里": {"heritage_priority": 3},
                }
            },
            "西安": {
                "cultural_themes": ["秦汉文化", "丝绸之路", "古城文化", "唐代文化", "关中民俗"],
                "pref_theme_map": {
                    "历史文化": "秦汉文化",
                    "美食": "关中民俗",
                    "自然风光": "古城文化",
                    "亲子": "唐代文化",
                },
                "scenic_spots_cultural_value": {
                    "兵马俑": {"heritage_priority": 1, "must_visit": True},
                    "大雁塔": {"heritage_priority": 2},
                    "回民街": {"heritage_priority": 2, "cultural_note": "西北美食文化地标"},
                    "城墙": {"heritage_priority": 1},
                }
            },
            "苏州": {
                "cultural_themes": ["园林文化", "昆曲", "丝绸刺绣", "江南水乡", "吴文化"],
                "pref_theme_map": {
                    "历史文化": "园林文化",
                    "美食": "江南水乡",
                    "自然风光": "江南水乡",
                    "亲子": "吴文化",
                },
                "scenic_spots_cultural_value": {
                    "拙政园": {"heritage_priority": 1, "must_visit": True},
                    "虎丘": {"heritage_priority": 2},
                    "山塘街": {"heritage_priority": 2},
                }
            },
            "黄山": {
                "cultural_themes": ["徽文化", "山水文化", "茶道", "徽派建筑", "自然奇观"],
                "pref_theme_map": {
                    "自然风光": "山水文化",
                    "历史文化": "徽文化",
                    "美食": "茶道",
                    "户外运动": "自然奇观",
                },
                "scenic_spots_cultural_value": {
                    "黄山": {"heritage_priority": 1, "must_visit": True},
                    "宏村": {"heritage_priority": 2},
                    "西递": {"heritage_priority": 2},
                }
            },
            "厦门": {
                "cultural_themes": ["闽南文化", "骑楼建筑", "海洋文化", "侨乡文化", "海峡文化"],
                "pref_theme_map": {
                    "自然风光": "海洋文化",
                    "历史文化": "骑楼建筑",
                    "美食": "闽南文化",
                    "亲子": "海洋文化",
                },
                "scenic_spots_cultural_value": {
                    "鼓浪屿": {"heritage_priority": 1, "must_visit": True},
                    "南普陀寺": {"heritage_priority": 2},
                    "曾厝垵": {"heritage_priority": 3},
                }
            },
            "桂林": {
                "cultural_themes": ["山水文化", "喀斯特地貌", "壮族文化", "漓江文化"],
                "pref_theme_map": {
                    "自然风光": "山水文化",
                    "历史文化": "壮族文化",
                    "户外运动": "喀斯特地貌",
                    "亲子": "漓江文化",
                },
                "scenic_spots_cultural_value": {
                    "漓江": {"heritage_priority": 1, "must_visit": True},
                    "象鼻山": {"heritage_priority": 2},
                    "阳朔": {"heritage_priority": 2},
                }
            },
        }
    
    def _validate_input(self, context: PlanningContext) -> bool:
        """验证输入数据"""
        # 需要POI列表和用户意图
        if not context.pois:
            self.memory.add_error(
                "缺少POI列表",
                {"pois_count": len(context.pois)},
                self.current_iteration
            )
            # 但不失败 - 可以只输出文化主题而没有具体景点
        
        if not context.user_intent:
            self.memory.add_error(
                "缺少用户意图",
                {},
                self.current_iteration
            )
            return False
        
        return True
    
    def _execute_core(self, context: PlanningContext) -> Dict[str, Any]:
        """
        核心业务逻辑：文化体验规划
        
        流程：
        1. 识别文化主题 (基于用户偏好 + 目的地特色)
        2. 筛选文化景点 (按优先级)
        3. 推荐文化活动
        4. 生成景点故事和背景
        5. 设计体验组合
        """
        
        result = {
            "cultural_theme": "",
            "cultural_pois": [],
            "cultural_background": {},
            "activities": [],
            "special_experiences": [],
            "status": "success"
        }
        
        try:
            destination = context.user_intent.destination
            preferences = context.user_intent.preferences or []
            
            # Step 1: 识别文化主题
            theme = self._identify_cultural_theme(destination, preferences)
            result["cultural_theme"] = theme
            context.cultural_theme = theme  # 回写到共享上下文
            print(f"✓ 文化主题: {theme}")

            # Step 2: 筛选和排序文化景点
            if context.pois:
                cultural_pois = self._filter_cultural_pois(context.pois, destination, theme)
                result["cultural_pois"] = cultural_pois
                context.cultural_pois = cultural_pois  # 回写到共享上下文
                print(f"✓ 文化景点: {len(cultural_pois)} 个")

                # Step 3: 为每个景点生成文化背景
                for poi in context.pois:
                    if poi.name in [cp.get("name") for cp in cultural_pois]:
                        background = self._generate_cultural_background(destination, poi)
                        result["cultural_background"][poi.id] = background
                context.cultural_background = result["cultural_background"]  # 回写
                print(f"✓ 生成了 {len(result['cultural_background'])} 个文化背景")

            # Step 4: 推荐文化活动
            activities = self._recommend_activities(destination, theme, preferences)
            result["activities"] = activities
            context.cultural_activities = activities  # 回写到共享上下文
            print(f"✓ 推荐活动: {len(activities)} 个")

            # Step 5: 设计特色体验
            experiences = self._design_special_experiences(destination, theme, preferences)
            result["special_experiences"] = experiences
            context.special_experiences = experiences  # 回写到共享上下文
            print(f"✓ 设计体验: {len(experiences)} 个")
            
            # 学习新知识
            self.learn_and_store({
                "type": "cultural_insight",
                "destination": destination,
                "theme_identified": theme,
                "user_preferences": preferences,
                "cultural_pois_count": len(result["cultural_pois"]),
                "activities_count": len(activities)
            })
            
            return result
            
        except Exception as e:
            print(f"✗ 文化体验规划失败: {e}")
            self.memory.add_error(str(e), {"destination": destination}, self.current_iteration)
            result["status"] = "error"
            result["error"] = str(e)
            return result
    
    def _identify_cultural_theme(self, destination: str, preferences: List[str]) -> str:
        """
        识别文化主题

        优先级：
        1. 目的地+偏好的精确映射（pref_theme_map）
        2. 可用主题列表的关键词模糊匹配
        3. 基于用户偏好的通用主题
        4. 目的地名 + 偏好的兜底组合
        """
        db = self.cultural_db.get(destination, {})
        available_themes = db.get("cultural_themes", [])
        pref_theme_map = db.get("pref_theme_map", {})

        # 1. 精确映射：从 pref_theme_map 找与用户偏好匹配的主题
        matched_via_map = []
        for pref in preferences:
            if pref in pref_theme_map:
                matched_via_map.append(pref_theme_map[pref])
        if matched_via_map:
            return " + ".join(list(dict.fromkeys(matched_via_map))[:2])

        # 2. 模糊匹配：用户偏好关键词 vs 可用主题列表
        matched_themes = []
        for theme in available_themes:
            for pref in preferences:
                if pref.lower() in theme.lower() or theme.lower() in pref.lower():
                    matched_themes.append(theme)
        if matched_themes:
            return " + ".join(list(dict.fromkeys(matched_themes))[:2])

        # 3. 没有偏好匹配但有目的地数据：用目的地主要前2个主题
        if available_themes:
            return " + ".join(available_themes[:2])

        # 4. 兜底：根据用户偏好动态生成描述
        PREF_FALLBACK = {
            "亲子": "亲子探索",
            "历史文化": "历史文化探索",
            "美食": "美食文化体验",
            "自然风光": "自然风光游览",
            "户外运动": "户外探险体验",
            "乡村体验": "乡村民俗体验",
            "购物": "都市休闲游",
        }
        fallback_labels = [PREF_FALLBACK[p] for p in preferences if p in PREF_FALLBACK]
        if fallback_labels:
            return f"{destination} · " + " + ".join(fallback_labels[:2])
        return f"{destination}深度游"
    
    def _filter_cultural_pois(self, pois: List[POI], destination: str, 
                            theme: str) -> List[Dict[str, Any]]:
        """
        筛选文化景点
        
        按照：
        1. 是否是文化相关景点
        2. 优先级排序
        3. 与主题的相关性
        """
        db = self.cultural_db.get(destination, {})
        cultural_values = db.get("scenic_spots_cultural_value", {})
        
        filtered = []
        
        for poi in pois:
            # 检查是否是文化景点
            if poi.category == "景点":
                priority = 5  # 默认优先级
                must_visit = False
                
                # 检查是否在文化数据库中
                if poi.name in cultural_values:
                    priority = cultural_values[poi.name].get("heritage_priority", 5)
                    must_visit = cultural_values[poi.name].get("must_visit", False)
                
                # 检查与主题的相关性
                desc = poi.description or ""
                if any(keyword in desc or keyword in poi.name or keyword in theme
                       for keyword in ["文化", "戏曲", "非遗", "历史", "乡村", "民俗"]):
                    priority -= 1  # 优先级提升
                
                filtered.append({
                    "poi_id": poi.id,
                    "name": poi.name,
                    "priority": priority,
                    "must_visit": must_visit,
                    "reason": f"与'{theme}'文化主题相关",
                    "rating": poi.rating,
                    "price": poi.price
                })
        
        # 按优先级排序
        filtered.sort(key=lambda x: x["priority"])
        
        return filtered[:5]  # 返回前5个
    
    def _generate_cultural_background(self, destination: str, poi: POI) -> str:
        """
        生成文化背景和故事
        
        使用LLM生成，或返回预定义的故事
        """
        # 预定义的故事库
        stories = {
            "黄梅戏博物馆": "黄梅戏起源于安庆，是中国第五大戏曲。博物馆馆藏丰富，展示了600多年的黄梅戏历史。",
            "天柱山": "天柱山是道教文化的重要圣地，有'江南第一山'之称。",
            "菱湖公园": "菱湖原为古代皖河故道，经过精心规划建成江南风格的生态公园。"
        }
        
        if poi.name in stories:
            return stories[poi.name]
        
        # 如果没有预定义故事，使用LLM生成
        if self.llm_client:
            try:
                prompt = f"为'{destination}'的景点'{poi.name}'生成一段150字以内的文化背景说明。"
                story = self.llm_client.generate(prompt)
                return story
            except Exception as e:
                print(f"LLM生成失败: {e}")
        
        # 返回默认说明
        return poi.description or f"{poi.name}是{destination}的重要景点。"
    
    def _recommend_activities(self, destination: str, theme: str, 
                            preferences: List[str]) -> List[Dict[str, Any]]:
        """推荐文化活动"""
        activities = []
        
        # 基于主题推荐活动
        if "黄梅戏" in theme:
            activities.extend([
                {
                    "activity": "黄梅戏演员互动讲座",
                    "time": "14:00-15:30",
                    "duration_hours": 1.5,
                    "cost": 100,
                    "level": "初级",
                    "description": "与黄梅戏演员面对面交流，了解戏曲发展历程"
                },
                {
                    "activity": "黄梅戏表演欣赏",
                    "time": "19:00-20:30",
                    "duration_hours": 1.5,
                    "cost": 200,
                    "level": "体验",
                    "description": "观看专业演员的精彩黄梅戏表演"
                },
                {
                    "activity": "沉浸式戏曲学习",
                    "time": "10:00-12:00",
                    "duration_hours": 2,
                    "cost": 300,
                    "level": "深度",
                    "description": "学习基本的唱腔、身段和动作"
                }
            ])
        
        if "乡村" in theme or "民俗" in theme:
            activities.extend([
                {
                    "activity": "农家午餐体验",
                    "time": "12:00-14:00",
                    "duration_hours": 2,
                    "cost": 80,
                    "level": "轻松",
                    "description": "品尝地道的农家菜肴，体验乡村生活"
                },
                {
                    "activity": "民宿体验",
                    "time": "18:00-08:00",
                    "duration_hours": 14,
                    "cost": 150,
                    "level": "体验",
                    "description": "住在传统的农家民宿，感受纯朴的乡村气息"
                },
                {
                    "activity": "手工艺工坊体验",
                    "time": "15:00-17:00",
                    "duration_hours": 2,
                    "cost": 120,
                    "level": "互动",
                    "description": "学习传统手工艺，制作纪念品"
                }
            ])
        
        return activities[:5]  # 返回前5个
    
    def _design_special_experiences(self, destination: str, theme: str, 
                                   preferences: List[str]) -> List[Dict[str, Any]]:
        """
        设计特色体验组合
        
        将多个活动组合成特色体验包
        """
        experiences = []
        
        if "黄梅戏" in theme:
            experiences.append({
                "name": "沉浸式非遗文化体验",
                "description": "从欣赏 → 学习 → 互动 → 表演，全程沉浸黄梅戏文化",
                "duration_hours": 4,
                "cost_estimate": 600,
                "included_activities": [
                    "黄梅戏表演欣赏(1小时)",
                    "演员互动讲座(1.5小时)",
                    "基本动作学习(1小时)",
                    "戏服体验拍照(30分钟)"
                ],
                "best_time": "下午2-6点",
                "highlights": ["与演员合影", "穿戏服拍照", "学会基本唱腔"]
            })
        
        if "乡村" in theme or "美食" in preferences:
            experiences.append({
                "name": "乡村文化美食体验",
                "description": "品尝地道农家菜，学习烹饪方式，体验乡村生活",
                "duration_hours": 6,
                "cost_estimate": 400,
                "included_activities": [
                    "农场参观(1小时)",
                    "采摘体验(1小时)",
                    "农家烹饪课程(2小时)",
                    "农家午餐享受(1小时)",
                    "民宿休息(1小时)"
                ],
                "best_time": "上午9点开始",
                "highlights": ["亲手采摘", "学会农家菜", "感受乡村气息"]
            })
        
        experiences.append({
            "name": f"{destination}文化精华一日游",
            "description": f"游历{destination}主要文化景点，深入了解{theme}文化",
            "duration_hours": 8,
            "cost_estimate": 480,
            "included_activities": [
                "早餐(1小时)",
                "主要文化景点参观(4小时)",
                "午餐特色菜(1.5小时)",
                "工艺工坊体验(1小时)",
                "下午茶(30分钟)"
            ],
            "best_time": "早上8点出发",
            "highlights": ["全面体验文化", "专业导游讲解", "记录美好回忆"]
        })
        
        return experiences
