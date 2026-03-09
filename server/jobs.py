import os
import subprocess
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

PROJECTS_DIR = Path(os.environ.get("CONDUIT_PROJECTS_DIR", Path.home() / "projects"))
LOGS_DIR = Path(__file__).parent.parent / "logs"

jobs: dict[str, dict] = {}


def _repo_name(git_repo: str) -> str:
    name = git_repo.rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return name


def _ensure_repo(git_repo: str, log_file) -> Path:
    repo_name = _repo_name(git_repo)
    repo_path = PROJECTS_DIR / repo_name
    if repo_path.exists():
        log_file.write(f"[conduit] Pulling {repo_path}\n")
        log_file.flush()
        subprocess.run(["git", "pull"], cwd=repo_path, check=True, stdout=log_file, stderr=log_file)
    else:
        log_file.write(f"[conduit] Cloning {git_repo} -> {repo_path}\n")
        log_file.flush()
        subprocess.run(["git", "clone", git_repo, str(repo_path)], check=True, stdout=log_file, stderr=log_file)
    return repo_path


def _ensure_venv(repo_path: Path, log_file) -> Path:
    venv_path = repo_path / ".venv"
    if not venv_path.exists():
        log_file.write(f"[conduit] Creating venv at {venv_path}\n")
        log_file.flush()
        subprocess.run(["python", "-m", "venv", str(venv_path)], check=True, stdout=log_file, stderr=log_file)

    pip = venv_path / "Scripts" / "pip.exe"

    if (repo_path / "requirements.txt").exists():
        log_file.write("[conduit] Installing requirements.txt\n")
        log_file.flush()
        subprocess.run([str(pip), "install", "-r", "requirements.txt"], cwd=repo_path, check=True, stdout=log_file, stderr=log_file)
    elif (repo_path / "pyproject.toml").exists():
        log_file.write("[conduit] Installing pyproject.toml\n")
        log_file.flush()
        subprocess.run([str(pip), "install", "-e", "."], cwd=repo_path, check=True, stdout=log_file, stderr=log_file)

    return venv_path


def _venv_env(venv_path: Path, base_env: dict) -> dict:
    env = base_env.copy()
    scripts_dir = str(venv_path / "Scripts")
    env["VIRTUAL_ENV"] = str(venv_path)
    env["PATH"] = scripts_dir + os.pathsep + env.get("PATH", "")
    env.pop("PYTHONHOME", None)
    return env


def _push_results(job: dict, repo_path: Path):
    """Wait for job to finish, then commit and push any changes."""
    process = job["process"]
    process.wait()

    log_path = Path(job["log_path"])

    status_result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )

    if not status_result.stdout.strip():
        return

    with open(log_path, "a") as f:
        f.write("\n[conduit] Committing and pushing changes...\n")

    try:
        subprocess.run(["git", "add", "-A"], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", f"conduit: job {job['id']}"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(["git", "push"], cwd=repo_path, check=True)
        job["files_updated"] = True
        with open(log_path, "a") as f:
            f.write("[conduit] Push complete.\n")
    except subprocess.CalledProcessError as e:
        with open(log_path, "a") as f:
            f.write(f"[conduit] Git push failed: {e}\n")


def submit_job(
    name: str,
    command: str,
    git_repo: Optional[str] = None,
    working_dir: Optional[str] = None,
    env: Optional[dict] = None,
) -> dict:
    job_id = str(uuid.uuid4())
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"{job_id}.log"

    resolved_working_dir = working_dir

    job = {
        "id": job_id,
        "name": name,
        "command": command,
        "git_repo": git_repo,
        "working_dir": None,
        "log_path": str(log_path),
        "status": "queued",
        "start_time": datetime.utcnow().isoformat(),
        "pid": None,
        "process": None,
        "files_updated": False,
    }
    jobs[job_id] = job

    try:
        proc_env = os.environ.copy()
        if env:
            proc_env.update(env)

        with open(log_path, "w") as log_file:
            repo_path = None
            if git_repo:
                repo_path = _ensure_repo(git_repo, log_file)
                resolved_working_dir = resolved_working_dir or str(repo_path)
                venv_path = _ensure_venv(repo_path, log_file)
                proc_env = _venv_env(venv_path, proc_env)

            job["working_dir"] = resolved_working_dir

            log_file.write(f"[conduit] Running: {command}\n\n")
            log_file.flush()

            process = subprocess.Popen(
                command,
                shell=True,
                cwd=resolved_working_dir,
                env=proc_env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )

        job["process"] = process
        job["pid"] = process.pid
        job["status"] = "running"

        if git_repo and repo_path:
            thread = threading.Thread(target=_push_results, args=(job, repo_path), daemon=True)
            thread.start()

    except Exception as e:
        job["status"] = "failed"
        with open(log_path, "a") as f:
            f.write(f"\n[conduit] Error: {e}\n")

    return _serialize(job)


def list_jobs() -> list[dict]:
    _refresh_statuses()
    return [_serialize(j) for j in jobs.values()]


def get_job(job_id: str) -> Optional[dict]:
    job = jobs.get(job_id)
    if job is None:
        return None
    _refresh_status(job)
    return _serialize(job)


def get_job_output(job_id: str, lines: int = 100) -> Optional[str]:
    job = jobs.get(job_id)
    if job is None:
        return None
    log_path = Path(job["log_path"])
    if not log_path.exists():
        return ""
    with open(log_path, "r", errors="replace") as f:
        all_lines = f.readlines()
    return "".join(all_lines[-lines:])


def kill_job(job_id: str) -> Optional[dict]:
    job = jobs.get(job_id)
    if job is None:
        return None
    process = job.get("process")
    if process and job["status"] == "running":
        process.terminate()
        job["status"] = "failed"
    return _serialize(job)


def _refresh_statuses():
    for job in jobs.values():
        _refresh_status(job)


def _refresh_status(job: dict):
    if job["status"] not in ("running",):
        return
    process = job.get("process")
    if process is None:
        return
    ret = process.poll()
    if ret is None:
        job["status"] = "running"
    elif ret == 0:
        job["status"] = "done"
    else:
        job["status"] = "failed"


def _serialize(job: dict) -> dict:
    return {
        "id": job["id"],
        "name": job["name"],
        "command": job["command"],
        "git_repo": job["git_repo"],
        "working_dir": job["working_dir"],
        "log_path": job["log_path"],
        "status": job["status"],
        "start_time": job["start_time"],
        "pid": job["pid"],
        "files_updated": job["files_updated"],
    }
