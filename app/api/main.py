from __future__ import annotations

import shutil
import zipfile
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.config import OUTPUT_DIR, UPLOADS_DIR
from app.engine.modernizer import analyze_project, modernize_project

app = FastAPI(title="FreshLine API", version="1.0.0")

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


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "FreshLine API", "status": "ok"}


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
