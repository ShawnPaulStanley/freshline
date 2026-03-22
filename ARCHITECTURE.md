# Architecture Guide

> For Shawn or anyone building a frontend / extending FreshLine.

---

## Module Map

```
app/
├── cli.py              ← UI layer (terminal). Replace with FastAPI for web.
├── config.py           ← All settings. Reads from .env
├── engine/             ← Core logic. This is the brain.
│   ├── parser.py       ← INPUT: .java file path → OUTPUT: ParsedFile
│   ├── graph.py        ← INPUT: [ParsedFile] → OUTPUT: DependencyGraph
│   ├── dead_code.py    ← INPUT: [ParsedFile] → OUTPUT: dead methods, noise stats
│   ├── optimizer.py    ← INPUT: method + graph → OUTPUT: OptimizedContext
│   └── modernizer.py   ← INPUT: project path → OUTPUT: ProjectResult (orchestrator)
├── llm/
│   ├── groq_client.py  ← Groq API wrapper. Send prompt → get response.
│   └── prompts.py      ← Prompt templates. Edit these to change LLM behavior.
└── models/
    └── schemas.py      ← ALL data classes. This is the shared contract.
```

---

## Data Flow

```
                    ┌──────────────────────────────────────┐
                    │        modernizer.py (orchestrator)   │
                    │                                      │
   Java Project ──► │  1. parser.parse_project(dir)        │
                    │       → list[ParsedFile]              │
                    │                                      │
                    │  2. DependencyGraph().build(files)    │
                    │       → graph with nodes/edges        │
                    │                                      │
                    │  3. dead_code.detect_dead_methods()   │
                    │       → list of dead methods          │
                    │                                      │
                    │  4. For each method (topo-sorted):    │
                    │     a. optimizer.optimize_context()   │
                    │        → OptimizedContext             │
                    │     b. groq_client.send(prompt)       │
                    │        → {code, confidence, ...}      │
                    │                                      │
                    │  5. Assemble output Python project    │
                    │       → ProjectResult                 │
                    └──────────────────────────────────────┘
```

---

## Key Data Classes (schemas.py)

### `ParsedFile`
```python
file_path: str
package: str
imports: list[str]
classes: list[ParsedClass]
raw_source: str
parse_errors: list[str]
```

### `ParsedMethod`
```python
name: str
class_name: str
source_code: str
return_type: str
parameters: list[str]      # ["String name", "int age"]
calls: list[str]            # ["Logger.log", "withdraw"]
qualified_name → "Account.deposit"
is_entry_point → True if main/init/run
```

### `OptimizedContext`
```python
target_function: ParsedMethod
context_code: str           # The assembled context for the LLM
included_deps: list[str]    # What fit in the token budget
excluded_deps: list[str]    # What didn't fit
compression_ratio → float   # How much we compressed
estimated_tokens: int
```

### `ModernizedFunction`
```python
original_method: ParsedMethod
python_code: str
explanation: str
confidence: float           # 0.0 - 1.0
confidence_notes: str
context_stats: OptimizedContext
```

### `ProjectResult`
```python
project_name: str
files_parsed: int
methods_converted: int
methods_skipped: int        # Dead code skipped
functions: list[ModernizedFunction]
avg_confidence: float
avg_compression_ratio: float
```

---

## How to Add a Web Frontend

The CLI (`cli.py`) is just a UI layer. The engine is completely decoupled. Here's the recommended approach:

### 1. Add FastAPI

```bash
pip install fastapi uvicorn python-multipart
```

### 2. Create `app/api/routes.py`

```python
from fastapi import FastAPI, UploadFile
from app.engine.modernizer import modernize_project, analyze_project
from app.config import UPLOADS_DIR, OUTPUT_DIR

app = FastAPI(title="FreshLine API")

@app.post("/api/upload")
async def upload_project(file: UploadFile):
    # Extract zip to uploads/
    # Return { repo_id, file_count }

@app.get("/api/analyze/{project_name}")
async def analyze(project_name: str):
    result = analyze_project(str(UPLOADS_DIR / project_name))
    return result  # Has graph, dead code, noise stats

@app.post("/api/modernize/{project_name}")
async def modernize(project_name: str):
    result = modernize_project(str(UPLOADS_DIR / project_name))
    # ProjectResult dataclass → dict for JSON response
    return {
        "project_name": result.project_name,
        "files_parsed": result.files_parsed,
        "methods_converted": result.methods_converted,
        "avg_confidence": result.avg_confidence,
        "functions": [
            {
                "name": f.original_method.qualified_name,
                "python_code": f.python_code,
                "confidence": f.confidence,
                "explanation": f.explanation,
            }
            for f in result.functions
        ],
    }
```

### 3. Run

```bash
uvicorn app.api.routes:app --reload
```

### Key Points for Frontend Dev
- **All data classes are in `schemas.py`** — they map 1:1 to your API response types
- **`analyze_project()`** returns everything needed for the analysis view (graph, dead code, stats)
- **`modernize_project()`** returns everything needed for the results view (converted code, confidence per method)
- **The dep graph exports to `{nodes, edges}` dict** via `graph.to_dict()` — perfect for d3.js visualization
- **No state** — each call is independent, no sessions to manage

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Parse per-method, not per-file | Methods are the atomic unit of conversion. Keeps LLM context focused. |
| Topological sort for conversion order | Process dependencies before dependents, so already-converted code can inform later conversions. |
| Signature-only fallback | When a dependency is too large for the token budget, include just its signature instead of nothing. |
| 2-second rate limit | Groq free tier allows 30 req/min. 2s spacing keeps us safe. |
| Marker-delimited LLM output | JSON output format fails when code contains quotes/backslashes. Markers are unambiguous. |
| Dead code skipped by default | Reduces LLM calls and prevents wasted conversions. User can override. |
