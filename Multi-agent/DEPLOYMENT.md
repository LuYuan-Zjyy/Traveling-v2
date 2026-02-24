# 多Agent行程规划系统 - 部署和使用指南

## 🎯 系统概述

这是一个基于LangChain的多Agent行程规划系统，实现了完整的AI驱动的文化体验旅行规划功能。

### 核心优势
- **智能协作**: 多个专业化Agent协同工作
- **迭代优化**: 最多5轮自动优化
- **质量保证**: 自动评分和改进建议
- **模块化设计**: 7个独立的前端UI模块
- **知识积累**: 自动学习和知识库系统

## 📁 完整的项目结构

```
Multi-agent/
├── core/                          # ✓ 核心框架 (100%)
│   ├── __init__.py
│   ├── planning_context.py        # 全局状态和数据共享
│   ├── agent_state.py            # Agent生命周期状态机
│   ├── agent_memory.py           # 内存和学习系统
│   └── base_agent.py             # Agent基类
│
├── agents/                        # ✓ 具体Agent (60% - 3/5)
│   ├── __init__.py
│   ├── data_collection_agent.py  # ✓ 数据采集 (完成)
│   ├── culture_agent.py          # ✓ 文化体验设计 (完成)
│   └── quality_eval_agent.py     # ✓ 质量评估 (完成)
│
├── knowledge_base/               # ✓ 知识库系统 (100%)
│   ├── __init__.py
│   └── kb_manager.py            # 自动学习和知识持久化
│
├── orchestrator.py              # ✓ 主协调层 (100%)
│                                 # - Agent调度
│                                 # - 迭代反馈循环
│                                 # - 结果融合
│
├── api.py                       # ✓ REST API (100%)
│                                # - HTTP接口
│                                # - 数据验证
│                                # - 错误处理
│
├── ui_modules.py                # ✓ 前端模块 (100%)
│                                # - 7个UI组件
│                                # - 响应转换工厂
│
├── run.py                       # ✓ 启动脚本 (100%)
│                                # - 4个命令: api, demo, test, info
│
├── __init__.py                  # 模块入口
├── requirements.txt             # Python依赖
├── README.md                    # 项目说明
├── QUICKSTART.md                # 快速开始
└── IMPLEMENTATION_GUIDE.md      # 详细指南
```

## 🚀 快速启动

### 1. 安装依赖
```bash
cd Multi-agent
pip install -r requirements.txt
```

### 2. 启动API服务
```bash
python run.py api
```

服务运行在 `http://localhost:8000`

### 3. 访问文档
- **自动API文档**: http://localhost:8000/docs
- **快速开始指南**: QUICKSTART.md
- **实现细节**: IMPLEMENTATION_GUIDE.md

## 🎯 使用示例

### 方式1: 通过REST API

```bash
curl -X POST "http://localhost:8000/api/v1/plan" \
  -H "Content-Type: application/json" \
  -d '{
    "destination": "安庆",
    "duration_days": 3,
    "budget": 5000,
    "preferences": ["文化遗产", "美食", "天然景观"]
  }'
```

### 方式2: 运行完整示例

```bash
python run.py demo
```

### 方式3: 直接在Python中使用

```python
import asyncio
from core.planning_context import UserIntent
from orchestrator import TravelPlanningOrchestrator

async def main():
    # 创建编排器
    orchestrator = TravelPlanningOrchestrator()
    
    # 定义用户需求
    user_intent = UserIntent(
        destination="安庆",
        duration_days=3,
        budget=5000,
        preferences=["文化遗产", "美食"]
    )
    
    # 执行规划
    response = await orchestrator.orchestrate(user_intent)
    
    print(f"规划状态: {response['status']}")
    print(f"质量评分: {response['quality_score']}")
    print(f"迭代次数: {response['iterations']}")

asyncio.run(main())
```

## 🔄 执行流程

```
┌─────────────────────┐
│   用户请求         │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 编排器初始化         │
└──────────┬──────────┘
           │
           ▼
     ┌─────────────────────────────┐
     │ 第1轮迭代 (必执行)           │
     ├─────────────────────────────┤
     │ 1. 数据采集Agent             │
     │    - 获取POI数据            │
     │    - 获取天气信息            │
     │    - 计算路线               │
     │                             │
     │ 2. 文化体验Agent             │
     │    - 识别文化主题            │
     │    - 筛选文化POI            │
     │    - 生成故事背景            │
     │    - 推荐特色活动            │
     │                             │
     │ 3. 质量评估Agent             │
     │    - 评分 (0-1)             │
     │    - 生成反馈               │
     └─────────────┬───────────────┘
                   │
           评分 ≥ 0.75? NO
                   │
                   ▼
        ┌────────────────────┐
        │ 后续迭代(3-5轮)    │
        │ 根据反馈改进       │
        └────────┬───────────┘
                 │
           评分 ≥ 0.75? YES
                 │
                 ▼
      ┌──────────────────────┐
      │ 融合所有Agent输出    │
      └──────────┬───────────┘
                 │
                 ▼
      ┌──────────────────────┐
      │ 转换为UI模块         │
      └──────────┬───────────┘
                 │
                 ▼
      ┌──────────────────────┐
      │ 返回最终规划方案     │
      └──────────────────────┘
```

## 📊 API文档

### 主要端点

| 方法 | 端点 | 描述 |
|-----|------|------|
| POST | `/api/v1/plan` | 创建行程规划 |
| GET | `/api/v1/examples` | 获取示例 |
| GET | `/api/v1/destinations` | 获取目的地 |
| GET | `/api/v1/status` | 系统状态 |
| POST | `/api/v1/feedback` | 提交反馈 |

### 请求示例

```json
{
  "destination": "安庆",
  "duration_days": 3,
  "budget": 5000,
  "preferences": ["文化遗产", "美食", "天然景观"],
  "trip_type": "cultural"
}
```

### 响应示例

```json
{
  "status": "success",
  "final_plan": {...},
  "ui_modules": {
    "modules": {
      "itinerary": {...},
      "culture": {...},
      "budget": {...},
      "navigation": {...},
      "knowledge": {...},
      "execution": {...},
      "contingency": {...}
    }
  },
  "quality_score": 0.82,
  "iterations": 2,
  "suggestions": [
    "建议增加更多特色文化体验内容",
    "预算可能略有超支"
  ],
  "session_id": "user_123_20231201_120000"
}
```

## 🤖 Agent说明

### 1. DataCollectionAgent (数据采集)
- **职责**: 从外部API采集行程相关数据
- **输出**: POI列表、天气数据、路线信息
- **关键方法**: 
  - `_geocode()` - 地址编码
  - `_search_pois()` - POI搜索
  - `_get_weather()` - 天气获取
  - `_calculate_routes()` - 路线计算

### 2. CultureAgent (文化体验)
- **职责**: 设计深度的文化体验
- **输出**: 文化主题、筛选POI、故事背景、活动推荐
- **核心差异**: 将旅行转化为文化学习体验
- **关键方法**:
  - `_identify_cultural_theme()` - 主题识别
  - `_filter_cultural_pois()` - POI筛选和排序
  - `_generate_cultural_background()` - 故事生成
  - `_recommend_activities()` - 活动推荐

### 3. QualityEvalAgent (质量评估)
- **职责**: 评估规划方案质量
- **输出**: 综合评分、改进建议、Agent反馈
- **评估维度**:
  - 完整性 (25%)
  - 可行性 (25%)
  - 用户匹配度 (25%)
  - 体验质量 (25%)

## 📈 质量评分规则

```
综合评分 = ∑ (各维度评分 × 权重)

⭐⭐⭐⭐⭐ 优秀     ≥ 0.90 (完全满足要求)
⭐⭐⭐⭐   好      ≥ 0.75 (大体满足，可接受)
⭐⭐⭐     一般     ≥ 0.60 (需要改进)
⭐⭐      差      < 0.60 (需要重新规划)
```

## 🔧 配置和定制

### 修改质量阈值
在 `orchestrator.py` 中修改:
```python
QUALITY_THRESHOLD = 0.75  # 改为你需要的值
```

### 修改最大迭代次数
```python
MAX_ITERATIONS = 5  # 改为你需要的值
```

### 添加新的API端点
在 `api.py` 中添加新的路由:
```python
@app.get("/api/v1/your_endpoint")
async def your_endpoint():
    return {...}
```

## 🧪 测试系统

```bash
# 运行基础测试
python run.py test

# 获取系统信息
python run.py info
```

## 📦 依赖管理

核心依赖:
- **fastapi** - REST API框架
- **langchain** - LLM编排
- **pydantic** - 数据验证
- **sqlalchemy** - 数据库ORM
- **aiohttp** - 异步HTTP

安装/更新:
```bash
pip install -r requirements.txt
```

## 🐛 常见问题

### Q: 如何集成真实的LLM API?
A: 在 `agents/` 中修改相应的Agent，将mock调用替换为真实API调用。

### Q: 如何添加新的数据源?
A: 扩展 `DataCollectionAgent._search_pois()` 方法。

### Q: 如何持久化规划历史?
A: 实现 `orchestrator.save_session()` 中的数据库逻辑。

### Q: 如何实现多语言支持?
A: 在 `CultureAgent` 中添加语言参数和翻译逻辑。

## 📚 进阶主题

### 实现自定义Agent

1. 继承 `TravelPlanningAgent`:
```python
class MyCustomAgent(TravelPlanningAgent):
    def _validate_input(self, context):
        # 验证逻辑
        return True
    
    def _execute_core(self, context):
        # 核心业务逻辑
        return {"result": "data"}
```

2. 在编排器中添加:
```python
self.my_agent = MyCustomAgent()
```

### 知识库系统

自动学习优秀规划:
```python
# 会自动调用
self.knowledge_base.learn_from_agent_output(context)
```

## 🚢 部署

### Docker部署 (示例)

```dockerfile
FROM python:3.9

WORKDIR /app
COPY . .

RUN pip install -r Multi-agent/requirements.txt

EXPOSE 8000

CMD ["python", "Multi-agent/run.py", "api"]
```

### 生产环境建议
- 使用 `uvicorn` + `gunicorn` 处理多进程
- 配置 `nginx` 反向代理
- 使用 `Redis` 缓存API响应
- 定期备份知识库

## 📞 支持和反馈

- 查看 `QUICKSTART.md` 了解快速开始
- 查看 `IMPLEMENTATION_GUIDE.md` 了解实现细节
- 查看 API文档 (http://localhost:8000/docs)

## 📝 许可证

MIT License

---

**上次更新**: 2024年
**版本**: 1.0.0
