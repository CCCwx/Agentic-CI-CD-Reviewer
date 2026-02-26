import hashlib
import hmac
import logging

import httpx

from config import get_settings

logger = logging.getLogger(__name__)


class GitHubClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_url = self.settings.github_api_base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {self.settings.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Agentic-PR-Reviewer",
        }

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        if not signature or not signature.startswith("sha256="):
            return False

        digest = hmac.new(
            key=self.settings.github_webhook_secret.encode("utf-8"),
            msg=payload,
            digestmod=hashlib.sha256,
        ).hexdigest()
        expected_signature = f"sha256={digest}"
        return hmac.compare_digest(expected_signature, signature)

    async def get_pr_diff(self, repo_full_name: str, pr_number: int) -> str:
        url = f"{self.base_url}/repos/{repo_full_name}/pulls/{pr_number}"
        headers = {**self._headers, "Accept": "application/vnd.github.v3.diff"}

        logger.info("Fetching PR diff for %s#%s", repo_full_name, pr_number)
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            logger.info(
                "Fetched PR diff for %s#%s with status %s",
                repo_full_name,
                pr_number,
                response.status_code,
            )
            return response.text

    async def post_pr_comment(self, repo_full_name: str, pr_number: int, body: str) -> None:
        url = f"{self.base_url}/repos/{repo_full_name}/issues/{pr_number}/comments"
        payload = {"body": body}

        logger.info("Posting PR comment to %s#%s", repo_full_name, pr_number)
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=self._headers, json=payload)
            response.raise_for_status()
            logger.info(
                "Posted PR comment to %s#%s with status %s",
                repo_full_name,
                pr_number,
                response.status_code,
            )
