import hashlib
import hmac
import logging
from typing import Any

import httpx
from asyncio import sleep

from config import get_settings

logger = logging.getLogger(__name__)


class GitHubClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_url = self.settings.github_api_base_url.rstrip("/")
        self.timeout = self.settings.github_request_timeout_seconds
        self.max_retries = self.settings.github_max_retries
        self.retry_backoff_seconds = self.settings.github_retry_backoff_seconds
        self.retry_max_backoff_seconds = self.settings.github_retry_max_backoff_seconds
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

    def _is_retryable_status(self, status_code: int) -> bool:
        return status_code == 429 or 500 <= status_code <= 599

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.request(
                        method=method,
                        url=url,
                        headers=headers,
                        json=json,
                    )

                if not self._is_retryable_status(response.status_code):
                    response.raise_for_status()
                    return response

                retry_after = response.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    delay = float(retry_after)
                else:
                    delay = min(
                        self.retry_backoff_seconds * (2**attempt),
                        self.retry_max_backoff_seconds,
                    )

                logger.warning(
                    "GitHub API retryable status=%s attempt=%s/%s url=%s delay=%ss",
                    response.status_code,
                    attempt + 1,
                    self.max_retries + 1,
                    url,
                    delay,
                )
                if attempt >= self.max_retries:
                    response.raise_for_status()
                await sleep(delay)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
                delay = min(
                    self.retry_backoff_seconds * (2**attempt),
                    self.retry_max_backoff_seconds,
                )
                logger.warning(
                    "GitHub API network error attempt=%s/%s url=%s delay=%ss error=%s",
                    attempt + 1,
                    self.max_retries + 1,
                    url,
                    delay,
                    str(exc),
                )
                if attempt >= self.max_retries:
                    raise
                await sleep(delay)

        if last_error:
            raise last_error
        raise RuntimeError("Unexpected retry flow in GitHub client")

    async def get_pr_diff(self, repo_full_name: str, pr_number: int) -> str:
        url = f"{self.base_url}/repos/{repo_full_name}/pulls/{pr_number}"
        headers = {**self._headers, "Accept": "application/vnd.github.v3.diff"}

        logger.info("Fetching PR diff for %s#%s", repo_full_name, pr_number)
        response = await self._request_with_retry("GET", url, headers=headers)
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
        response = await self._request_with_retry(
            "POST",
            url,
            headers=self._headers,
            json=payload,
        )
        logger.info(
            "Posted PR comment to %s#%s with status %s",
            repo_full_name,
            pr_number,
            response.status_code,
        )
