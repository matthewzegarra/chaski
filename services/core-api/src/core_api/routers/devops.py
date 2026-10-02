"""DevOps: latest GitHub Actions runs (read-only token) or a mock when not configured."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from chaski_common.auth import CurrentUser, require_roles
from chaski_common.logging import get_logger
from chaski_common.roles import Role
from fastapi import APIRouter, Depends, HTTPException

from core_api.settings import get_settings

router = APIRouter(prefix="/devops", tags=["devops"])
log = get_logger(__name__)


def _env_for(branch: str, name: str) -> str:
    text = f"{branch} {name}".lower()
    if "prod" in text or branch in ("main", "master"):
        return "PROD"
    if "test" in text or branch.startswith("release"):
        return "TEST"
    return "DEV"


def _github(repo: str, token: str) -> list[dict[str, Any]]:
    resp = httpx.get(
        f"https://api.github.com/repos/{repo}/actions/runs",
        params={"per_page": 15},
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        timeout=10,
    )
    resp.raise_for_status()
    return [
        {
            "id": r["id"],
            "workflow": r["name"],
            "branch": r["head_branch"],
            "commit": r["head_sha"][:7],
            "status": r["conclusion"] or r["status"],
            "environment": _env_for(r["head_branch"] or "", r["name"] or ""),
            "started_at": r["run_started_at"],
            "url": r["html_url"],
            "actor": (r.get("actor") or {}).get("login"),
        }
        for r in resp.json().get("workflow_runs", [])
    ]


def _mock() -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    plan = [
        ("cuentas-api CI/CD", "main", "success", "PROD", 2),
        ("cuentas-api CI/CD", "release/1.4", "success", "TEST", 5),
        ("cuentas-api CI/CD", "develop", "success", "DEV", 7),
        ("cuentas-api CI/CD", "develop", "failure", "DEV", 9),
        ("core-api build", "develop", "success", "DEV", 12),
        ("ia-api build", "develop", "success", "DEV", 20),
        ("web apps build", "main", "success", "PROD", 26),
        ("infra (bicep what-if)", "main", "success", "PROD", 30),
    ]
    return [
        {
            "id": 9_000_000 + i,
            "workflow": wf,
            "branch": branch,
            "commit": f"{(0xA1B2C3 + i * 7919) & 0xFFFFFFF:07x}",
            "status": status,
            "environment": env,
            "started_at": (now - timedelta(hours=hours)).isoformat(),
            "url": None,
            "actor": "chaski-bot",
            "tests": {
                "passed": 64 if status == "success" else 61,
                "failed": 0 if status == "success" else 3,
            },
            "coverage": 95.0 if status == "success" else 93.2,
        }
        for i, (wf, branch, status, env, hours) in enumerate(plan)
    ]


@router.get("/deployments")
def deployments(_user: CurrentUser = Depends(require_roles(Role.TI, Role.ADMIN))) -> dict[str, Any]:
    s = get_settings()
    if s.github_repo and s.github_token:
        try:
            runs = _github(s.github_repo, s.github_token.get_secret_value())
        except Exception as exc:
            log.exception("github_actions_failed")
            raise HTTPException(502, "No se pudo consultar GitHub Actions") from exc
        source = "github"
    else:
        runs = _mock()
        source = "mock"
    versions: dict[str, dict[str, Any]] = {}
    for r in runs:
        if r["status"] == "success" and r["environment"] not in versions:
            versions[r["environment"]] = {"commit": r["commit"], "deployed_at": r["started_at"]}
    return {"source": source, "runs": runs, "versions": versions}
