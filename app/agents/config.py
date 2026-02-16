"""Agent configuration loader.

Loads agent personas and settings from agent_config.yaml.
"""

from __future__ import annotations

import os
import yaml
from typing import Dict, Any, Optional
from pathlib import Path
from pydantic import BaseModel, Field


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
        config_path = project_root / "agent_config.yaml"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Agent config file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config_data = yaml.safe_load(f)

    return AgentsConfig(**config_data)


def get_agent_config(agent_name: str, config_path: Optional[str] = None) -> AgentConfig:
    """
    Get configuration for a specific agent.

    Args:
        agent_name: Name of the agent (ba, dev, tester, manager)
        config_path: Optional path to config file

    Returns:
        AgentConfig for the specified agent
    """
    all_configs = load_agent_config(config_path)

    agent_map = {
        "ba": all_configs.ba,
        "dev": all_configs.dev,
        "tester": all_configs.tester,
    }

    if agent_name.lower() in agent_map:
        return agent_map[agent_name.lower()]

    if agent_name.lower() == "manager" and all_configs.manager:
        return all_configs.manager

    raise ValueError(
        f"Unknown agent: {agent_name}. Available: {list(agent_map.keys())}"
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
