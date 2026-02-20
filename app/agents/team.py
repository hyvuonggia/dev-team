"""
LangGraph Team Graph Definition

This module builds and compiles the StateGraph for the multi-agent team.
It defines the graph topology with:
- Manager (Supervisor) node for routing decisions
- Worker nodes (BA, Dev, Tester) that perform work
- Conditional edges for dynamic routing
- Standard edges for returning to Manager
"""

from __future__ import annotations

import logging

from langgraph.graph import StateGraph, START, END

from app.models.state import TeamState
from app.agents.manager import manager_node
from app.agents.workers import ba_node, dev_node, tester_node

logger = logging.getLogger(__name__)


def build_team_graph() -> StateGraph:
    """
    Build and compile the LangGraph StateGraph for the AI Dev Team.

    Graph Topology:
    ```
    START -> Manager -> [conditional routing]
                          |
            .-------------+------------.
            |             |            |
           BA --> Manager  Dev --> Manager  Tester --> Manager
            |                            |
            '-----------------+----------'
                              |
                             END
    ```

    Key Features:
    - Manager node uses LLM to dynamically decide next agent
    - Worker nodes always report back to Manager
    - Supports iteration (e.g., Tester finds bug -> Manager routes to Dev)
    - Loop prevention via max_iterations in state

    Returns:
        Compiled StateGraph ready for execution
    """
    # Initialize the state graph
    workflow = StateGraph(TeamState)

    # ==========================================================================
    # Add Nodes
    # ==========================================================================

    # Manager (Supervisor) node - makes routing decisions
    workflow.add_node("manager", manager_node)

    # Worker nodes - perform actual work
    workflow.add_node("ba", ba_node)
    workflow.add_node("dev", dev_node)
    workflow.add_node("tester", tester_node)

    # ==========================================================================
    # Define Standard Edges
    # ==========================================================================

    # Workers ALWAYS report back to the Manager after completing their work
    # This creates the hub-and-spoke pattern
    workflow.add_edge("ba", "manager")
    workflow.add_edge("dev", "manager")
    workflow.add_edge("tester", "manager")

    # ==========================================================================
    # Define Conditional Edges (The Routing Logic)
    # ==========================================================================

    def route_from_manager(state: TeamState) -> str:
        """
        Routing function that reads the Manager's decision.

        Args:
            state: Current TeamState containing next_agent decision

        Returns:
            String indicating next node to route to
        """
        return state.get("next_agent", "FINISH")

    # The Manager uses a conditional edge to route to the appropriate worker
    # or finish the workflow
    workflow.add_conditional_edges(
        "manager",
        route_from_manager,
        {
            "ba": "ba",
            "dev": "dev",
            "tester": "tester",
            "FINISH": END,
        },
    )

    # ==========================================================================
    # Set Entry Point
    # ==========================================================================

    # All workflows start at the Manager
    workflow.add_edge(START, "manager")

    # ==========================================================================
    # Compile the Graph
    # ==========================================================================

    # Compile into an executable application
    # This creates the runnable graph that can be invoked
    compiled_graph = workflow.compile()

    return compiled_graph


# ============================================================================
# Convenience Functions
# ============================================================================


async def run_team_workflow(
    user_request: str,
    project_id: str | None = None,
    max_iterations: int = 10,
) -> TeamState:
    """
    Convenience function to run the team workflow from start to finish.

    Args:
        user_request: The user's request text
        project_id: Optional project ID for workspace isolation
        max_iterations: Maximum iterations before forcing completion

    Returns:
        Final TeamState after workflow completion
    """
    from langchain_core.messages import HumanMessage

    logger.info("=" * 70)
    logger.info("🚀 TEAM WORKFLOW: Starting execution")
    logger.info(f"   Request: {user_request[:60]}...")
    logger.info(f"   Project: {project_id or 'default'}")
    logger.info(f"   Max Iterations: {max_iterations}")
    logger.info("=" * 70)

    # Build the graph
    graph = build_team_graph()
    logger.info("📊 Graph compiled successfully")

    # Initialize state
    initial_state: TeamState = {
        "user_request": user_request,
        "project_id": project_id,
        "messages": [HumanMessage(content=user_request)],
        "next_agent": "manager",
        "task": None,
        "ba_result": None,
        "dev_result": None,
        "tester_result": None,
        "artifacts": [],
        "status": "pending",
        "clarifying_questions": [],
        "error_message": None,
        "iteration_count": 0,
        "max_iterations": max_iterations,
    }
    logger.info("📝 Initial state created")

    # Run the workflow
    logger.info("⚡ Executing workflow...")
    logger.info("")

    final_state = await graph.ainvoke(initial_state)

    logger.info("")
    logger.info("=" * 70)
    logger.info("✅ WORKFLOW COMPLETE")
    logger.info(f"   Final Status: {final_state.get('status', 'unknown')}")
    logger.info(f"   Total Iterations: {final_state.get('iteration_count', 0)}")
    logger.info(f"   Artifacts Created: {len(final_state.get('artifacts', []))}")
    logger.info(f"   BA Complete: {'✓' if final_state.get('ba_result') else '✗'}")
    logger.info(f"   Dev Complete: {'✓' if final_state.get('dev_result') else '✗'}")
    logger.info(
        f"   Tester Complete: {'✓' if final_state.get('tester_result') else '✗'}"
    )

    if final_state.get("error_message"):
        logger.error(f"   Error: {final_state['error_message']}")

    logger.info("=" * 70)

    return final_state


def get_graph_visualization() -> str:
    """
    Get a text-based visualization of the graph structure.

    Returns:
        ASCII art representation of the graph
    """
    return """
    LangGraph AI Dev Team Structure
    =================================

    START
      |
      v
    +-----------+
    |  Manager  |<-----------------------------+
    | (Router)  |                              |
    +-----+-----+                              |
          |                                    |
          | Conditional Edges                  |
          | (LLM decides next_agent)           |
          v                                    |
    +-----+-----+     +---------+     +--------+-------+
    |     |     |     |         |     |                |
    v     v     v     v         v     v                |/  (always returns)
   +---+ +---+ +---+ +---+   +---+ +---+
   |BA | |Dev| |Tester| |END|
   +-+-+ +-+-+ +-+-+-+ +---+
     |     |     |
     +-----+-----+
           |
           v
    +-----------+
    |  Manager  |
    +-----------+

    Flow:
    1. START -> Manager
    2. Manager LLM decides next_agent (ba/dev/tester/FINISH)
    3. If worker: Execute worker -> Return to Manager
    4. If FINISH: End workflow
    5. Manager reviews results and decides again (loop possible)
    """
