from typing import Any, Literal, NotRequired, TypedDict

from pydantic import BaseModel, Field


class ReviewIssue(BaseModel):
    file_path: str = Field(..., description="Issue location file path")
    line_number: int = Field(..., ge=1, description="Issue line number")
    issue_description: str = Field(..., min_length=1, description="Detailed issue description")
    severity: Literal["low", "medium", "high", "critical"] = Field(
        ..., description="Issue severity level"
    )


class ReviewResult(BaseModel):
    has_bugs: bool = Field(..., description="Whether critical issues exist in this PR")
    issues: list[ReviewIssue] = Field(default_factory=list, description="Detected issues list")
    summary: str = Field(..., min_length=1, description="Short review summary")


class GraphState(TypedDict):
    repo_name: str
    pr_number: int
    pr_diff: str
    review_result: ReviewResult | None
    patch_code: str | None
    final_comment: str | None
    github_client: NotRequired[Any]
