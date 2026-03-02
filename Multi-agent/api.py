"""
FastAPI REST API 入口点
前端通过此API与多Agent系统交互
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import asyncio
import json
from datetime import datetime

# 导入核心组件
from multi_agent_orchestrator import TravelPlanningOrchestrator
from core.planning_context import UserIntent


# FastAPI应用
app = FastAPI(
    title="智能行程规划系统 API",
    description="基于多Agent的文化体验行程规划系统",
    version="1.0.0"
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 数据模型
class PlanningRequest(BaseModel):
    """规划请求"""
    destination: str
    duration_days: int
    budget: float
    preferences: Optional[List[str]] = None
    trip_type: Optional[str] = None


class PlanningResponse(BaseModel):
    """规划响应"""
    status: str
    final_plan: Optional[Dict[str, Any]] = None
    ui_modules: Optional[Dict[str, Any]] = None
    quality_score: float
    iterations: int
    suggestions: Optional[List[str]] = None
    session_id: Optional[str] = None


@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat()
    }


@app.post("/api/v1/plan", response_model=PlanningResponse)
async def create_travel_plan(request: PlanningRequest):
    """
    创建行程规划
    
    请求参数:
    - destination: 目的地 (必填)
    - duration_days: 天数 (必填, 1-30)
    - budget: 预算 (必填, 单位:¥)
    - preferences: 偏好列表 (可选)
    - trip_type: 旅行类型 (可选: cultural/adventure/food/nature)
    
    返回:
    - 完整的行程规划方案
    - UI模块数据
    - 质量评分
    - 迭代次数
    """
    
    try:
        # 验证输入
        if not request.destination or len(request.destination.strip()) == 0:
            raise HTTPException(status_code=400, detail="目的地不能为空")
        
        if request.duration_days < 1 or request.duration_days > 30:
            raise HTTPException(status_code=400, detail="天数需要在1-30天之间")
        
        if request.budget <= 0:
            raise HTTPException(status_code=400, detail="预算需要大于0")
        
        # 创建用户意图
        user_intent = UserIntent(
            destination=request.destination,
            duration_days=request.duration_days,
            budget=request.budget,
            preferences=request.preferences or [],
            trip_type=request.trip_type
        )
        
        # 创建编排器并执行
        orchestrator = TravelPlanningOrchestrator()
        response = await orchestrator.orchestrate(user_intent)
        
        # 保存会话
        if response["status"] == "success":
            session_id = orchestrator.save_session(
                user_id="web_user",
                session_name=f"{request.destination}_{request.duration_days}天游",
                response=response
            )
        else:
            session_id = None
        
        # 返回响应
        return PlanningResponse(
            status=response["status"],
            final_plan=response.get("final_plan"),
            ui_modules=response.get("ui_modules"),
            quality_score=response.get("quality_score", 0.0),
            iterations=response.get("iterations", 0),
            suggestions=response.get("suggestions", []),
            session_id=session_id
        )
        
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"❌ API错误: {e}")
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")


@app.get("/api/v1/examples")
async def get_examples():
    """
    获取规划示例
    """
    examples = [
        {
            "destination": "安庆",
            "duration_days": 3,
            "budget": 5000,
            "preferences": ["文化遗产", "美食", "天然景观"],
            "description": "3天安庆文化美食之旅"
        },
        {
            "destination": "黄山",
            "duration_days": 4,
            "budget": 8000,
            "preferences": ["自然风景", "登山", "摄影"],
            "description": "4天黄山山水精品游"
        },
        {
            "destination": "西安",
            "duration_days": 5,
            "budget": 10000,
            "preferences": ["历史文化", "博物馆", "美食"],
            "description": "5天西安历史文化深度游"
        }
    ]
    
    return {
        "status": "success",
        "count": len(examples),
        "examples": examples
    }


@app.get("/api/v1/destinations")
async def get_available_destinations():
    """
    获取可用目的地列表
    """
    destinations = {
        "安庆": {
            "region": "安徽",
            "highlights": ["皖江文化", "黄梅戏", "美食"],
            "days_recommended": "3-4"
        },
        "黄山": {
            "region": "安徽",
            "highlights": ["黄山风景", "徽州建筑", "茶文化"],
            "days_recommended": "3-4"
        },
        "西安": {
            "region": "陕西",
            "highlights": ["秦始皇兵马俑", "古城墙", "美食街"],
            "days_recommended": "4-5"
        },
        "成都": {
            "region": "四川",
            "highlights": ["大熊猫", "宽窄巷子", "川菜美食"],
            "days_recommended": "3-4"
        }
    }
    
    return {
        "status": "success",
        "count": len(destinations),
        "destinations": destinations
    }


@app.get("/api/v1/status")
async def get_system_status():
    """
    获取系统状态
    """
    return {
        "status": "operational",
        "version": "1.0.0",
        "agents": {
            "data_collection": "ready",
            "culture_experience": "ready",
            "quality_evaluation": "ready"
        },
        "supported_features": [
            "Cultural experience design",
            "POI recommendation",
            "Itinerary optimization",
            "Quality assessment",
            "Iterative refinement"
        ]
    }


@app.post("/api/v1/feedback")
async def submit_feedback(feedback_data: Dict[str, Any]):
    """
    提交用户反馈（用于持续改进）
    
    反馈包含:
    - session_id: 会话ID
    - rating: 用户评分 (1-5)
    - comments: 用户评论
    - issues: 发现的问题
    """
    
    try:
        # 这里可以保存反馈到数据库
        print(f"📝 收到用户反馈: {feedback_data}")
        
        return {
            "status": "success",
            "message": "感谢您的反馈，我们会持续改进",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 错误处理
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "detail": exc.detail,
            "timestamp": datetime.now().isoformat()
        }
    )


# 启动脚本
if __name__ == "__main__":
    import uvicorn
    
    print("\n" + "="*60)
    print("🚀 启动智能行程规划API服务器")
    print("="*60)
    print("📍 API文档: http://localhost:8000/docs")
    print("📍 API服务: http://localhost:8000")
    print("="*60 + "\n")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
