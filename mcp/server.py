import os
from typing import Optional
import httpx
from mcp.server.fastmcp import FastMCP

SERVER = os.environ.get("CONDUIT_SERVER", "http://localhost:2006")

mcp = FastMCP("conduit")


def _api(method: str, path: str, **kwargs):
    url = f"{SERVER}{path}"
    with httpx.Client(timeout=30) as client:
        resp = client.request(method, url, **kwargs)
        resp.raise_for_status()
        return resp.json()


@mcp.tool()
def run_job(
    command: str,
    git_repo: Optional[str] = None,
    working_dir: Optional[str] = None,
    name: Optional[str] = None,
) -> dict:
    """Submit a job to the remote GPU server. Returns the new job's ID and initial status."""
    body = {
        "name": name or command[:60],
        "command": command,
        "git_repo": git_repo,
        "working_dir": working_dir,
    }
    return _api("POST", "/jobs", json=body)


@mcp.tool()
def job_status(job_id: str) -> dict:
    """Get the current status and recent output (last 20 lines) for a job."""
    job = _api("GET", f"/jobs/{job_id}")
    output_result = _api("GET", f"/jobs/{job_id}/output", params={"lines": 20})
    job["recent_output"] = output_result.get("output", "")
    return job


@mcp.tool()
def list_jobs() -> list:
    """List all jobs on the remote GPU server with id, name, status, and start time."""
    return _api("GET", "/jobs")


@mcp.tool()
def job_output(job_id: str, lines: int = 100) -> str:
    """Get the last N lines of log output for a job."""
    result = _api("GET", f"/jobs/{job_id}/output", params={"lines": lines})
    return result.get("output", "")


@mcp.tool()
def kill_job(job_id: str) -> dict:
    """Kill a running job by ID."""
    return _api("DELETE", f"/jobs/{job_id}")


if __name__ == "__main__":
    mcp.run()
