"""
配置管理模块
加载 .env 文件中的 API Key 和其他配置项
"""
import os
from dataclasses import dataclass, field
from pathlib import Path

# 尝试加载 .env
try:
    from dotenv import load_dotenv
    
    # 计算项目根目录: config.py 在 orchestrator/ 目录下, 根目录是 parent.parent
    config_file = Path(__file__).resolve()  # 获取config.py的绝对路径
    project_root = config_file.parent.parent  # 项目根目录
    root_env = project_root / ".env"  # 项目根目录的.env
    local_env = config_file.parent / ".env"  # orchestrator/.env
    
    # 优先加载根目录的.env (所有模块共享), 其次从 orchestrator/.env (向后兼容)
    # 使用 override=True 确保环境变量能被正确覆盖
    if root_env.exists() and root_env.stat().st_size > 0:
        load_dotenv(root_env, override=True)
    elif local_env.exists() and local_env.stat().st_size > 0:
        load_dotenv(local_env, override=True)
    
except ImportError:
    pass  # 没装 python-dotenv 就跳过, 依赖环境变量
except Exception:
    # 加载失败不影响运行, 依赖环境变量
    pass


@dataclass
class DeepSeekConfig:
    """DeepSeek LLM 配置"""
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    temperature: float = 0.3          # 意图识别用低温度
    planning_temperature: float = 0.7  # 规划生成用稍高温度
    max_tokens: int = 4096

    def __post_init__(self):
        self.api_key = self.api_key or os.getenv("DEEPSEEK_API_KEY", "")
        self.base_url = self.base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.model = self.model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


@dataclass
class AmapConfig:
    """高德地图 配置"""
    api_key: str = ""
    base_url: str = "https://restapi.amap.com"

    def __post_init__(self):
        self.api_key = self.api_key or os.getenv("AMAP_API_KEY", "")


@dataclass
class AgentConfig:
    """主控Agent总配置"""
    deepseek: DeepSeekConfig = field(default_factory=DeepSeekConfig)
    amap: AmapConfig = field(default_factory=AmapConfig)

    def validate(self) -> list[str]:
        """校验必填Key, 返回缺失项列表"""
        missing = []
        if not self.deepseek.api_key:
            missing.append("DEEPSEEK_API_KEY")
        if not self.amap.api_key:
            missing.append("AMAP_API_KEY")
        return missing


def load_config(**overrides) -> AgentConfig:
    """加载配置, 支持参数覆盖"""
    ds_overrides = {k.replace("deepseek_", ""): v for k, v in overrides.items() if k.startswith("deepseek_")}
    amap_overrides = {k.replace("amap_", ""): v for k, v in overrides.items() if k.startswith("amap_")}

    config = AgentConfig(
        deepseek=DeepSeekConfig(**ds_overrides),
        amap=AmapConfig(**amap_overrides),
    )

    missing = config.validate()
    if missing:
        print(f"  [WARN] Missing API Key: {', '.join(missing)}")
        print(f"   请在项目根目录的 .env 文件或环境变量中配置")

    return config

