import logging

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request

from agent.graph import run_pr_review
from config import get_settings
from github_api.client import GitHubClient

settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Agentic PR Reviewer", version="0.1.0")


async def process_pr(repo_name: str, pr_number: int) -> None:
    client = GitHubClient()
    try:
        logger.info("Background task started for %s#%s", repo_name, pr_number)
        pr_diff = await client.get_pr_diff(repo_name, pr_number)
        await run_pr_review(
            repo_name=repo_name,
            pr_number=pr_number,
            pr_diff=pr_diff,
            github_client=client,
        )
        logger.info("Background task completed for %s#%s", repo_name, pr_number)
    except Exception:
        logger.exception("Background task failed for %s#%s", repo_name, pr_number)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhook")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
) -> dict[str, str]:
    payload = await request.body()
    client = GitHubClient()

    if not client.verify_webhook_signature(payload, x_hub_signature_256 or ""):
        logger.warning("Webhook signature verification failed")
        raise HTTPException(status_code=401, detail="Invalid signature")

    if x_github_event != "pull_request":
        logger.info("Ignored webhook event: %s", x_github_event)
        return {"status": "Ignored event"}

    data = await request.json()
    action = data.get("action")
    if action not in {"opened", "synchronize"}:
        logger.info("Ignored pull_request action: %s", action)
        return {"status": "Ignored action"}

    repo_name = data.get("repository", {}).get("full_name")
    pr_number = data.get("pull_request", {}).get("number")
    if not repo_name or not pr_number:
        raise HTTPException(status_code=400, detail="Missing repository or pull request number")

    logger.info("Webhook accepted for %s#%s action=%s", repo_name, pr_number, action)
    background_tasks.add_task(process_pr, repo_name, int(pr_number))
    return {"status": "Processing"}
