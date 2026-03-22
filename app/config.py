import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Groq LLM Config ──────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_MAX_TOKENS = 4096
GROQ_TEMPERATURE = 0.1  # Low temp = more deterministic code output

# ── Context Optimizer Config ─────────────────────────────────────
MAX_CONTEXT_TOKENS = 6000       # Token budget for LLM context window
DIRECT_DEP_WEIGHT = 1.0         # Weight for direct dependencies
TRANSITIVE_DEP_WEIGHT = 0.5     # Weight for transitive deps (further = less weight)
TYPE_ONLY_DEP_WEIGHT = 0.2      # Weight for type-only references

# ── Paths ─────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
UPLOADS_DIR = PROJECT_ROOT / "uploads"
OUTPUT_DIR = PROJECT_ROOT / "output"
SAMPLES_DIR = PROJECT_ROOT / "samples"

# Create dirs if they don't exist
UPLOADS_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Dead Code Detection ──────────────────────────────────────────
NOISE_COMMENT_THRESHOLD = 3     # Lines of consecutive comments = noise
ENTRY_POINT_METHODS = {"main", "init", "run", "start", "execute"}
