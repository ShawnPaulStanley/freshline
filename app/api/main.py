from __future__ import annotations

import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from app.config import OUTPUT_DIR, UPLOADS_DIR
from app.engine.modernizer import analyze_project, modernize_project

app = FastAPI(title="FreshLine API", version="1.0.0")
UI_FILE = Path(__file__).with_name("ui.html")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {k: _to_jsonable(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(v) for v in value]
    return value


def _project_path(project_name: str) -> Path:
    safe_name = Path(project_name).name
    path = UPLOADS_DIR / safe_name
    if not path.exists() or not path.is_dir():
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")
    return path


def _java_file_count(project_dir: Path) -> int:
    return sum(1 for _ in project_dir.rglob("*.java"))


def _zip_directory(source_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in source_dir.rglob("*"):
            if file_path.is_file():
                archive.write(file_path, arcname=file_path.relative_to(source_dir))


def _repo_name_from_url(repo_url: str) -> str:
    normalized = repo_url.strip().rstrip("/")
    if normalized.endswith(".git"):
        normalized = normalized[:-4]

    if "/" not in normalized:
        return ""

    name = normalized.split("/")[-1].strip()
    if not name:
        return ""

    invalid_chars = set('\\/:*?"<>|')
    if any(ch in invalid_chars for ch in name):
        return ""

    return name


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/ui", status_code=307)


@app.get("/ui", response_class=HTMLResponse, include_in_schema=False)
def ui() -> str:
    if not UI_FILE.exists():
        raise HTTPException(status_code=500, detail="UI file is missing")
    return UI_FILE.read_text(encoding="utf-8")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/projects")
def list_projects() -> dict[str, Any]:
    projects = sorted([d.name for d in UPLOADS_DIR.iterdir() if d.is_dir()])
    return {
        "projects": projects,
        "count": len(projects),
    }


@app.post("/api/projects/upload-zip")
def upload_project_zip(file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip uploads are supported")

    project_name = Path(file.filename).stem
    project_dir = UPLOADS_DIR / project_name

    temp_zip = UPLOADS_DIR / f"{project_name}.zip"
    try:
        with temp_zip.open("wb") as destination:
            shutil.copyfileobj(file.file, destination)

        if project_dir.exists():
            shutil.rmtree(project_dir)
        project_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(temp_zip, "r") as zf:
            zf.extractall(project_dir)

        nested_dirs = [p for p in project_dir.iterdir() if p.is_dir()]
        files_at_root = [p for p in project_dir.iterdir() if p.is_file()]
        if len(nested_dirs) == 1 and not files_at_root:
            nested_root = nested_dirs[0]
            for item in nested_root.iterdir():
                shutil.move(str(item), project_dir / item.name)
            nested_root.rmdir()

        java_files = _java_file_count(project_dir)

        return {
            "project_name": project_name,
            "project_dir": str(project_dir),
            "java_files": java_files,
        }
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail=f"Invalid zip file: {exc}") from exc
    finally:
        file.file.close()
        if temp_zip.exists():
            temp_zip.unlink(missing_ok=True)


@app.post("/api/projects/import-github")
def import_project_github(
    repo_url: str = Query(..., description="Git repository URL"),
    overwrite: bool = Query(True, description="Overwrite existing project folder if present"),
) -> dict[str, Any]:
    repo_name = _repo_name_from_url(repo_url)
    if not repo_name:
        raise HTTPException(status_code=400, detail="Invalid repository URL")

    if shutil.which("git") is None:
        raise HTTPException(status_code=500, detail="Git is not installed on server")

    project_dir = UPLOADS_DIR / repo_name

    if project_dir.exists():
        if not overwrite:
            raise HTTPException(status_code=409, detail=f"Project '{repo_name}' already exists")
        shutil.rmtree(project_dir)

    proc = subprocess.run(
        ["git", "clone", repo_url, str(project_dir)],
        capture_output=True,
        text=True,
        check=False,
        timeout=240,
    )

    if proc.returncode != 0:
        details = proc.stderr.strip() or proc.stdout.strip() or "git clone failed"
        raise HTTPException(status_code=400, detail=details)

    java_files = _java_file_count(project_dir)

    return {
        "project_name": repo_name,
        "project_dir": str(project_dir),
        "repo_url": repo_url,
        "java_files": java_files,
    }


@app.get("/api/projects/{project_name}/analyze")
def analyze(project_name: str) -> dict[str, Any]:
    project_dir = _project_path(project_name)

    if _java_file_count(project_dir) == 0:
        raise HTTPException(status_code=400, detail="Project contains no .java files")

    result = analyze_project(str(project_dir))

    payload = {
        "files": result["files"],
        "classes": result["classes"],
        "methods": result["methods"],
        "dead_methods": result["dead_methods"],
        "dead_method_names": result["dead_method_names"],
        "noise": result["noise"],
        "graph": result["graph"],
        "graph_stats": result["graph_stats"],
    }
    return _to_jsonable(payload)


@app.post("/api/projects/{project_name}/modernize")
def modernize(
    project_name: str,
    skip_dead_code: bool = Query(True),
) -> dict[str, Any]:
    project_dir = _project_path(project_name)

    if _java_file_count(project_dir) == 0:
        raise HTTPException(status_code=400, detail="Project contains no .java files")

    try:
        result = modernize_project(
            project_dir=str(project_dir),
            project_name=project_name,
            skip_dead_code=skip_dead_code,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_jsonable(result)


@app.get("/api/output")
def list_output_projects() -> dict[str, Any]:
    outputs = sorted([d.name for d in OUTPUT_DIR.iterdir() if d.is_dir()])
    return {
        "projects": outputs,
        "count": len(outputs),
    }


@app.get("/api/projects/{project_name}/download-output")
def download_output(project_name: str, background_tasks: BackgroundTasks) -> FileResponse:
    safe_name = Path(project_name).name
    output_dir = OUTPUT_DIR / safe_name

    if not output_dir.exists() or not output_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Output for '{project_name}' not found")

    temp_file = tempfile.NamedTemporaryFile(prefix=f"freshline_{safe_name}_", suffix=".zip", delete=False)
    temp_file_path = Path(temp_file.name)
    temp_file.close()

    _zip_directory(output_dir, temp_file_path)
    background_tasks.add_task(lambda p: Path(p).unlink(missing_ok=True), str(temp_file_path))

    return FileResponse(
        path=temp_file_path,
        media_type="application/zip",
        filename=f"{safe_name}_output.zip",
    )


@app.delete("/api/projects/{project_name}/storage")
def cleanup_storage(project_name: str) -> dict[str, Any]:
    safe_name = Path(project_name).name
    project_dir = UPLOADS_DIR / safe_name
    output_dir = OUTPUT_DIR / safe_name

    deleted_upload = False
    deleted_output = False

    if project_dir.exists() and project_dir.is_dir():
        shutil.rmtree(project_dir)
        deleted_upload = True

    if output_dir.exists() and output_dir.is_dir():
        shutil.rmtree(output_dir)
        deleted_output = True

    return {
        "project_name": safe_name,
        "deleted_upload": deleted_upload,
        "deleted_output": deleted_output,
    }
