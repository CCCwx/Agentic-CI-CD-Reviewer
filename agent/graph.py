import logging

from langgraph.graph import END, START, StateGraph

from agent.nodes import committer_agent, patcher_agent, reviewer_agent
from agent.state import GraphState
from github_api.client import GitHubClient

logger = logging.getLogger(__name__)


def _route_after_review(state: GraphState) -> str:
    review_result = state.get("review_result")
    if review_result and review_result.has_bugs:
        return "patcher"
    return "committer"


def build_graph():
    workflow = StateGraph(GraphState)
    workflow.add_node("reviewer", reviewer_agent)
    workflow.add_node("patcher", patcher_agent)
    workflow.add_node("committer", committer_agent)

    workflow.add_edge(START, "reviewer")
    workflow.add_conditional_edges(
        "reviewer",
        _route_after_review,
        {
            "patcher": "patcher",
            "committer": "committer",
        },
    )
    workflow.add_edge("patcher", "committer")
    workflow.add_edge("committer", END)
    return workflow.compile()


GRAPH = build_graph()


async def run_pr_review(
    repo_name: str,
    pr_number: int,
    pr_diff: str,
    github_client: GitHubClient | None = None,
) -> GraphState:
    logger.info("Running review graph for %s#%s", repo_name, pr_number)
    initial_state: GraphState = {
        "repo_name": repo_name,
        "pr_number": pr_number,
        "pr_diff": pr_diff,
        "review_result": None,
        "patch_code": None,
        "final_comment": None,
    }
    if github_client is not None:
        initial_state["github_client"] = github_client

    result = await GRAPH.ainvoke(initial_state)
    logger.info("Review graph completed for %s#%s", repo_name, pr_number)
    return result
