#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
多Agent行程规划系统 - 启动脚本

使用示例:
  # 启动API服务
  python run.py api

  # 运行完整示例
  python run.py demo
  
  # 显示系统信息
  python run.py info
"""

import sys
import asyncio
import argparse
from typing import Optional


def print_header():
    """打印系统标题"""
    print("\n" + "="*60)
    print("🌍 多Agent文化体验行程规划系统 v1.0")
    print("="*60 + "\n")


def cmd_api(port: int = 8000):
    """启动REST API服务"""
    print_header()
    print(f"📍 启动API服务 (端口: {port})")
    print("-"*60)
    
    try:
        import uvicorn
        from api import app
        
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=port,
            log_level="info"
        )
    except ImportError:
        print("❌ 缺少依赖: fastapi, uvicorn")
        print("   请运行: pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        sys.exit(1)


async def cmd_demo():
    """运行完整示例"""
    print_header()
    print("🎬 运行完整示例 - 安庆3天文化美食之旅")
    print("-"*60 + "\n")
    
    try:
        from multi_agent_orchestrator import TravelPlanningOrchestrator
        from core.planning_context import UserIntent
        
        # 创建编排器
        orchestrator = TravelPlanningOrchestrator()
        
        # 创建用户意图
        user_intent = UserIntent(
            destination="安庆",
            duration_days=3,
            budget=5000,
            preferences=["文化遗产", "美食", "天然景观"]
        )
        
        # 执行编排
        response = await orchestrator.orchestrate(user_intent)
        
        # 显示结果
        print("\n✨ 规划完成！")
        print(f"  • 状态: {response['status']}")
        print(f"  • 质量评分: {response['quality_score']:.2f}/1.0")
        print(f"  • 迭代次数: {response['iterations']}")
        
        if response["status"] == "success":
            print(f"  • UI模块数: {len(response.get('ui_modules', {}).get('modules', {}))}")
        
        # 保存会话
        if response["status"] == "success":
            orchestrator.save_session(
                user_id="demo_user",
                session_name="安庆3天文化美食之旅",
                response=response
            )
        
        return response
        
    except Exception as e:
        print(f"❌ 示例运行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def cmd_info():
    """显示系统信息"""
    print_header()
    
    print("📊 系统信息")
    print("-"*60)
    print("✓ 版本: 1.0.0")
    print("✓ 框架: LangChain 0.1.0+")
    print("✓ Python: 3.8+")
    print("✓ 主要依赖:")
    print("    • fastapi - REST API框架")
    print("    • langchain - LLM编排框架")
    print("    • pydantic - 数据验证")
    
    print("\n🤖 Agent组件")
    print("-"*60)
    print("✓ DataCollectionAgent - 数据采集")
    print("✓ CultureAgent - 文化体验设计")
    print("✓ QualityEvalAgent - 质量评估")
    
    print("\n📂 核心模块")
    print("-"*60)
    print("✓ core/ - 框架基础")
    print("✓ agents/ - Agent实现")
    print("✓ knowledge_base/ - 知识库")
    print("✓ ui_modules.py - 前端模块")
    
    print("\n🔌 API端点")
    print("-"*60)
    print("✓ POST /api/v1/plan - 创建行程规划")
    print("✓ GET /api/v1/examples - 获取示例")
    print("✓ GET /api/v1/destinations - 目的地列表")
    print("✓ GET /api/v1/status - 系统状态")
    print("✓ POST /api/v1/feedback - 提交反馈")
    
    print("\n📖 快速开始")
    print("-"*60)
    print("1. 安装依赖:")
    print("   pip install -r requirements.txt")
    print("2. 启动API服务:")
    print("   python run.py api")
    print("3. 访问API文档:")
    print("   http://localhost:8000/docs")
    print("4. 运行示例:")
    print("   python run.py demo")
    
    print("\n💡 更多信息请查看 QUICKSTART.md")
    print("="*60 + "\n")


def cmd_test():
    """运行测试"""
    print_header()
    print("🧪 运行基础测试")
    print("-"*60 + "\n")
    
    tests = []
    
    # 测试1: 导入模块
    try:
        from core.planning_context import PlanningContext, UserIntent
        from core.base_agent import TravelPlanningAgent
        from agents.data_collection_agent import DataCollectionAgent
        from agents.culture_agent import CultureAgent
        from agents.quality_eval_agent import QualityEvalAgent
        tests.append(("模块导入", True))
    except Exception as e:
        tests.append(("模块导入", False, str(e)))
    
    # 测试2: 创建PlanningContext
    try:
        user_intent = UserIntent(destination="测试", duration_days=1, budget=1000)
        context = PlanningContext(user_intent=user_intent)
        tests.append(("创建PlanningContext", True))
    except Exception as e:
        tests.append(("创建PlanningContext", False, str(e)))
    
    # 测试3: 创建Agent
    try:
        agent = DataCollectionAgent()
        tests.append(("实例化DataCollectionAgent", True))
    except Exception as e:
        tests.append(("实例化DataCollectionAgent", False, str(e)))
    
    # 显示结果
    passed = sum(1 for t in tests if t[1])
    total = len(tests)
    
    print(f"测试结果: {passed}/{total} 通过\n")
    
    for test in tests:
        name = test[0]
        status = "✓" if test[1] else "✗"
        result = "通过" if test[1] else f"失败: {test[2] if len(test) > 2 else ''}"
        print(f"  {status} {name}: {result}")
    
    print("\n" + "="*60 + "\n")
    
    return 0 if passed == total else 1


def main():
    """主入口点"""
    parser = argparse.ArgumentParser(
        description="多Agent行程规划系统启动脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python run.py api              # 启动API服务 (端口8000)
  python run.py api --port 8001  # 启动API服务 (自定义端口)
  python run.py demo             # 运行完整示例
  python run.py test             # 运行测试
  python run.py info             # 显示系统信息
        """
    )
    
    parser.add_argument(
        "command",
        choices=["api", "demo", "test", "info"],
        help="要执行的命令"
    )
    
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="API服务端口 (默认: 8000)"
    )
    
    args = parser.parse_args()
    
    if args.command == "api":
        cmd_api(port=args.port)
    elif args.command == "demo":
        asyncio.run(cmd_demo())
    elif args.command == "test":
        sys.exit(cmd_test())
    elif args.command == "info":
        cmd_info()


if __name__ == "__main__":
    main()
