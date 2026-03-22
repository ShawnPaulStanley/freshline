"""FreshLine Desktop GUI (Tkinter).

Run with:
    python -m app.gui
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import traceback
from pathlib import Path
from tkinter import Tk, StringVar, BooleanVar, END
from tkinter import ttk, filedialog, messagebox
from tkinter import simpledialog
from tkinter.scrolledtext import ScrolledText

from app.config import UPLOADS_DIR, OUTPUT_DIR, SAMPLES_DIR, GROQ_API_KEY
from app.engine.modernizer import analyze_project, modernize_project


class FreshLineGUI:
    def __init__(self, root: Tk):
        self.root = root
        self.root.title("FreshLine")
        self.root.geometry("1000x700")

        self.project_var = StringVar()
        self.skip_dead_var = BooleanVar(value=True)
        self.status_var = StringVar(value="Ready")
        self._busy = False

        self._build_ui()
        self.refresh_projects()
        self._show_startup_info()

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=12)
        container.pack(fill="both", expand=True)

        title = ttk.Label(
            container,
            text="FreshLine",
            font=("Segoe UI", 14, "bold"),
        )
        title.pack(anchor="w", pady=(0, 10))

        proj_frame = ttk.LabelFrame(container, text="Project", padding=10)
        proj_frame.pack(fill="x", pady=(0, 8))

        ttk.Label(proj_frame, text="Uploads project:").grid(row=0, column=0, sticky="w", padx=(0, 8))

        self.project_combo = ttk.Combobox(
            proj_frame,
            textvariable=self.project_var,
            state="readonly",
            width=50,
        )
        self.project_combo.grid(row=0, column=1, sticky="ew")

        ttk.Button(proj_frame, text="Refresh", command=self.refresh_projects).grid(
            row=0, column=2, padx=(8, 0)
        )
        ttk.Button(proj_frame, text="Import Folder...", command=self.import_project_folder).grid(
            row=0, column=3, padx=(8, 0)
        )
        ttk.Button(proj_frame, text="Import GitHub...", command=self.import_github_project).grid(
            row=0, column=4, padx=(8, 0)
        )
        ttk.Button(proj_frame, text="Copy Sample", command=self.copy_sample_project).grid(
            row=0, column=5, padx=(8, 0)
        )

        proj_frame.columnconfigure(1, weight=1)

        action_frame = ttk.LabelFrame(container, text="Actions", padding=10)
        action_frame.pack(fill="x", pady=(0, 8))

        ttk.Checkbutton(
            action_frame,
            text="Skip dead code during modernization",
            variable=self.skip_dead_var,
        ).grid(row=0, column=0, sticky="w", padx=(0, 12))

        ttk.Button(action_frame, text="Analyze", command=self.analyze_selected).grid(row=0, column=1, padx=4)
        ttk.Button(action_frame, text="Modernize", command=self.modernize_selected).grid(row=0, column=2, padx=4)
        ttk.Button(action_frame, text="Open uploads", command=lambda: self.open_folder(UPLOADS_DIR)).grid(
            row=0, column=3, padx=4
        )
        ttk.Button(action_frame, text="Open output", command=lambda: self.open_folder(OUTPUT_DIR)).grid(
            row=0, column=4, padx=4
        )

        logs_frame = ttk.LabelFrame(container, text="Output", padding=8)
        logs_frame.pack(fill="both", expand=True)

        self.logs = ScrolledText(logs_frame, wrap="word", height=25, font=("Consolas", 10))
        self.logs.pack(fill="both", expand=True)

        bottom = ttk.Frame(container)
        bottom.pack(fill="x", pady=(8, 0))
        ttk.Label(bottom, textvariable=self.status_var).pack(side="left")
        ttk.Button(bottom, text="Clear output", command=self.clear_logs).pack(side="right")

    def _show_startup_info(self) -> None:
        self.log(f"Uploads dir: {UPLOADS_DIR}")
        self.log(f"Output dir : {OUTPUT_DIR}")
        if not GROQ_API_KEY:
            self.log("WARNING: GROQ_API_KEY is not set. Analyze works, modernize will fail until configured.")

    def log(self, message: str) -> None:
        self.logs.insert(END, message + "\n")
        self.logs.see(END)

    def clear_logs(self) -> None:
        self.logs.delete("1.0", END)

    def refresh_projects(self) -> None:
        projects = sorted([d.name for d in UPLOADS_DIR.iterdir() if d.is_dir()])
        self.project_combo["values"] = projects
        if projects:
            if self.project_var.get() not in projects:
                self.project_var.set(projects[0])
            self.status_var.set(f"Ready - {len(projects)} project(s) in uploads")
        else:
            self.project_var.set("")
            self.status_var.set("Ready - No projects in uploads")

    def import_project_folder(self) -> None:
        source = filedialog.askdirectory(title="Select Java project folder")
        if not source:
            return

        src_path = Path(source)
        dest = UPLOADS_DIR / src_path.name

        try:
            if dest.exists():
                overwrite = messagebox.askyesno(
                    "Overwrite project?",
                    f"{dest.name} already exists in uploads/. Overwrite it?",
                )
                if not overwrite:
                    return
                shutil.rmtree(dest)

            shutil.copytree(src_path, dest)
            self.log(f"Imported project: {dest.name}")
            self.refresh_projects()
            self.project_var.set(dest.name)
        except Exception as exc:
            messagebox.showerror("Import failed", str(exc))

    def copy_sample_project(self) -> None:
        sample_src = SAMPLES_DIR / "banking-app"
        if not sample_src.exists():
            messagebox.showerror("Missing sample", "Could not find samples/banking-app")
            return

        dest = UPLOADS_DIR / "banking-app"
        try:
            if dest.exists():
                overwrite = messagebox.askyesno(
                    "Overwrite sample?",
                    "banking-app already exists in uploads/. Overwrite it?",
                )
                if not overwrite:
                    return
                shutil.rmtree(dest)

            shutil.copytree(sample_src, dest)
            self.log("Copied sample project: banking-app")
            self.refresh_projects()
            self.project_var.set("banking-app")
        except Exception as exc:
            messagebox.showerror("Copy sample failed", str(exc))

    def import_github_project(self) -> None:
        if self._busy:
            messagebox.showinfo("Busy", "Another task is running. Please wait.")
            return

        repo_url = simpledialog.askstring(
            "Import from GitHub",
            "Enter GitHub repository URL:\nExample: https://github.com/owner/repo",
            parent=self.root,
        )
        if not repo_url:
            return

        repo_url = repo_url.strip()
        repo_name = self._repo_name_from_url(repo_url)
        if not repo_name:
            messagebox.showerror("Invalid URL", "Could not determine repository name from URL.")
            return

        if shutil.which("git") is None:
            messagebox.showerror("Git not found", "Git is required to import from GitHub.")
            return

        destination = UPLOADS_DIR / repo_name
        if destination.exists():
            overwrite = messagebox.askyesno(
                "Overwrite project?",
                f"{repo_name} already exists in uploads/. Overwrite it?",
            )
            if not overwrite:
                return

        def job() -> str:
            if destination.exists():
                shutil.rmtree(destination)

            proc = subprocess.run(
                ["git", "clone", repo_url, str(destination)],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:
                details = proc.stderr.strip() or proc.stdout.strip() or "git clone failed"
                raise RuntimeError(details)

            return f"Imported GitHub project: {repo_name}\n  URL: {repo_url}\n  Destination: {destination}"

        self._run_background(
            title=f"Importing GitHub project {repo_name}",
            work=job,
            on_success=lambda: self._select_project(repo_name),
        )

    def _repo_name_from_url(self, repo_url: str) -> str:
        normalized = repo_url.rstrip("/")
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

    def _select_project(self, project_name: str) -> None:
        self.refresh_projects()
        values = set(self.project_combo["values"])
        if project_name in values:
            self.project_var.set(project_name)

    def _selected_project_path(self) -> Path | None:
        project_name = self.project_var.get().strip()
        if not project_name:
            messagebox.showwarning("No project selected", "Pick a project from uploads first.")
            return None
        project_path = UPLOADS_DIR / project_name
        if not project_path.exists():
            messagebox.showerror("Project not found", f"{project_path} does not exist.")
            return None
        return project_path

    def _count_java_files(self, project_path: Path) -> int:
        return sum(1 for _ in project_path.rglob("*.java"))

    def analyze_selected(self) -> None:
        project_path = self._selected_project_path()
        if project_path is None:
            return

        java_count = self._count_java_files(project_path)
        if java_count == 0:
            message = (
                f"No .java files found in {project_path.name}.\n\n"
                "FreshLine currently analyzes and modernizes Java projects only."
            )
            self.log(f"Analyze skipped: {project_path.name} has no .java files")
            messagebox.showinfo("No Java files", message)
            return

        def job() -> str:
            result = analyze_project(str(project_path))
            dead_preview = ", ".join(result["dead_method_names"][:10])
            if len(result["dead_method_names"]) > 10:
                dead_preview += ", ..."

            return (
                f"Analyze complete: {project_path.name}\n"
                f"  Files: {result['files']}\n"
                f"  Classes: {result['classes']}\n"
                f"  Methods: {result['methods']}\n"
                f"  Dead methods: {result['dead_methods']}\n"
                f"  Noise ratio: {result['noise']['noise_ratio']:.1%}\n"
                f"  Graph nodes/edges: {result['graph_stats']['total_nodes']}/{result['graph_stats']['total_edges']}\n"
                f"  Graph cycles: {'Yes' if result['graph_stats']['has_cycles'] else 'No'}\n"
                f"  Dead method names: {dead_preview if dead_preview else 'None'}"
            )

        self._run_background(
            title=f"Analyzing {project_path.name}",
            work=job,
        )

    def modernize_selected(self) -> None:
        project_path = self._selected_project_path()
        if project_path is None:
            return

        java_count = self._count_java_files(project_path)
        if java_count == 0:
            message = (
                f"No .java files found in {project_path.name}.\n\n"
                "FreshLine currently modernizes Java projects only."
            )
            self.log(f"Modernize skipped: {project_path.name} has no .java files")
            messagebox.showinfo("No Java files", message)
            return

        skip_dead = self.skip_dead_var.get()

        def job() -> str:
            result = modernize_project(
                project_dir=str(project_path),
                skip_dead_code=skip_dead,
            )
            return (
                f"Modernization complete: {result.project_name}\n"
                f"  Files parsed: {result.files_parsed} (failed: {result.files_failed})\n"
                f"  Methods converted: {result.methods_converted}\n"
                f"  Methods skipped: {result.methods_skipped}\n"
                f"  Avg confidence: {result.avg_confidence:.0%}\n"
                f"  Avg compression: {result.avg_compression_ratio:.0%}\n"
                f"  Output: {result.output_dir}"
            )

        self._run_background(
            title=f"Modernizing {project_path.name}",
            work=job,
            on_success=lambda: self.open_folder(OUTPUT_DIR),
        )

    def _run_background(self, title: str, work, on_success=None) -> None:
        if self._busy:
            messagebox.showinfo("Busy", "Another task is running. Please wait.")
            return

        self._busy = True
        self.status_var.set(f"Running - {title}")
        self.log(f"\n=== {title} ===")

        def runner() -> None:
            try:
                result_text = work()
                self.root.after(0, lambda: self._on_job_done(result_text, on_success))
            except Exception as exc:
                error = f"{exc}\n\n{traceback.format_exc()}"
                self.root.after(0, lambda: self._on_job_error(error))

        threading.Thread(target=runner, daemon=True).start()

    def _on_job_done(self, message: str, on_success=None) -> None:
        self.log(message)
        self.status_var.set("Ready")
        self._busy = False
        if on_success:
            try:
                on_success()
            except Exception:
                pass

    def _on_job_error(self, error_text: str) -> None:
        self.log("Task failed:")
        self.log(error_text)
        self.status_var.set("Ready - Task failed")
        self._busy = False
        messagebox.showerror("Task failed", "See output panel for details.")

    def open_folder(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(str(path))
        else:
            self.log(f"Open folder manually: {path}")


def main() -> None:
    root = Tk()
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    app = FreshLineGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
