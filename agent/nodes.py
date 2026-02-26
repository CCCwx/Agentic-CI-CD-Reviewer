import logging

from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from agent.state import GraphState, ReviewResult
from config import get_settings
from github_api.client import GitHubClient

logger = logging.getLogger(__name__)


def _build_chat_model():
    settings = get_settings()
    provider = settings.llm_provider.strip().lower()

    if provider == "openai":
        return ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            temperature=0,
        )

    return ChatGoogleGenerativeAI(
        model=settings.llm_model,
        google_api_key=settings.llm_api_key,
        temperature=0,
    )


async def reviewer_agent(state: GraphState) -> GraphState:
    logger.info("Reviewer agent started for %s#%s", state["repo_name"], state["pr_number"])
    llm = _build_chat_model().with_structured_output(ReviewResult)

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "You are a strict senior SDE reviewer. Focus on concurrency bugs, null pointer risks, "
                    "race conditions, async misuse, and business logic vulnerabilities. "
                    "Only report actionable issues and return structured output."
                ),
            ),
            (
                "human",
                "Please review the following PR diff:\n\n{pr_diff}",
            ),
        ]
    )

    chain = prompt | llm
    review_result = await chain.ainvoke({"pr_diff": state["pr_diff"]})
    logger.info(
        "Reviewer agent finished for %s#%s, has_bugs=%s",
        state["repo_name"],
        state["pr_number"],
        review_result.has_bugs,
    )
    return {"review_result": review_result}


async def patcher_agent(state: GraphState) -> GraphState:
    logger.info("Patcher agent started for %s#%s", state["repo_name"], state["pr_number"])
    review_result = state.get("review_result")
    if not review_result or not review_result.has_bugs:
        logger.info("Patcher agent skipped for %s#%s", state["repo_name"], state["pr_number"])
        return {"patch_code": None}

    llm = _build_chat_model()
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "You are a principal engineer. Based on review issues, generate concrete patch guidance "
                    "or code snippets to fix the bugs. Keep output concise and markdown-friendly."
                ),
            ),
            (
                "human",
                (
                    "PR diff:\n{pr_diff}\n\n"
                    "Review result:\n{review_result}\n\n"
                    "Return a patch proposal with code snippets."
                ),
            ),
        ]
    )
    chain = prompt | llm
    patch_resp = await chain.ainvoke(
        {
            "pr_diff": state["pr_diff"],
            "review_result": review_result.model_dump_json(indent=2),
        }
    )
    patch_code = patch_resp.content if isinstance(patch_resp.content, str) else str(patch_resp.content)
    logger.info("Patcher agent finished for %s#%s", state["repo_name"], state["pr_number"])
    return {"patch_code": patch_code}


async def committer_agent(state: GraphState) -> GraphState:
    logger.info("Committer agent started for %s#%s", state["repo_name"], state["pr_number"])
    review_result = state.get("review_result")
    patch_code = state.get("patch_code")
    llm = _build_chat_model()

    if review_result and not review_result.has_bugs:
        final_comment = (
            "## PR Review Result\n\n"
            "LGTM ✅\n\n"
            f"{review_result.summary}\n\n"
            "No blocking issues found."
        )
    else:
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    (
                        "You are a friendly code review assistant. Generate a GitHub PR comment in markdown, "
                        "including a short summary, issue list, and suggested fix snippets."
                    ),
                ),
                (
                    "human",
                    (
                        "Review result JSON:\n{review_result}\n\n"
                        "Patch proposal:\n{patch_code}\n\n"
                        "Produce final PR review comment."
                    ),
                ),
            ]
        )
        chain = prompt | llm
        comment_resp = await chain.ainvoke(
            {
                "review_result": review_result.model_dump_json(indent=2) if review_result else "{}",
                "patch_code": patch_code or "N/A",
            }
        )
        final_comment = (
            comment_resp.content
            if isinstance(comment_resp.content, str)
            else str(comment_resp.content)
        )

    github_client = state.get("github_client") or GitHubClient()
    await github_client.post_pr_comment(
        repo_full_name=state["repo_name"],
        pr_number=state["pr_number"],
        body=final_comment,
    )
    logger.info("Committer agent finished for %s#%s", state["repo_name"], state["pr_number"])
    return {"final_comment": final_comment}
