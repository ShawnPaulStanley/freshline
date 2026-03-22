# ⚡ FreshLine — Legacy Code Modernization Engine

> CLI tool that converts legacy Java projects to modern Python using LLM-powered context optimization. Minimizes hallucinations by feeding only relevant code dependencies to the model.

![Python](https://img.shields.io/badge/python-3.12+-blue?logo=python)
![License](https://img.shields.io/badge/license-MIT-green)

---

## What It Does

1. **Parses** Java projects into AST (classes, methods, fields, imports, calls)
2. **Builds a dependency graph** — maps how every function connects to others
3. **Detects dead code & noise** — finds unreachable methods, excessive comments, TODO blocks, commented-out code
4. **Optimizes context windows** — for each function, packs *only* the relevant dependencies into the LLM prompt (the key innovation that prevents hallucinations)
5. **Converts Java → Python** via Groq LLM with confidence scoring per function
6. **Outputs a complete Python project** with a conversion report

## Why Context Optimization Matters

Most LLM code tools dump the entire codebase into the prompt. This causes:
- **Hallucinations** — the model gets confused by irrelevant code
- **Context overflow** — large repos exceed the context window
- **Noise pollution** — dead code, TODO comments, and commented-out code distract the model

FreshLine solves this by walking the dependency graph and feeding only what each function actually needs.

---

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/ShawnPaulStanley/freshline.git
cd freshline
python -m pip install -r requirements.txt
```

### 2. Set Your Groq API Key

Get a **free** key from [console.groq.com](https://console.groq.com), then:

```bash
# Copy the example and add your key
cp .env.example .env
```

Edit `.env`:
```
GROQ_API_KEY=gsk_your_actual_key_here
```

### 3. Run

```bash
python -m app.cli
```

You'll get an interactive terminal menu:

```
═══════════════════════════════════
   ⚡ FRESHLINE MENU
═══════════════════════════════════
   [1] List projects in uploads/
   [2] Analyze project (parse + dep graph + dead code)
   [3] Modernize project (Java → Python)
   [4] View output projects
   [5] Copy sample project to uploads/
   [6] Settings
   [0] Exit
═══════════════════════════════════
```

### 4. Try the Sample

1. Pick **[5]** to copy the sample `banking-app` into `uploads/`
2. Pick **[2]** to analyze it (see the dependency graph, dead code, noise ratio)
3. Pick **[3]** to modernize it (converts to Python, outputs to `output/banking-app/`)

---

## Project Structure

```
freshline/
├── app/
│   ├── cli.py                ← Interactive terminal menu
│   ├── config.py             ← Groq key, token budgets, paths
│   ├── engine/
│   │   ├── parser.py         ← Java AST parser (javalang)
│   │   ├── graph.py          ← Dependency graph builder (networkx)
│   │   ├── dead_code.py      ← Dead code + noise detector
│   │   ├── optimizer.py      ← Context window optimizer ★
│   │   └── modernizer.py     ← Full pipeline orchestrator
│   ├── llm/
│   │   ├── groq_client.py    ← Groq API client + response parser
│   │   └── prompts.py        ← Prompt templates (modernize + document)
│   └── models/
│       └── schemas.py        ← All data classes (ParsedFile, etc.)
├── samples/
│   └── banking-app/          ← 7-file sample Java project for testing
├── uploads/                  ← Drop Java project folders here (gitignored)
├── output/                   ← Converted Python projects appear here (gitignored)
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## How the Engine Works

```
Java Project
     │
     ▼
┌─────────────┐
│   PARSER    │  javalang AST → classes, methods, fields, imports, calls
└──────┬──────┘
       ▼
┌─────────────┐
│ DEP GRAPH   │  networkx directed graph: nodes = methods, edges = calls/imports
└──────┬──────┘
       ▼
┌─────────────┐
│ DEAD CODE   │  find unreachable methods, strip noise (TODOs, excessive comments)
│  DETECTOR   │
└──────┬──────┘
       ▼
┌─────────────┐
│  CONTEXT    │  ★ For each function: walk graph → rank deps → pack under
│ OPTIMIZER   │    token budget → include signatures for deps that don't fit
└──────┬──────┘
       ▼
┌─────────────┐
│  GROQ LLM   │  Send optimized context → get Python code + confidence score
│ (llama-3.3) │
└──────┬──────┘
       ▼
  Python Project
  (output/ folder)
```

---

## Sample Output

When you modernize the sample banking app, you get:

| File | What It Contains |
|------|------------------|
| `account.py` | Account class with deposit, withdraw, transfer |
| `transaction.py` | Transaction dataclass |
| `banking_app.py` | Main app with account management |
| `logger.py` | Logging utility |
| `interest_calculator.py` | Interest rate calculator |
| `CONVERSION_REPORT.md` | Per-method confidence scores and conversion details |

Each function gets a **confidence score**:
- 🟢 **90-100%** — straight conversion, full context available
- 🟡 **50-89%** — good but had to make assumptions
- 🔴 **0-49%** — significant guesswork, review carefully

---

## For Shawn (Frontend Integration)

> See [ARCHITECTURE.md](ARCHITECTURE.md) for the full breakdown of each module and how to hook up a web frontend.

**TL;DR**: The engine functions in `app/engine/modernizer.py` return structured Python dataclasses. To add a web frontend:

1. Add FastAPI as a thin API layer that calls the existing engine functions
2. Key functions to expose:
   - `modernizer.analyze_project(path)` → returns graph + stats + dead code
   - `modernizer.modernize_project(path)` → returns full conversion results
3. All data classes are in `app/models/schemas.py` — they serialize cleanly to JSON

---

## Tech Stack

| Component | Tech | Why |
|-----------|------|-----|
| Java Parser | `javalang` | Reliable Java AST parser for Python |
| Dep Graph | `networkx` | Industry-standard graph library |
| LLM | Groq API (`llama-3.3-70b-versatile`) | Free tier, fast inference |
| Token Counting | Word-based heuristic | No C compiler needed (unlike tiktoken) |
| CLI | `rich` | Beautiful terminal UI |
| Config | `python-dotenv` | Clean env var management |

---

## Configuration

All config lives in `app/config.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model to use |
| `MAX_CONTEXT_TOKENS` | `6000` | Token budget per LLM call |
| `GROQ_TEMPERATURE` | `0.1` | Low = deterministic code output |
| `NOISE_COMMENT_THRESHOLD` | `3` | Lines of consecutive comments = noise |

---

## License

MIT
