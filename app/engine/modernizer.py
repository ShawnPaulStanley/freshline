"""
Modernization Pipeline — orchestrates the full Java → Python conversion.

This is the main entry point that ties all engine modules together:
Parser → Dependency Graph → Dead Code Detection → Context Optimization → LLM → Output
"""

import os
import time
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.panel import Panel

from app.models.schemas import (
    ParsedFile, ModernizedFunction, ProjectResult, OptimizedContext,
)
from app.engine.parser import parse_project
from app.engine.graph import DependencyGraph
from app.engine.dead_code import detect_dead_methods, clean_source, get_noise_summary
from app.engine.optimizer import optimize_context, count_tokens
from app.llm.groq_client import GroqClient
from app.llm.prompts import (
    MODERNIZE_SYSTEM_PROMPT,
    build_modernize_prompt,
    DOCUMENT_SYSTEM_PROMPT,
    build_document_prompt,
)
from app.config import OUTPUT_DIR

console = Console()


def modernize_project(
    project_dir: str,
    project_name: str | None = None,
    skip_dead_code: bool = True,
    generate_docs: bool = True,
) -> ProjectResult:
    """Run the full modernization pipeline on a Java project.

    Args:
        project_dir: Path to the Java project directory.
        project_name: Optional name (defaults to directory name).
        skip_dead_code: Whether to skip detected dead methods.
        generate_docs: Whether to also generate documentation.

    Returns:
        ProjectResult with all conversion results and stats.
    """
    if project_name is None:
        project_name = Path(project_dir).name

    output_dir = OUTPUT_DIR / project_name
    output_dir.mkdir(parents=True, exist_ok=True)

    console.print(Panel(
        f"[bold cyan]⚡ FRESHLINE — Modernizing: {project_name}[/bold cyan]",
        border_style="cyan"
    ))

    # ── Step 1: Parse ──────────────────────────────────────────────
    console.print("\n[bold yellow]📂 Step 1: Parsing Java files...[/bold yellow]")
    parsed_files = parse_project(project_dir)

    files_parsed = len([pf for pf in parsed_files if not pf.parse_errors])
    files_failed = len([pf for pf in parsed_files if pf.parse_errors])

    for pf in parsed_files:
        status = "✓" if not pf.parse_errors else "✗"
        fname = Path(pf.file_path).name
        class_count = len(pf.classes)
        method_count = len(pf.all_methods)
        console.print(f"  {status} {fname}: {class_count} classes, {method_count} methods")
        for err in pf.parse_errors:
            console.print(f"    [red]Error: {err}[/red]")

    # ── Step 2: Build Dependency Graph ─────────────────────────────
    console.print("\n[bold yellow]🕸️  Step 2: Building dependency graph...[/bold yellow]")
    dep_graph = DependencyGraph()
    dep_graph.build(parsed_files)

    stats = dep_graph.get_stats()
    console.print(f"  Nodes: {stats['total_nodes']} | Edges: {stats['total_edges']} | "
                  f"Classes: {stats['classes']} | Methods: {stats['methods']} | "
                  f"Cycles: {'Yes' if stats['has_cycles'] else 'No'}")

    # ── Step 3: Detect Dead Code & Noise ───────────────────────────
    console.print("\n[bold yellow]🧹 Step 3: Detecting dead code & noise...[/bold yellow]")
    dead_methods = detect_dead_methods(parsed_files)
    noise_summary = get_noise_summary(parsed_files)

    dead_names = {m.qualified_name for m in dead_methods}
    console.print(f"  Dead methods found: {len(dead_methods)}")
    for dm in dead_methods:
        console.print(f"    [dim]✗ {dm.qualified_name}[/dim]")

    console.print(f"  Noise ratio: {noise_summary['noise_ratio']:.1%} "
                  f"({noise_summary['noise_lines']} / {noise_summary['total_lines']} lines)")
    for noise_type, count in noise_summary.get("noise_by_type", {}).items():
        console.print(f"    {noise_type}: {count} lines")

    # ── Step 4: Get Conversion Order ───────────────────────────────
    conversion_order = dep_graph.get_conversion_order()
    all_methods = dep_graph.get_all_methods()

    # Filter out dead methods if requested
    methods_to_convert = []
    methods_skipped = 0
    for method_id in conversion_order:
        method = dep_graph.get_method(method_id)
        if method is None:
            continue
        if skip_dead_code and method_id in dead_names:
            methods_skipped += 1
            continue
        methods_to_convert.append(method)

    console.print(f"\n[bold yellow]🔄 Step 4: Converting {len(methods_to_convert)} methods "
                  f"(skipping {methods_skipped} dead)...[/bold yellow]")

    # ── Step 5: Modernize Each Method ──────────────────────────────
    llm_client = GroqClient()
    results: list[ModernizedFunction] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Converting...", total=len(methods_to_convert))

        for method in methods_to_convert:
            progress.update(task, description=f"Converting {method.qualified_name}")

            # Optimize context for this method
            opt_ctx = optimize_context(method, dep_graph)

            # Clean the target method's source
            cleaned = clean_source(method.source_code)

            # Build the prompt
            user_prompt = build_modernize_prompt(
                target_method_source=cleaned.cleaned_source,
                context_code=opt_ctx.context_code,
                target_class_name=method.class_name,
                method_name=method.name,
                included_deps=opt_ctx.included_deps,
                excluded_deps=opt_ctx.excluded_deps,
            )

            # Send to LLM
            llm_response = llm_client.send(MODERNIZE_SYSTEM_PROMPT, user_prompt)

            result = ModernizedFunction(
                original_method=method,
                python_code=llm_response["code"],
                explanation=llm_response["explanation"],
                documentation="",  # Will be filled in doc generation pass
                confidence=llm_response["confidence"],
                confidence_notes=llm_response["confidence_notes"],
                context_stats=opt_ctx,
            )
            results.append(result)

            # Show per-method stats
            conf_color = "green" if result.confidence >= 0.8 else "yellow" if result.confidence >= 0.5 else "red"
            console.print(
                f"  ✓ {method.qualified_name}: "
                f"[{conf_color}]confidence={result.confidence:.0%}[/{conf_color}] | "
                f"context={opt_ctx.optimized_total_lines}L/{opt_ctx.original_total_lines}L "
                f"({opt_ctx.compression_ratio:.0%} compressed) | "
                f"~{opt_ctx.estimated_tokens} tokens"
            )

            progress.advance(task)

    # ── Step 6: Assemble Output ────────────────────────────────────
    console.print(f"\n[bold yellow]📦 Step 6: Assembling output in {output_dir}...[/bold yellow]")
    _assemble_output(results, output_dir, project_name)

    # ── Compute final stats ────────────────────────────────────────
    total_original_lines = sum(r.context_stats.original_total_lines for r in results)
    total_output_lines = sum(len(r.python_code.splitlines()) for r in results)
    avg_confidence = sum(r.confidence for r in results) / len(results) if results else 0
    avg_compression = sum(r.context_stats.compression_ratio for r in results) / len(results) if results else 0

    project_result = ProjectResult(
        project_name=project_name,
        source_dir=project_dir,
        output_dir=str(output_dir),
        files_parsed=files_parsed,
        files_failed=files_failed,
        methods_converted=len(results),
        methods_skipped=methods_skipped,
        functions=results,
        total_original_lines=total_original_lines,
        total_output_lines=total_output_lines,
        avg_confidence=avg_confidence,
        avg_compression_ratio=avg_compression,
    )

    _print_summary(project_result)
    return project_result


def _assemble_output(
    results: list[ModernizedFunction],
    output_dir: Path,
    project_name: str,
) -> None:
    """Assemble the converted Python code into output files."""

    # Group results by class name
    by_class: dict[str, list[ModernizedFunction]] = {}
    for r in results:
        cls = r.original_method.class_name
        by_class.setdefault(cls, []).append(r)

    for class_name, class_results in by_class.items():
        # Create a Python module for each Java class
        module_name = _to_snake_case(class_name) + ".py"
        module_path = output_dir / module_name

        lines = []
        lines.append(f'"""')
        lines.append(f"Modernized from Java class: {class_name}")
        lines.append(f"Auto-converted by FreshLine — Legacy Code Modernization Engine")
        lines.append(f'"""')
        lines.append("")

        for r in class_results:
            lines.append(f"# --- {r.original_method.qualified_name} ---")
            lines.append(f"# Confidence: {r.confidence:.0%}")
            if r.confidence_notes:
                lines.append(f"# Notes: {r.confidence_notes}")
            lines.append("")
            lines.append(r.python_code)
            lines.append("")
            lines.append("")

        module_path.write_text("\n".join(lines), encoding="utf-8")
        console.print(f"  ✓ {module_path.name}")

    # Write a conversion report
    report_path = output_dir / "CONVERSION_REPORT.md"
    report_lines = [
        f"# FreshLine Conversion Report: {project_name}",
        f"",
        f"## Summary",
        f"- Methods converted: {len(results)}",
        f"- Average confidence: {sum(r.confidence for r in results) / len(results):.0%}" if results else "- No methods converted",
        f"",
        f"## Per-Method Details",
        f"",
    ]

    for r in results:
        conf_emoji = "🟢" if r.confidence >= 0.8 else "🟡" if r.confidence >= 0.5 else "🔴"
        report_lines.append(f"### {conf_emoji} {r.original_method.qualified_name}")
        report_lines.append(f"- **Confidence**: {r.confidence:.0%}")
        report_lines.append(f"- **Context compression**: {r.context_stats.compression_ratio:.0%}")
        report_lines.append(f"- **Explanation**: {r.explanation}")
        if r.confidence_notes:
            report_lines.append(f"- **Notes**: {r.confidence_notes}")
        report_lines.append(f"- **Dependencies included**: {', '.join(r.context_stats.included_deps) or 'None'}")
        if r.context_stats.excluded_deps:
            report_lines.append(f"- **Dependencies excluded**: {', '.join(r.context_stats.excluded_deps)}")
        report_lines.append("")

    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    console.print(f"  ✓ {report_path.name}")


def _print_summary(result: ProjectResult) -> None:
    """Print final conversion summary."""
    conf_color = "green" if result.avg_confidence >= 0.8 else "yellow" if result.avg_confidence >= 0.5 else "red"

    summary = (
        f"[bold]Project:[/bold] {result.project_name}\n"
        f"[bold]Files parsed:[/bold] {result.files_parsed} (failed: {result.files_failed})\n"
        f"[bold]Methods converted:[/bold] {result.methods_converted} (skipped dead: {result.methods_skipped})\n"
        f"[bold]Avg confidence:[/bold] [{conf_color}]{result.avg_confidence:.0%}[/{conf_color}]\n"
        f"[bold]Avg compression:[/bold] {result.avg_compression_ratio:.0%}\n"
        f"[bold]Output:[/bold] {result.output_dir}"
    )

    console.print(Panel(summary, title="⚡ Conversion Complete", border_style="green"))


def _to_snake_case(name: str) -> str:
    """Convert PascalCase/camelCase to snake_case."""
    import re
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def analyze_project(project_dir: str) -> dict:
    """Analyze a project without converting — returns stats and graph data."""
    console.print(Panel(
        f"[bold cyan]🔍 Analyzing: {Path(project_dir).name}[/bold cyan]",
        border_style="cyan"
    ))

    parsed_files = parse_project(project_dir)

    dep_graph = DependencyGraph()
    dep_graph.build(parsed_files)

    dead_methods = detect_dead_methods(parsed_files)
    noise_summary = get_noise_summary(parsed_files)

    return {
        "files": len(parsed_files),
        "classes": sum(len(pf.classes) for pf in parsed_files),
        "methods": sum(len(pf.all_methods) for pf in parsed_files),
        "dead_methods": len(dead_methods),
        "dead_method_names": [m.qualified_name for m in dead_methods],
        "noise": noise_summary,
        "graph": dep_graph.to_dict(),
        "graph_stats": dep_graph.get_stats(),
        "parsed_files": parsed_files,
    }
