import os
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings


_BASE_DIR = Path(__file__).resolve().parent.parent


def _load_yaml_config() -> dict:
    config_path = _BASE_DIR / "config.yaml"
    if not config_path.exists():
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    def _resolve_env(value):
        if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            env_key = value[2:-1]
            return os.environ.get(env_key, "")
        if isinstance(value, dict):
            return {k: _resolve_env(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_resolve_env(v) for v in value]
        return value

    return _resolve_env(raw)


class LLMConfig(BaseSettings):
    base_url: str = "https://api.deepseek.com"
    api_key: str = ""
    chat_model: str = "deepseek-v4-flash"
    chat_mini_model: str = "deepseek-v4-flash"
    # Embedding uses separate endpoint (Alibaba Cloud)
    embedding_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-v3"
    embedding_dimensions: int = 2048
    max_tokens: int = 8192
    temperature: float = 0.7

    model_config = {"env_prefix": "LLM_"}


class DatabaseConfig(BaseSettings):
    path: str = "data/diary_agent.db"

    model_config = {"env_prefix": "DATABASE_"}


class TavilyConfig(BaseSettings):
    api_key: str = ""
    search_depth: str = "advanced"
    max_results_per_query: int = 3
    cache_ttl_hours: int = 168
    include_domains: List[str] = Field(
        default_factory=lambda: [
            "baike.baidu.com",
            "movie.douban.com",
            "book.douban.com",
            "zh.wikipedia.org",
        ]
    )

    model_config = {"env_prefix": "TAVILY_"}


class KnowledgeDepthConfig(BaseSettings):
    base_trigger_mentions: int = 3
    detail_discussion_chars: int = 100
    emotional_connection_patterns: List[str] = Field(
        default_factory=lambda: ["让我想起", "跟我一样", "感同身受", "共鸣"]
    )


class DecisionPatternConfig(BaseSettings):
    min_decisions: int = 3
    regret_keywords: List[str] = Field(
        default_factory=lambda: ["后悔", "早该", "不该", "要是", "早知道"]
    )
    major_purchase_threshold_ratio: float = 3.0


class WechatImportConfig(BaseSettings):
    privacy_tier_default: str = "tier1"
    client_preprocessing: bool = True


class MemoryConfig(BaseSettings):
    short_term_max_messages: int = 40
    mid_term_max_sessions: int = 5
    summary_trigger_tokens: int = 8000


class AmapConfig(BaseSettings):
    api_key: str = ""

    model_config = {"env_prefix": "AMAP_"}


class RerankerConfig(BaseSettings):
    enabled: bool = True
    model: str = "BAAI/bge-reranker-v2-m3"
    # 国内镜像，避免 huggingface.co 连接超时
    hf_endpoint: str = "https://hf-mirror.com"
    # 模型缓存目录，避免下载到 C 盘；默认存到项目 data 目录下
    cache_dir: str = ""

    model_config = {"env_prefix": "RERANKER_"}


class Settings(BaseSettings):
    llm: LLMConfig = LLMConfig()
    database: DatabaseConfig = DatabaseConfig()
    tavily: TavilyConfig = TavilyConfig()
    knowledge_depth: KnowledgeDepthConfig = KnowledgeDepthConfig()
    decision_pattern: DecisionPatternConfig = DecisionPatternConfig()
    wechat_import: WechatImportConfig = WechatImportConfig()
    memory: MemoryConfig = MemoryConfig()
    amap: AmapConfig = AmapConfig()
    reranker: RerankerConfig = RerankerConfig()

    model_config = {"env_prefix": "NIANNIAN_"}

    @classmethod
    def from_yaml(cls) -> "Settings":
        data = _load_yaml_config()
        llm_data = data.get("llm", {})
        if "DEEPSEEK_API_KEY" in os.environ:
            llm_data["api_key"] = os.environ["DEEPSEEK_API_KEY"]
        if "DASHSCOPE_API_KEY" in os.environ:
            llm_data["embedding_api_key"] = os.environ["DASHSCOPE_API_KEY"]
        tavily_data = data.get("tavily", {})
        if "TAVILY_API_KEY" in os.environ:
            tavily_data["api_key"] = os.environ["TAVILY_API_KEY"]

        settings = cls(
            llm=LLMConfig(**llm_data),
            database=DatabaseConfig(**data.get("database", {})),
            tavily=TavilyConfig(**tavily_data),
            knowledge_depth=KnowledgeDepthConfig(**data.get("knowledge_depth", {})),
            decision_pattern=DecisionPatternConfig(**data.get("decision_pattern", {})),
            wechat_import=WechatImportConfig(**data.get("wechat_import", {})),
            memory=MemoryConfig(**data.get("memory", {})),
            amap=AmapConfig(**data.get("amap", {})),
            reranker=RerankerConfig(**data.get("reranker", {})),
        )

        # 将 reranker 配置注入环境变量，供 reranker.py 读取
        # 必须在 import FlagEmbedding 之前生效
        os.environ["RERANKER_ENABLED"] = "true" if settings.reranker.enabled else "false"
        os.environ["RERANKER_MODEL"] = settings.reranker.model
        os.environ["RERANKER_HF_ENDPOINT"] = settings.reranker.hf_endpoint
        # 缓存目录：未配置则默认存到项目 data/huggingface_cache 下
        cache_dir = settings.reranker.cache_dir or str(_BASE_DIR / "data" / "huggingface_cache")
        os.environ["RERANKER_CACHE_DIR"] = cache_dir
        # 直接设置 HF_HOME，确保所有 huggingface 相关库都使用此缓存目录
        os.makedirs(cache_dir, exist_ok=True)
        os.environ["HF_HOME"] = cache_dir

        # 检查本地缓存是否已存在：存在则设置 HF_HUB_OFFLINE=1，
        # 避免 transformers/FlagEmbedding 在 import 和运行时联网检查更新
        # 必须在任何 HF 相关库 import 之前设置才有效
        model_name = settings.reranker.model
        if "/" in model_name:
            cache_model_dir = os.path.join(
                cache_dir, "hub", f"models--{model_name.replace('/', '--')}", "snapshots"
            )
            if os.path.isdir(cache_model_dir) and os.listdir(cache_model_dir):
                os.environ["HF_HUB_OFFLINE"] = "1"
                os.environ["TRANSFORMERS_OFFLINE"] = "1"

        return settings

    @property
    def db_path(self) -> Path:
        p = Path(self.database.path)
        if not p.is_absolute():
            return _BASE_DIR / p
        return p


settings = Settings.from_yaml()
