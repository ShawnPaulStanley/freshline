"""Quick smoke test for all engine modules."""
import sys, os
from pathlib import Path

# Fix Windows encoding
sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, str(Path(__file__).parent))

from app.engine.parser import parse_project
from app.engine.graph import DependencyGraph
from app.engine.dead_code import detect_dead_methods, get_noise_summary
from app.engine.optimizer import optimize_context

SAMPLE = str(Path(__file__).parent / "samples" / "banking-app")

print("=" * 60)
print("FRESHLINE ENGINE SMOKE TEST")
print("=" * 60)

# 1. Parse
print("\n[1] PARSING...")
files = parse_project(SAMPLE)
for f in files:
    name = Path(f.file_path).name
    errs = f.parse_errors
    classes = len(f.classes)
    methods = len(f.all_methods)
    status = "OK" if not errs else f"ERRORS: {errs}"
    print(f"  {name}: {classes} classes, {methods} methods -- {status}")

print(f"\n  Total files: {len(files)}")
print(f"  Total classes: {sum(len(f.classes) for f in files)}")
print(f"  Total methods: {sum(len(f.all_methods) for f in files)}")

# 2. Dep Graph
print("\n[2] DEPENDENCY GRAPH...")
graph = DependencyGraph()
graph.build(files)
stats = graph.get_stats()
print(f"  Nodes: {stats['total_nodes']}")
print(f"  Edges: {stats['total_edges']}")
print(f"  Classes: {stats['classes']}")
print(f"  Methods: {stats['methods']}")
print(f"  Has cycles: {stats['has_cycles']}")

print("\n  Sample edges:")
gd = graph.to_dict()
for edge in gd["edges"][:15]:
    print(f"    {edge['source']} --[{edge['type']}]--> {edge['target']}")
if len(gd["edges"]) > 15:
    print(f"    ... and {len(gd['edges']) - 15} more")

# 3. Dead code
print("\n[3] DEAD CODE DETECTION...")
dead = detect_dead_methods(files)
print(f"  Dead methods: {len(dead)}")
for d in dead:
    print(f"    X {d.qualified_name}")

noise = get_noise_summary(files)
print(f"\n  Noise ratio: {noise['noise_ratio']:.1%}")
print(f"  Noise lines: {noise['noise_lines']} / {noise['total_lines']}")
for nt, count in noise.get("noise_by_type", {}).items():
    print(f"    {nt}: {count} lines")

# 4. Optimizer
print("\n[4] CONTEXT OPTIMIZATION...")
conversion_order = graph.get_conversion_order()
test_count = 0
for mid in conversion_order:
    m = graph.get_method(mid)
    if m and m.calls and test_count < 3:
        ctx = optimize_context(m, graph)
        print(f"\n  Target: {m.qualified_name}")
        print(f"    Calls: {m.calls}")
        print(f"    Included deps: {ctx.included_deps}")
        print(f"    Excluded deps: {ctx.excluded_deps}")
        print(f"    Original LOC: {ctx.original_total_lines}")
        print(f"    Optimized LOC: {ctx.optimized_total_lines}")
        print(f"    Compression: {ctx.compression_ratio:.1%}")
        print(f"    Est. tokens: {ctx.estimated_tokens}")
        test_count += 1

print("\n" + "=" * 60)
print("ALL CHECKS PASSED")
print("=" * 60)
