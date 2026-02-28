"""Agent configuration loader.

Loads agent personas and settings from agent_config.yaml.
Provides cached LLM factory to avoid recreating identical instances.
"""

from __future__ import annotations

import os
import yaml
from typing import Dict, Any, Optional, Tuple
from pathlib import Path
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI

from app.config import settings


class AgentConfig(BaseModel):
    """Configuration for a single agent persona."""

    role: str = Field(..., description="Agent role name")
    name: str = Field(..., description="Agent display name")
    model: str = Field(..., description="LLM model to use")
    temperature: float = Field(..., description="Temperature for LLM generation")
    system_prompt: str = Field(..., description="System prompt for the agent")


class AgentsConfig(BaseModel):
    """Root configuration containing all agent personas."""

    ba: AgentConfig
    dev: AgentConfig
    tester: AgentConfig
    manager: Optional[AgentConfig] = None


def load_agent_config(config_path: Optional[str] = None) -> AgentsConfig:
    """
    Load agent configuration from YAML file.

    Args:
        config_path: Path to the YAML config file. If None, uses default path.

    Returns:
        AgentsConfig object with all agent configurations
    """
    if config_path is None:
        # Default to project root
        project_root = Path(__file__).parent.parent.parent
        resolved_path = project_root / "agent_config.yaml"
    else:
        resolved_path = Path(config_path)

    if not resolved_path.exists():
        raise FileNotFoundError(f"Agent config file not found: {resolved_path}")

    with open(resolved_path, "r", encoding="utf-8") as f:
        config_data = yaml.safe_load(f)

    return AgentsConfig(**config_data)


def get_agent_config(agent_name: str, config_path: Optional[str] = None) -> AgentConfig:
    """
    Get configuration for a specific agent.

    Uses the cached config via get_config() for default path,
    falls back to load_agent_config() only when a custom path is provided.

    Args:
        agent_name: Name of the agent (ba, dev, tester, manager)
        config_path: Optional path to config file

    Returns:
        AgentConfig for the specified agent
    """
    all_configs = load_agent_config(config_path) if config_path else get_config()

    agent_map = {
        "ba": all_configs.ba,
        "dev": all_configs.dev,
        "tester": all_configs.tester,
        "manager": all_configs.manager,
    }

    agent_key = agent_name.lower()
    if agent_key in agent_map and agent_map[agent_key] is not None:
        return agent_map[agent_key]

    available = [k for k, v in agent_map.items() if v is not None]
    raise ValueError(
        f"Unknown or unavailable agent: {agent_name}. Available: {available}"
    )


# Singleton instance for caching
_config_cache: Optional[AgentsConfig] = None


def get_config() -> AgentsConfig:
    """
    Get cached agent configuration.

    Returns:
        AgentsConfig object (cached after first call)
    """
    global _config_cache
    if _config_cache is None:
        _config_cache = load_agent_config()
    return _config_cache


# ============================================================================
# LLM Instance Cache
# ============================================================================

# Cache key: (model, temperature, base_url) -> ChatOpenAI instance
_llm_cache: Dict[Tuple[str, float, str], ChatOpenAI] = {}


def get_llm(
    model: Optional[str] = None,
    temperature: float = 0.7,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> ChatOpenAI:
    """
    Get a cached ChatOpenAI instance.

    Returns an existing instance if one with the same (model, temperature, base_url)
    already exists, otherwise creates and caches a new one.

    Args:
        model: Model name (defaults to settings.OPENAI_MODEL)
        temperature: Temperature for generation
        base_url: API base URL (defaults to settings.OPENAI_API_BASE)
        api_key: API key (defaults to settings.OPENROUTER_API_KEY)

    Returns:
        Cached ChatOpenAI instance
    """
    resolved_model = model or settings.OPENAI_MODEL
    resolved_base_url = base_url or settings.OPENAI_API_BASE
    resolved_api_key = api_key or settings.OPENROUTER_API_KEY

    cache_key = (resolved_model, temperature, resolved_base_url)

    if cache_key not in _llm_cache:
        _llm_cache[cache_key] = ChatOpenAI(
            model=resolved_model,
            api_key=resolved_api_key,
            base_url=resolved_base_url,
            temperature=temperature,
        )

    return _llm_cache[cache_key]


def get_llm_for_agent(agent_config: AgentConfig) -> ChatOpenAI:
    """
    Get a cached ChatOpenAI instance configured for a specific agent.

    Convenience wrapper around get_llm() that extracts parameters
    from an AgentConfig object.

    Args:
        agent_config: Agent configuration with model and temperature

    Returns:
        Cached ChatOpenAI instance
    """
    return get_llm(
        model=agent_config.model,
        temperature=agent_config.temperature,
    )
