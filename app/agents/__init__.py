"""Agents package for AI Dev Team."""

from app.agents.ba import (
    canonicalize_whitespace,
    validate_request,
    run_ba_analysis,
)

from app.agents.developer import (
    generate_implementation,
    run_static_checks,
    format_user_stories,
    format_context,
)

from app.agents.tester import (
    review_and_generate_tests,
    review_project,
    read_source_files,
    analyze_code_structure,
)

# LangGraph Architecture - New Supervisor Pattern
from app.agents.manager import (
    manager_node,
    route_request,
    RouteDecision,
)

from app.agents.workers import (
    ba_node,
    dev_node,
    tester_node,
    create_task_from_state,
)

from app.agents.team import (
    build_team_graph,
    run_team_workflow,
    get_graph_visualization,
)

from app.agents.config import (
    AgentConfig,
    AgentsConfig,
    load_agent_config,
    get_agent_config,
    get_config,
)

__all__ = [
    # BA Agent exports
    "canonicalize_whitespace",
    "validate_request",
    "run_ba_analysis",
    # Dev Agent exports
    "generate_implementation",
    "run_static_checks",
    "format_user_stories",
    "format_context",
    # Tester Agent exports
    "review_and_generate_tests",
    "review_project",
    "read_source_files",
    "analyze_code_structure",
    # LangGraph Manager (Supervisor) exports
    "manager_node",
    "route_request",
    "RouteDecision",
    # LangGraph Worker exports
    "ba_node",
    "dev_node",
    "tester_node",
    "create_task_from_state",
    # LangGraph Team exports
    "build_team_graph",
    "run_team_workflow",
    "get_graph_visualization",
    # Config exports
    "AgentConfig",
    "AgentsConfig",
    "load_agent_config",
    "get_agent_config",
    "get_config",
]
