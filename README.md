# Traveling-v2: 智能旅游规划系统

基于 DeepSeek LLM 和高德地图 API 的 AI 智能旅行规划系统，提供行程规划、地图导航、景点推荐等功能。

## ✨ 核心功能

- **AI 行程规划** - 使用 DeepSeek LLM 生成详细的日程规划
- **地图导航** - 集成高德地图，显示景点位置、路线规划、距离/耗时估算
- **智能推荐** - 自动搜索景点、餐厅、酒店，基于用户偏好推荐
- **天气预报** - 实时查询目的地天气信息
- **可视化界面** - 基于 Leaflet 的交互式地图，直观展示规划结果

## 🚀 快速开始

### 前置要求

- Python 3.8+
- 高德地图 API Key（需要开通"Web 服务"）
- DeepSeek API Key

### 配置环境

1. **编辑 `.env` 文件**
```
DEEPSEEK_API_KEY=sk-xxxxxx
AMAP_API_KEY=xxxxxx
```

2. **安装依赖**
```bash
cd MCP_map
pip install -r requirements.txt
```

### 运行应用

```bash
# 启动 Flask 应用
cd MCP_map
python -c "from app import app; app.run(debug=False, port=5000)"

# 然后打开浏览器访问
http://localhost:5000
```

## 📁 项目结构

```
Traveling-v2/
├── .env                    # 环境变量配置（填入密钥）
├── README.md               # 本文件
│
├── MCP_map/                # 🌐 Web 应用（主要功能）
│   ├── app.py              # Flask 后端
│   ├── requirements.txt
│   ├── static/
│   │   ├── app.js          # Leaflet 地图脚本
│   │   └── style.css
│   └── templates/
│       └── index.html      # Web UI
│
├── orchestrator/           # 🤖 主控 Agent（核心规划）
│   ├── orchestrator.py     # 主控 Agent
│   ├── main.py             # 命令行入口
│   ├── config.py           # 配置管理
│   ├── amap_tools.py       # 高德 API 工具
│   ├── deepseek_client.py  # DeepSeek 客户端
│   ├── prompts.py          # LLM 提示词
│   ├── result_store.py     # 结果存储
│   └── requirements.txt
│
├── Multi-agent/            # 📂 垂直领域 Agent
│   ├── culture/            # 文化推荐
│   └── Route/              # 路由优化
│
└── Anqing_Data/            # 📊 示例数据
```

## 💡 使用示例

### Web 界面（推荐）

1. 打开 http://localhost:5000
2. 输入旅行需求：`安庆市 3 天，预算 2000 元，喜欢文化和美食`
3. 点击 **"AI 规划"**
4. 查看规划结果和地图

### 命令行

```bash
cd orchestrator
python main.py
# 输入：西安 3 天旅游，预算 5000 元
```

## 🔧 API 配置

### 高德地图

访问 [高德开放平台](https://console.amap.com/dev/key/app) 申请 Web Key

### DeepSeek

访问 [DeepSeek](https://www.deepseek.com) 获取 API Key

## 📊 工作流程

```
用户输入
  ↓
[意图识别] - 解析旅行需求
  ↓
[任务分解] - 调用高德 API 收集数据
  ↓
[规划生成] - DeepSeek 生成行程
  ↓
[地图可视化] - 前端显示结果
```

## 🐛 故障排查

### 地图无法显示路线

1. 按 F12 打开浏览器控制台，检查是否有错误
2. 验证 `.env` 中 `AMAP_API_KEY` 是否正确
3. 查看后端日志中 `[ROUTE DEBUG]` 的输出

### 规划失败

- 检查 DeepSeek API 连接
- 确保 API 密钥有效且有余额
- 查看错误日志

## 📝 输出

规划结果保存在 `orchestrator/outputs/sessions/` 中

## 🙏 致谢

- [高德开放平台](https://amap.com)
- [DeepSeek](https://www.deepseek.com)
- [Leaflet.js](https://leafletjs.com)

---

**需要帮助？** 查看项目源代码或提交 Issue

