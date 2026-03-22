"""
FreshLine CLI — Interactive terminal menu for the Legacy Code Modernization Engine.

Drop Java projects into uploads/ → Run from terminal → Get Python output in output/
"""

import sys
import os
from pathlib import Path

# Add project root to path so imports work when running directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, IntPrompt
from rich import box

from app.config import UPLOADS_DIR, OUTPUT_DIR, SAMPLES_DIR, GROQ_API_KEY, GROQ_MODEL
from app.engine.modernizer import modernize_project, analyze_project

console = Console()

BANNER = """
[bold cyan]
    ███████╗██████╗ ███████╗███████╗██╗  ██╗██╗     ██╗███╗   ██╗███████╗
    ██╔════╝██╔══██╗██╔════╝██╔════╝██║  ██║██║     ██║████╗  ██║██╔════╝
    █████╗  ██████╔╝█████╗  ███████╗███████║██║     ██║██╔██╗ ██║█████╗  
    ██╔══╝  ██╔══██╗██╔══╝  ╚════██║██╔══██║██║     ██║██║╚██╗██║██╔══╝  
    ██║     ██║  ██║███████╗███████║██║  ██║███████╗██║██║ ╚████║███████╗
    ╚═╝     ╚═╝  ╚═╝╚══════╝╚══════╝╚═╝  ╚═╝╚══════╝╚═╝╚═╝  ╚═══╝╚══════╝
[/bold cyan]
[dim]    Legacy Code Modernization Engine — Java → Python[/dim]
[dim]    Context Optimization • Dead Code Detection • LLM Conversion[/dim]
"""


def main():
    console.clear()
    console.print(BANNER)

    # Check API key
    if not GROQ_API_KEY or GROQ_API_KEY == "your_groq_api_key_here":
        console.print(Panel(
            "[bold red]GROQ_API_KEY not configured![/bold red]\n\n"
            "1. Get a free API key from [link=https://console.groq.com]console.groq.com[/link]\n"
            "2. Set it in [bold]freshline/.env[/bold]:\n"
            "   [cyan]GROQ_API_KEY=gsk_your_key_here[/cyan]",
            title="Setup Required",
            border_style="red"
        ))
        console.print()

    while True:
        _show_menu()
        choice = Prompt.ask("\n[bold cyan]Choose[/bold cyan]", default="0")

        if choice == "1":
            _list_projects()
        elif choice == "2":
            _analyze_project()
        elif choice == "3":
            _modernize_project()
        elif choice == "4":
            _view_outputs()
        elif choice == "5":
            _copy_sample()
        elif choice == "6":
            _show_settings()
        elif choice == "0":
            console.print("\n[bold cyan]Exiting.[/bold cyan]\n")
            break
        else:
            console.print("[red]Invalid choice. Try again.[/red]")


def _show_menu():
    table = Table(box=box.ROUNDED, border_style="cyan", show_header=False, padding=(0, 2))
    table.add_column("Option", style="bold cyan", width=6)
    table.add_column("Action", style="white")

    table.add_row("[1]", "List projects in uploads/")
    table.add_row("[2]", "Analyze project (parse + dep graph + dead code)")
    table.add_row("[3]", "Modernize project (Java -> Python)")
    table.add_row("[4]", "View output projects")
    table.add_row("[5]", "Copy sample project to uploads/")
    table.add_row("[6]", "Settings")
    table.add_row("[0]", "Exit")

    console.print(Panel(table, title="[bold]FRESHLINE MENU[/bold]", border_style="cyan"))


def _list_projects():
    console.print("\n[bold yellow]Projects in uploads/:[/bold yellow]")

    if not UPLOADS_DIR.exists():
        UPLOADS_DIR.mkdir(exist_ok=True)

    projects = [d for d in UPLOADS_DIR.iterdir() if d.is_dir()]

    if not projects:
        console.print("  [dim]No projects found. Drop a Java project folder into uploads/[/dim]")
        console.print(f"  [dim]Or use option [5] to copy the sample project.[/dim]")
        return

    table = Table(box=box.SIMPLE, show_header=True)
    table.add_column("#", style="cyan", width=4)
    table.add_column("Project", style="bold white")
    table.add_column(".java files", style="yellow", justify="right")
    table.add_column("Total lines", style="green", justify="right")

    for i, project_dir in enumerate(projects, 1):
        java_files = list(project_dir.rglob("*.java"))
        total_lines = 0
        for jf in java_files:
            try:
                total_lines += len(jf.read_text(encoding="utf-8", errors="replace").splitlines())
            except Exception:
                pass
        table.add_row(str(i), project_dir.name, str(len(java_files)), str(total_lines))

    console.print(table)


def _select_project() -> Path | None:
    """Let user pick a project from uploads/."""
    projects = [d for d in UPLOADS_DIR.iterdir() if d.is_dir()]

    if not projects:
        console.print("[red]No projects in uploads/. Add a Java project folder first.[/red]")
        return None

    _list_projects()
    try:
        idx = IntPrompt.ask("\n[bold]Select project #[/bold]", default=1)
        if 1 <= idx <= len(projects):
            return projects[idx - 1]
        else:
            console.print("[red]Invalid selection.[/red]")
            return None
    except Exception:
        return None


def _analyze_project():
    project_dir = _select_project()
    if project_dir is None:
        return

    console.print()
    result = analyze_project(str(project_dir))

    # Show detailed analysis
    table = Table(title=f"Analysis: {project_dir.name}", box=box.ROUNDED, border_style="cyan")
    table.add_column("Metric", style="bold white")
    table.add_column("Value", style="cyan", justify="right")

    table.add_row("Java files", str(result["files"]))
    table.add_row("Classes", str(result["classes"]))
    table.add_row("Methods", str(result["methods"]))
    table.add_row("Dead methods", f"[red]{result['dead_methods']}[/red]")
    table.add_row("Noise ratio", f"{result['noise']['noise_ratio']:.1%}")
    table.add_row("Noise lines", str(result['noise']['noise_lines']))
    table.add_row("Graph nodes", str(result['graph_stats']['total_nodes']))
    table.add_row("Graph edges", str(result['graph_stats']['total_edges']))
    table.add_row("Has cycles", "Yes" if result['graph_stats']['has_cycles'] else "No")

    console.print(table)

    if result["dead_methods"] > 0:
        console.print(f"\n[bold red]Dead methods (will be skipped during conversion):[/bold red]")
        for name in result["dead_method_names"]:
            console.print(f"  [dim]- {name}[/dim]")

    # Show dependency graph as text
    console.print(f"\n[bold yellow]Dependency Graph:[/bold yellow]")
    graph_data = result["graph"]
    for edge in graph_data["edges"][:20]:  # Show first 20 edges
        console.print(f"  {edge['source']} —[{edge['type']}]→ {edge['target']}")
    if len(graph_data["edges"]) > 20:
        console.print(f"  [dim]... and {len(graph_data['edges']) - 20} more edges[/dim]")


def _modernize_project():
    project_dir = _select_project()
    if project_dir is None:
        return

    # Check API key
    if not GROQ_API_KEY or GROQ_API_KEY == "your_groq_api_key_here":
        console.print("[bold red]Set GROQ_API_KEY in .env first![/bold red]")
        return

    skip_dead = Prompt.ask(
        "\n[bold]Skip dead code?[/bold]",
        choices=["y", "n"],
        default="y"
    ) == "y"

    console.print()

    try:
        result = modernize_project(
            project_dir=str(project_dir),
            skip_dead_code=skip_dead,
        )
        console.print(f"\n[bold green]Output saved to: {result.output_dir}[/bold green]")
    except Exception as e:
        console.print(f"\n[bold red]Error: {e}[/bold red]")
        import traceback
        console.print(traceback.format_exc())


def _view_outputs():
    console.print("\n[bold yellow]Output projects:[/bold yellow]")

    if not OUTPUT_DIR.exists():
        OUTPUT_DIR.mkdir(exist_ok=True)

    outputs = [d for d in OUTPUT_DIR.iterdir() if d.is_dir()]

    if not outputs:
        console.print("  [dim]No output projects yet. Run a modernization first.[/dim]")
        return

    for output_dir in outputs:
        py_files = list(output_dir.glob("*.py"))
        report = output_dir / "CONVERSION_REPORT.md"

        console.print(f"\n  [bold]{output_dir.name}/[/bold]")
        for pf in py_files:
            lines = len(pf.read_text(encoding="utf-8").splitlines())
            console.print(f"    - {pf.name} ({lines} lines)")
        if report.exists():
            console.print(f"    - CONVERSION_REPORT.md")

        # Ask if they want to view a file
        view = Prompt.ask(
            f"  View a file from {output_dir.name}?",
            choices=["y", "n"],
            default="n"
        )
        if view == "y":
            all_files = list(output_dir.iterdir())
            for i, f in enumerate(all_files, 1):
                console.print(f"    [{i}] {f.name}")
            try:
                idx = IntPrompt.ask("    File #", default=1)
                if 1 <= idx <= len(all_files):
                    content = all_files[idx-1].read_text(encoding="utf-8")
                    console.print(Panel(
                        content,
                        title=all_files[idx-1].name,
                        border_style="green"
                    ))
            except Exception:
                pass


def _copy_sample():
    """Copy the sample banking-app to uploads/."""
    import shutil

    sample_src = SAMPLES_DIR / "banking-app"
    if not sample_src.exists():
        console.print("[red]Sample project not found at samples/banking-app/[/red]")
        return

    dest = UPLOADS_DIR / "banking-app"
    if dest.exists():
        console.print("[yellow]banking-app already exists in uploads/. Overwrite?[/yellow]")
        overwrite = Prompt.ask("Overwrite?", choices=["y", "n"], default="n")
        if overwrite == "n":
            return
        shutil.rmtree(dest)

    shutil.copytree(sample_src, dest)
    console.print("[bold green]Copied sample banking-app to uploads/[/bold green]")


def _show_settings():
    table = Table(title="Settings", box=box.ROUNDED, border_style="cyan")
    table.add_column("Setting", style="bold white")
    table.add_column("Value", style="cyan")

    key_display = f"{GROQ_API_KEY[:8]}...{GROQ_API_KEY[-4:]}" if len(GROQ_API_KEY) > 12 else "[red]NOT SET[/red]"
    table.add_row("Groq API Key", key_display)
    table.add_row("Groq Model", GROQ_MODEL)
    table.add_row("Uploads Dir", str(UPLOADS_DIR))
    table.add_row("Output Dir", str(OUTPUT_DIR))
    table.add_row("Samples Dir", str(SAMPLES_DIR))

    console.print(table)


if __name__ == "__main__":
    main()
