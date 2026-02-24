"""
数据采集Agent - 获取原始旅游规划数据
负责调用高德地图API、天气API等获取基础数据
"""

from typing import Dict, List, Any, Optional
from core.base_agent import TravelPlanningAgent
from core.planning_context import PlanningContext, POI


class DataCollectionAgent(TravelPlanningAgent):
    """
    数据采集Agent
    职责：获取和整理规划所需的基础数据
    """
    
    def __init__(self, amap_client=None):
        super().__init__(name="data_collection_agent")
        self.amap_client = amap_client  # 高德地图API客户端
        self.cache = {}  # 本地缓存
    
    def _validate_input(self, context: PlanningContext) -> bool:
        """验证输入数据"""
        if not context.user_intent:
            self.memory.add_error(
                "缺少用户意图信息",
                {"context": "user_intent为None"},
                self.current_iteration
            )
            return False
        
        if not context.user_intent.destination:
            self.memory.add_error(
                "缺少目的地信息",
                {"intent": context.user_intent},
                self.current_iteration
            )
            return False
        
        return True
    
    def _execute_core(self, context: PlanningContext) -> Dict[str, Any]:
        """
        核心业务逻辑：数据采集
        
        流程：
        1. 解析目的地 -> 获取坐标
        2. 搜索景点、餐厅、酒店 (POI搜索)
        3. 查询天气信息
        4. 计算景点间的路线时间
        """
        
        result = {
            "pois": [],
            "weather": {},
            "routes": [],
            "execution_info": {
                "destination": context.user_intent.destination,
                "data_sources": []
            }
        }
        
        destination = context.user_intent.destination
        
        try:
            # Step 1: 地理编码 (地址 -> 坐标)
            coordinates = self._geocode(destination)
            if not coordinates:
                raise Exception(f"无法解析目的地: {destination}")
            
            lat, lng = coordinates["lat"], coordinates["lng"]
            print(f"✓ 目的地坐标: ({lat}, {lng})")
            
            # Step 2: 搜索POI (景点、餐厅、酒店)
            pois = self._search_pois(destination, lat, lng)
            context.pois = pois
            result["pois"] = [self._poi_to_dict(poi) for poi in pois]
            result["execution_info"]["data_sources"].append("POI搜索")
            print(f"✓ 找到 {len(pois)} 个景点")
            
            # Step 3: 查询天气
            weather = self._get_weather(destination, context.user_intent.start_date)
            context.weather = weather
            result["weather"] = weather
            result["execution_info"]["data_sources"].append("天气查询")
            print(f"✓ 天气数据已获取")
            
            # Step 4: 计算景点间的路线和距离
            if len(pois) > 1:
                routes = self._calculate_routes(pois[:5])  # 只计算前5个POI间的路线
                context.routes = routes
                result["routes"] = routes
                result["execution_info"]["data_sources"].append("路线计算")
                print(f"✓ 计算了 {len(routes)} 条路线")
            
            # Step 5: 学习和存储
            self.learn_and_store({
                "type": "location_data",
                "destination": destination,
                "poi_count": len(pois),
                "weather_status": weather.get("weather", "未知"),
                "coordinates": coordinates
            })
            
            result["status"] = "success"
            return result
            
        except Exception as e:
            print(f"✗ 数据采集失败: {e}")
            self.memory.add_error(str(e), {"destination": destination}, self.current_iteration)
            result["status"] = "error"
            result["error"] = str(e)
            return result
    
    def _geocode(self, location: str) -> Optional[Dict[str, float]]:
        """
        地址转坐标
        
        模拟实现 - 实际需要调用高德API
        """
        # 模拟高德地图常见城市坐标
        location_coords = {
            "安庆": {"lat": 30.5463, "lng": 117.0556},
            "北京": {"lat": 39.9042, "lng": 116.4074},
            "上海": {"lat": 31.2304, "lng": 121.4737},
            "西安": {"lat": 34.3416, "lng": 108.9398},
            "成都": {"lat": 30.5728, "lng": 104.0668},
        }
        
        # 检查缓存
        if location in self.cache:
            return self.cache[location]
        
        # 如果有真实API，调用它
        if self.amap_client:
            try:
                result = self.amap_client.geocode(location)
                self.cache[location] = result
                return result
            except Exception as e:
                print(f"API调用失败: {e}，使用默认值")
        
        # 返回默认值或None
        result = location_coords.get(location, None)
        if result:
            self.cache[location] = result
        return result
    
    def _search_pois(self, location: str, lat: float, lng: float, 
                     poi_types: List[str] = None) -> List[POI]:
        """
        搜索POI (景点、餐厅、酒店等)
        
        模拟实现 - 实际需要调用高德API
        """
        if poi_types is None:
            poi_types = ["景点", "餐厅", "酒店"]
        
        # 模拟数据
        mock_pois = {
            "安庆": [
                POI(
                    id="poi_001",
                    name="黄梅戏博物馆",
                    category="景点",
                    location={"lat": 30.6465, "lng": 117.0576},
                    rating=4.8,
                    price=60,
                    opening_hours="09:00-17:00",
                    description="黄梅戏发源地和传承中心",
                    images=[]
                ),
                POI(
                    id="poi_002",
                    name="天柱山",
                    category="景点",
                    location={"lat": 30.3823, "lng": 116.7697},
                    rating=4.5,
                    price=95,
                    opening_hours="06:00-18:00",
                    description="安徽名山"
                ),
                POI(
                    id="poi_003",
                    name="菱湖公园",
                    category="景点",
                    location={"lat": 30.5543, "lng": 117.0463},
                    rating=4.2,
                    price=0,
                    opening_hours="全天"
                ),
                POI(
                    id="rest_001",
                    name="安庆特色餐厅",
                    category="餐厅",
                    location={"lat": 30.5663, "lng": 117.0676},
                    rating=4.3,
                    price=60,
                    description="正宗安庆菜"
                ),
                POI(
                    id="hotel_001",
                    name="安庆星级酒店",
                    category="酒店",
                    location={"lat": 30.5463, "lng": 117.0456},
                    rating=4.0,
                    price=180,
                    description="舒适商务酒店"
                ),
            ]
        }
        
        # 如果有真实API，调用它
        if self.amap_client:
            try:
                pois = self.amap_client.search_pois(location, lat, lng, poi_types)
                return pois
            except Exception as e:
                print(f"POI搜索API失败: {e}")
        
        # 返回模拟数据
        return mock_pois.get(location, [])
    
    def _get_weather(self, location: str, date: Optional[str] = None) -> Dict[str, Any]:
        """
        查询天气
        
        模拟实现 - 实际需要调用天气API
        """
        # 模拟天气数据
        weather_data = {
            "安庆": {
                "date": date or "2026-03-01",
                "city": "安庆",
                "weather": "晴",
                "high_temp": 25,
                "low_temp": 15,
                "humidity": 65,
                "wind": "3级",
                "uv_index": 6,
                "air_quality": "良好"
            }
        }
        
        # 如果有真实API，调用它
        if self.amap_client:
            try:
                weather = self.amap_client.get_weather(location, date)
                return weather
            except Exception as e:
                print(f"天气查询API失败: {e}")
        
        return weather_data.get(location, {})
    
    def _calculate_routes(self, pois: List[POI], 
                         transport_mode: str = "driving") -> List[Dict[str, Any]]:
        """
        计算POI之间的路线和距离
        
        模拟实现 - 实际需要调用高德路线API
        """
        routes = []
        
        for i in range(len(pois) - 1):
            from_poi = pois[i]
            to_poi = pois[i + 1]
            
            # 模拟计算距离和时间
            from_lat, from_lng = from_poi.location["lat"], from_poi.location["lng"]
            to_lat, to_lng = to_poi.location["lat"], to_poi.location["lng"]
            
            # 简单的欧几里得距离 (实际应使用真实路线API)
            import math
            distance_km = math.sqrt((to_lat - from_lat)**2 + (to_lng - from_lng)**2) * 111
            
            route = {
                "from": from_poi.name,
                "to": to_poi.name,
                "distance_km": round(distance_km, 2),
                "duration_minutes": max(15, int(distance_km * 3)),  # 估算时间
                "transport_mode": transport_mode
            }
            routes.append(route)
        
        return routes
    
    def _poi_to_dict(self, poi: POI) -> Dict[str, Any]:
        """将POI对象转换为字典"""
        return {
            "id": poi.id,
            "name": poi.name,
            "category": poi.category,
            "location": poi.location,
            "rating": poi.rating,
            "price": poi.price,
            "opening_hours": poi.opening_hours,
            "description": poi.description,
            "images": poi.images
        }
    
    def get_status(self) -> Dict[str, Any]:
        """获取Agent状态"""
        status = super().get_status()
        status["cache_size"] = len(self.cache)
        return status
