from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import jobs as job_store

app = FastAPI(title="conduit job server")


class JobRequest(BaseModel):
    name: str
    command: str
    git_repo: Optional[str] = None
    working_dir: Optional[str] = None
    env: Optional[dict[str, str]] = None


@app.post("/jobs", status_code=201)
def submit_job(req: JobRequest):
    job = job_store.submit_job(
        name=req.name,
        command=req.command,
        git_repo=req.git_repo,
        working_dir=req.working_dir,
        env=req.env,
    )
    return job


@app.get("/jobs")
def list_jobs():
    return job_store.list_jobs()


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/jobs/{job_id}/output")
def get_job_output(job_id: str, lines: int = 100):
    output = job_store.get_job_output(job_id, lines=lines)
    if output is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job_id": job_id, "output": output}


@app.delete("/jobs/{job_id}")
def kill_job(job_id: str):
    job = job_store.kill_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
