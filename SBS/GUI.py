"""
SBS/GUI.py — Graphical User Interface for Game Image Analyzer
=============================================================
Provides the GameImageAnalyzerGUI class: a full-featured desktop application
built with CustomTkinter that exposes every pipeline step through an
intuitive, modern dark-mode interface.

Layout
------
  ┌─ Header ──────────────────────────────────────────────────┐
  │ Game Image Analyzer                                        │
  ├─ Sidebar ──┬─ Content ──────────────────────────────────── │
  │ Full Run   │                                               │
  │ Scan       │   (active panel)                              │
  │ Charts     │                                               │
  │ Overviews  │                                               │
  │ Report     │                                               │
  │ Type Anal. │                                               │
  ├────────────┴───────────────────────────────────────────── │
  │ Log output                               [Clear] [Copy]   │
  └────────────────────────────────────────────────────────── ┘

Threading
---------
Every analysis operation runs in a daemon thread so the UI stays responsive.
stdout is redirected through a thread-safe queue that is drained on a 100 ms
timer and written to the log panel.

Classes
-------
  LogRedirector       — StringIO subclass that pipes writes to a Queue.
  _BrowseRow          — Reusable label + entry + Browse button widget.
  _SectionLabel       — Styled section header inside a panel.
  _ScanPanel          — UI for the 'scan' command.
  _ChartsPanel        — UI for the 'charts' command.
  _OverviewPanel      — UI for the 'overview' command.
  _ReportPanel        — UI for the 'report' command.
  _TypesPanel         — UI for the 'types' command.
  _FullPipelinePanel  — UI for the 'full' command (the home screen).
  GameImageAnalyzerGUI— Root application class; entry point via .run().

Dependencies: customtkinter, tkinter (stdlib)
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import queue
import sys
import io
from pathlib import Path


# ---------------------------------------------------------------------------
# Global appearance — set before any widgets are created
# ---------------------------------------------------------------------------
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Accent colors used throughout the UI
_ACCENT       = "#3B8ED0"   # CTk default blue
_ACCENT_HOVER = "#2E6DAD"
_SIDEBAR_BG   = "#1a1a2e"
_HEADER_BG    = "#16213e"
_SUCCESS      = "#2ecc71"
_WARNING      = "#e67e22"
_ERROR        = "#e74c3c"


# ---------------------------------------------------------------------------
# Helper: thread-safe stdout redirector
# ---------------------------------------------------------------------------

class LogRedirector(io.StringIO):
    """
    Redirects print() and sys.stdout output to a thread-safe queue.

    The GUI polls the queue every 100 ms on the main thread and appends
    any new text to the log textbox.

    Attributes:
        _queue (queue.Queue): Shared queue between worker threads and the
            main thread's log-drain timer.
    """

    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self._queue = log_queue

    def write(self, text: str):
        """Put non-empty text onto the queue for the UI to display."""
        if text and text.strip():
            self._queue.put(text)

    def flush(self):
        """No-op — required by the file-like interface."""
        pass


# ---------------------------------------------------------------------------
# Reusable composite widgets
# ---------------------------------------------------------------------------

class _BrowseRow(ctk.CTkFrame):
    """
    A single-line composite widget: [Label]  [Entry field]  [Browse button].

    Supports both directory and file selection dialogs.

    Args:
        parent:       Parent widget.
        label (str):  Text shown to the left of the entry.
        mode  (str):  'directory' opens a folder chooser,
                      'file'      opens a file chooser.
        file_types:   List of (description, pattern) tuples passed to
                      filedialog.askopenfilename().  Only used when
                      mode == 'file'.
    """

    def __init__(
        self,
        parent,
        label: str,
        mode: str = "directory",
        file_types: list = None,
        **kwargs,
    ):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._mode       = mode
        self._file_types = file_types or [("All files", "*.*")]

        ctk.CTkLabel(self, text=label, width=130, anchor="w",
                     font=ctk.CTkFont(size=13)).pack(side="left", padx=(0, 8))

        self._entry = ctk.CTkEntry(
            self, width=360, placeholder_text="Click Browse or type a path…",
            font=ctk.CTkFont(size=12),
        )
        self._entry.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            self, text="Browse", width=90,
            fg_color=_ACCENT, hover_color=_ACCENT_HOVER,
            command=self._browse,
        ).pack(side="left")

    def _browse(self):
        """Open the appropriate system dialog and populate the entry."""
        if self._mode == "directory":
            path = filedialog.askdirectory(title="Select Folder")
        else:
            path = filedialog.askopenfilename(
                title="Select File", filetypes=self._file_types
            )
        if path:
            self.set(path)

    def get(self) -> str:
        """Return the current entry value, stripped of whitespace."""
        return self._entry.get().strip()

    def set(self, value: str):
        """Set the entry field to value."""
        self._entry.delete(0, "end")
        self._entry.insert(0, value)


class _SectionLabel(ctk.CTkLabel):
    """A styled section-heading label with a subtle separator appearance."""

    def __init__(self, parent, text: str, **kwargs):
        super().__init__(
            parent, text=f"  {text}",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#8899aa",
            anchor="w",
            **kwargs,
        )


# ---------------------------------------------------------------------------
# Individual panel classes (one per pipeline step)
# ---------------------------------------------------------------------------

class _FullPipelinePanel(ctk.CTkScrollableFrame):
    """
    Home panel — runs the complete five-step analysis pipeline.

    This is the first panel shown on startup and is highlighted in the
    sidebar as the primary action.  All five steps (scan → charts →
    overviews → PDF report → optional type analysis) are triggered by a
    single 'Run Full Pipeline' button.
    """

    def __init__(self, parent, run_callback, **kwargs):
        """
        Args:
            parent:        Parent widget.
            run_callback:  Callable(args_dict) invoked when the user clicks Run.
        """
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._run = run_callback
        self._build()

    def _build(self):
        pad = {"padx": 24, "pady": 6, "sticky": "w"}

        ctk.CTkLabel(
            self, text="Full Analysis Pipeline",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, padx=24, pady=(20, 4), sticky="w")

        ctk.CTkLabel(
            self,
            text="Runs all five steps in sequence:\n"
                 "  1 · Scan images    2 · Generate charts    3 · Character overviews\n"
                 "  4 · PDF report     5 · Type analysis (optional)",
            font=ctk.CTkFont(size=12),
            text_color="#8899aa",
            justify="left",
        ).grid(row=1, column=0, columnspan=2, padx=24, pady=(0, 16), sticky="w")

        # --- Inputs ---
        _SectionLabel(self, "INPUT").grid(row=2, column=0, columnspan=2, **pad)

        self._input = _BrowseRow(self, "Image Folder", mode="directory")
        self._input.grid(row=3, column=0, columnspan=2, **pad)

        self._output = _BrowseRow(self, "Output Folder", mode="directory")
        self._output.grid(row=4, column=0, columnspan=2, **pad)

        ctk.CTkLabel(self, text="Project Name", width=130, anchor="w",
                     font=ctk.CTkFont(size=13)).grid(row=5, column=0, padx=24, pady=6, sticky="w")
        self._name = ctk.CTkEntry(self, width=360, placeholder_text='e.g. "My Game"',
                                   font=ctk.CTkFont(size=12))
        self._name.grid(row=5, column=1, padx=(0, 24), pady=6, sticky="w")

        # --- Type analysis (optional) ---
        _SectionLabel(self, "TYPE ANALYSIS  (optional)").grid(
            row=6, column=0, columnspan=2, padx=24, pady=(16, 4), sticky="w"
        )

        self._type_file = _BrowseRow(
            self, "Type Data CSV/JSON", mode="file",
            file_types=[("CSV / JSON", "*.csv *.json"), ("All files", "*.*")],
        )
        self._type_file.grid(row=7, column=0, columnspan=2, **pad)

        self._fetch_api = ctk.CTkSwitch(
            self, text="Fetch character types from external API",
            font=ctk.CTkFont(size=12),
        )
        self._fetch_api.grid(row=8, column=0, columnspan=2, padx=24, pady=(4, 16), sticky="w")

        # --- Run button ---
        self._run_btn = ctk.CTkButton(
            self, text="▶   Run Full Pipeline",
            font=ctk.CTkFont(size=15, weight="bold"),
            height=44, width=300,
            fg_color=_ACCENT, hover_color=_ACCENT_HOVER,
            command=self._on_run,
        )
        self._run_btn.grid(row=9, column=0, columnspan=2, padx=24, pady=8, sticky="w")

        self._status = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=12), text_color=_SUCCESS
        )
        self._status.grid(row=10, column=0, columnspan=2, padx=24, pady=(0, 16), sticky="w")

    def _on_run(self):
        input_dir = self._input.get()
        output_dir = self._output.get()

        if not input_dir:
            messagebox.showerror("Missing Input", "Please select an Image Folder.")
            return
        if not Path(input_dir).exists():
            messagebox.showerror("Invalid Path", f"Image folder does not exist:\n{input_dir}")
            return
        if not output_dir:
            messagebox.showerror("Missing Output", "Please select an Output Folder.")
            return

        self._run_btn.configure(state="disabled", text="⏳  Running…")
        self._status.configure(text="")
        self._run(
            {
                "command":      "full",
                "input":        input_dir,
                "output":       output_dir,
                "name":         self._name.get() or None,
                "type_data":    self._type_file.get() or None,
                "fetch_api": bool(self._fetch_api.get()),
            },
            done_callback=lambda ok: self._on_done(ok),
        )

    def _on_done(self, success: bool):
        self._run_btn.configure(state="normal", text="▶   Run Full Pipeline")
        if success:
            self._status.configure(text="✔  Pipeline complete!", text_color=_SUCCESS)
        else:
            self._status.configure(text="✖  An error occurred — see log below.", text_color=_ERROR)


class _ScanPanel(ctk.CTkScrollableFrame):
    """Panel for the 'scan' subcommand."""

    def __init__(self, parent, run_callback, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._run = run_callback
        self._build()

    def _build(self):
        pad = {"padx": 24, "pady": 6, "sticky": "w"}

        ctk.CTkLabel(self, text="Scan Images",
                     font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, columnspan=2, padx=24, pady=(20, 4), sticky="w")
        ctk.CTkLabel(
            self,
            text="Analyzes every image in a folder (or a single file) and writes\n"
                 "color and shape data to scan_results.csv.",
            font=ctk.CTkFont(size=12), text_color="#8899aa", justify="left",
        ).grid(row=1, column=0, columnspan=2, padx=24, pady=(0, 16), sticky="w")

        _SectionLabel(self, "INPUT").grid(row=2, column=0, columnspan=2, **pad)

        self._input = _BrowseRow(self, "Image Folder/File", mode="directory")
        self._input.grid(row=3, column=0, columnspan=2, **pad)

        self._output = _BrowseRow(self, "Output Folder", mode="directory")
        self._output.grid(row=4, column=0, columnspan=2, **pad)

        ctk.CTkLabel(self, text="CSV Filename", width=130, anchor="w",
                     font=ctk.CTkFont(size=13)).grid(row=5, column=0, padx=24, pady=6, sticky="w")
        self._csv = ctk.CTkEntry(self, width=360, placeholder_text="scan_results.csv",
                                  font=ctk.CTkFont(size=12))
        self._csv.grid(row=5, column=1, padx=(0, 24), pady=6, sticky="w")

        ctk.CTkLabel(self, text="Single Image Name", width=130, anchor="w",
                     font=ctk.CTkFont(size=13)).grid(row=6, column=0, padx=24, pady=6, sticky="w")
        self._name = ctk.CTkEntry(self, width=360,
                                   placeholder_text='Optional — overrides filename as character name',
                                   font=ctk.CTkFont(size=12))
        self._name.grid(row=6, column=1, padx=(0, 24), pady=6, sticky="w")

        self._run_btn = ctk.CTkButton(
            self, text="▶   Scan",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=40, width=200, fg_color=_ACCENT, hover_color=_ACCENT_HOVER,
            command=self._on_run,
        )
        self._run_btn.grid(row=7, column=0, columnspan=2, padx=24, pady=16, sticky="w")

        self._status = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=12))
        self._status.grid(row=8, column=0, columnspan=2, padx=24, sticky="w")

    def _on_run(self):
        input_path = self._input.get()
        if not input_path:
            messagebox.showerror("Missing Input", "Please select an image folder or file.")
            return

        self._run_btn.configure(state="disabled", text="⏳  Scanning…")
        self._status.configure(text="")
        self._run(
            {
                "command": "scan",
                "input":   input_path,
                "output":  self._output.get() or "output",
                "csv":     self._csv.get() or "scan_results.csv",
                "name":    self._name.get() or None,
            },
            done_callback=lambda ok: self._finish(ok),
        )

    def _finish(self, success: bool):
        self._run_btn.configure(state="normal", text="▶   Scan")
        self._status.configure(
            text="✔  Done!" if success else "✖  Error — see log.",
            text_color=_SUCCESS if success else _ERROR,
        )


class _ChartsPanel(ctk.CTkScrollableFrame):
    """Panel for the 'charts' subcommand."""

    def __init__(self, parent, run_callback, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._run = run_callback
        self._build()

    def _build(self):
        pad = {"padx": 24, "pady": 6, "sticky": "w"}

        ctk.CTkLabel(self, text="Generate Charts",
                     font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, columnspan=2, padx=24, pady=(20, 4), sticky="w")
        ctk.CTkLabel(
            self,
            text="Generates static PNG and interactive HTML charts from scan results.\n"
                 "Both raw (unfiltered) and filtered versions are produced by default.",
            font=ctk.CTkFont(size=12), text_color="#8899aa", justify="left",
        ).grid(row=1, column=0, columnspan=2, padx=24, pady=(0, 16), sticky="w")

        _SectionLabel(self, "INPUT").grid(row=2, column=0, columnspan=2, **pad)

        self._csv = _BrowseRow(
            self, "Scan Results CSV", mode="file",
            file_types=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        self._csv.grid(row=3, column=0, columnspan=2, **pad)

        self._output = _BrowseRow(self, "Output Folder", mode="directory")
        self._output.grid(row=4, column=0, columnspan=2, **pad)

        _SectionLabel(self, "OPTIONS").grid(row=5, column=0, columnspan=2,
                                             padx=24, pady=(16, 4), sticky="w")

        self._mode = ctk.CTkSegmentedButton(
            self, values=["All (raw + filtered)", "Static PNG only", "Interactive HTML only"],
            font=ctk.CTkFont(size=12),
        )
        self._mode.set("All (raw + filtered)")
        self._mode.grid(row=6, column=0, columnspan=2, padx=24, pady=6, sticky="w")

        self._run_btn = ctk.CTkButton(
            self, text="▶   Generate Charts",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=40, width=220, fg_color=_ACCENT, hover_color=_ACCENT_HOVER,
            command=self._on_run,
        )
        self._run_btn.grid(row=7, column=0, columnspan=2, padx=24, pady=16, sticky="w")

        self._status = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=12))
        self._status.grid(row=8, column=0, columnspan=2, padx=24, sticky="w")

    def _on_run(self):
        csv_path = self._csv.get()
        if not csv_path:
            messagebox.showerror("Missing Input", "Please select a scan results CSV.")
            return

        mode = self._mode.get()
        self._run_btn.configure(state="disabled", text="⏳  Generating…")
        self._run(
            {
                "command":          "charts",
                "csv":              csv_path,
                "output":           self._output.get() or "output/charts",
                "static_only":      mode == "Static PNG only",
                "interactive_only": mode == "Interactive HTML only",
            },
            done_callback=lambda ok: self._finish(ok),
        )

    def _finish(self, success: bool):
        self._run_btn.configure(state="normal", text="▶   Generate Charts")
        self._status.configure(
            text="✔  Done!" if success else "✖  Error — see log.",
            text_color=_SUCCESS if success else _ERROR,
        )


class _OverviewPanel(ctk.CTkScrollableFrame):
    """Panel for the 'overview' subcommand."""

    def __init__(self, parent, run_callback, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._run = run_callback
        self._build()

    def _build(self):
        pad = {"padx": 24, "pady": 6, "sticky": "w"}

        ctk.CTkLabel(self, text="Character Overviews",
                     font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, columnspan=2, padx=24, pady=(20, 4), sticky="w")
        ctk.CTkLabel(
            self,
            text="Generates a per-character dashboard (PNG + HTML) combining\n"
                 "the original image with its color and shape breakdown.",
            font=ctk.CTkFont(size=12), text_color="#8899aa", justify="left",
        ).grid(row=1, column=0, columnspan=2, padx=24, pady=(0, 16), sticky="w")

        _SectionLabel(self, "INPUT").grid(row=2, column=0, columnspan=2, **pad)

        self._csv = _BrowseRow(
            self, "Scan Results CSV", mode="file",
            file_types=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        self._csv.grid(row=3, column=0, columnspan=2, **pad)

        self._output = _BrowseRow(self, "Output Folder", mode="directory")
        self._output.grid(row=4, column=0, columnspan=2, **pad)

        _SectionLabel(self, "TARGET").grid(row=5, column=0, columnspan=2,
                                            padx=24, pady=(16, 4), sticky="w")

        self._target = ctk.CTkSegmentedButton(
            self, values=["All characters", "Single character", "Compare characters"],
            command=self._on_target_change, font=ctk.CTkFont(size=12),
        )
        self._target.set("All characters")
        self._target.grid(row=6, column=0, columnspan=2, padx=24, pady=6, sticky="w")

        # Single character entry (hidden by default)
        self._char_frame = ctk.CTkFrame(self, fg_color="transparent")
        ctk.CTkLabel(self._char_frame, text="Character Name", width=130, anchor="w",
                     font=ctk.CTkFont(size=13)).pack(side="left", padx=(0, 8))
        self._char_name = ctk.CTkEntry(self._char_frame, width=360,
                                        placeholder_text='e.g. "Pikachu"',
                                        font=ctk.CTkFont(size=12))
        self._char_name.pack(side="left")
        # hidden initially

        # Compare entry (hidden by default)
        self._compare_frame = ctk.CTkFrame(self, fg_color="transparent")
        ctk.CTkLabel(self._compare_frame, text="Character Names", width=130, anchor="w",
                     font=ctk.CTkFont(size=13)).pack(side="left", padx=(0, 8))
        self._compare_names = ctk.CTkEntry(
            self._compare_frame, width=360,
            placeholder_text='Space-separated, e.g. "Pikachu Charizard Mewtwo"',
            font=ctk.CTkFont(size=12),
        )
        self._compare_names.pack(side="left")
        # hidden initially

        _SectionLabel(self, "FORMAT").grid(row=9, column=0, columnspan=2,
                                            padx=24, pady=(16, 4), sticky="w")

        self._fmt = ctk.CTkSegmentedButton(
            self, values=["Static + Interactive", "Static PNG only", "Interactive HTML only"],
            font=ctk.CTkFont(size=12),
        )
        self._fmt.set("Static + Interactive")
        self._fmt.grid(row=10, column=0, columnspan=2, padx=24, pady=6, sticky="w")

        self._run_btn = ctk.CTkButton(
            self, text="▶   Generate Overviews",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=40, width=240, fg_color=_ACCENT, hover_color=_ACCENT_HOVER,
            command=self._on_run,
        )
        self._run_btn.grid(row=11, column=0, columnspan=2, padx=24, pady=16, sticky="w")

        self._status = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=12))
        self._status.grid(row=12, column=0, columnspan=2, padx=24, sticky="w")

    def _on_target_change(self, value: str):
        # Show/hide the conditional input rows
        if value == "Single character":
            self._char_frame.grid(row=7, column=0, columnspan=2, padx=24, pady=6, sticky="w")
            self._compare_frame.grid_forget()
        elif value == "Compare characters":
            self._compare_frame.grid(row=7, column=0, columnspan=2, padx=24, pady=6, sticky="w")
            self._char_frame.grid_forget()
        else:
            self._char_frame.grid_forget()
            self._compare_frame.grid_forget()

    def _on_run(self):
        csv_path = self._csv.get()
        if not csv_path:
            messagebox.showerror("Missing Input", "Please select a scan results CSV.")
            return

        target   = self._target.get()
        fmt      = self._fmt.get()
        args = {
            "command":          "overview",
            "csv":              csv_path,
            "output":           self._output.get() or "output/overviews",
            "all":              target == "All characters",
            "name":             self._char_name.get() if target == "Single character" else None,
            "compare":          self._compare_names.get().split() if target == "Compare characters" else None,
            "index":            None,
            "static_only":      fmt == "Static PNG only",
            "interactive_only": fmt == "Interactive HTML only",
        }

        self._run_btn.configure(state="disabled", text="⏳  Generating…")
        self._run(args, done_callback=lambda ok: self._finish(ok))

    def _finish(self, success: bool):
        self._run_btn.configure(state="normal", text="▶   Generate Overviews")
        self._status.configure(
            text="✔  Done!" if success else "✖  Error — see log.",
            text_color=_SUCCESS if success else _ERROR,
        )


class _ReportPanel(ctk.CTkScrollableFrame):
    """Panel for the 'report' subcommand."""

    def __init__(self, parent, run_callback, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._run = run_callback
        self._build()

    def _build(self):
        pad = {"padx": 24, "pady": 6, "sticky": "w"}

        ctk.CTkLabel(self, text="PDF Summary Report",
                     font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, columnspan=2, padx=24, pady=(20, 4), sticky="w")
        ctk.CTkLabel(
            self,
            text="Compiles a single-page professional PDF report with overview\n"
                 "statistics, top colors, shape distribution, and key insights.",
            font=ctk.CTkFont(size=12), text_color="#8899aa", justify="left",
        ).grid(row=1, column=0, columnspan=2, padx=24, pady=(0, 16), sticky="w")

        _SectionLabel(self, "INPUT").grid(row=2, column=0, columnspan=2, **pad)

        self._csv = _BrowseRow(
            self, "Scan Results CSV", mode="file",
            file_types=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        self._csv.grid(row=3, column=0, columnspan=2, **pad)

        self._output = _BrowseRow(self, "Output Folder", mode="directory")
        self._output.grid(row=4, column=0, columnspan=2, **pad)

        ctk.CTkLabel(self, text="Project Name", width=130, anchor="w",
                     font=ctk.CTkFont(size=13)).grid(row=5, column=0, padx=24, pady=6, sticky="w")
        self._name = ctk.CTkEntry(self, width=360,
                                   placeholder_text='e.g. "My Game"',
                                   font=ctk.CTkFont(size=12))
        self._name.grid(row=5, column=1, padx=(0, 24), pady=6, sticky="w")

        ctk.CTkLabel(self, text="PDF Filename", width=130, anchor="w",
                     font=ctk.CTkFont(size=13)).grid(row=6, column=0, padx=24, pady=6, sticky="w")
        self._filename = ctk.CTkEntry(self, width=360,
                                       placeholder_text="Leave blank for auto-name",
                                       font=ctk.CTkFont(size=12))
        self._filename.grid(row=6, column=1, padx=(0, 24), pady=6, sticky="w")

        self._run_btn = ctk.CTkButton(
            self, text="▶   Generate Report",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=40, width=220, fg_color=_ACCENT, hover_color=_ACCENT_HOVER,
            command=self._on_run,
        )
        self._run_btn.grid(row=7, column=0, columnspan=2, padx=24, pady=16, sticky="w")

        self._status = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=12))
        self._status.grid(row=8, column=0, columnspan=2, padx=24, sticky="w")

    def _on_run(self):
        csv_path = self._csv.get()
        if not csv_path:
            messagebox.showerror("Missing Input", "Please select a scan results CSV.")
            return
        self._run_btn.configure(state="disabled", text="⏳  Generating…")
        self._run(
            {
                "command":  "report",
                "csv":      csv_path,
                "output":   self._output.get() or "output",
                "name":     self._name.get() or None,
                "filename": self._filename.get() or None,
            },
            done_callback=lambda ok: self._finish(ok),
        )

    def _finish(self, success: bool):
        self._run_btn.configure(state="normal", text="▶   Generate Report")
        self._status.configure(
            text="✔  Done!" if success else "✖  Error — see log.",
            text_color=_SUCCESS if success else _ERROR,
        )


class _TypesPanel(ctk.CTkScrollableFrame):
    """Panel for the 'types' subcommand."""

    def __init__(self, parent, run_callback, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._run = run_callback
        self._build()

    def _build(self):
        pad = {"padx": 24, "pady": 6, "sticky": "w"}

        ctk.CTkLabel(self, text="Type Analysis",
                     font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, columnspan=2, padx=24, pady=(20, 4), sticky="w")
        ctk.CTkLabel(
            self,
            text="Correlates character types / attributes with detected visual\n"
                 "properties (colors, shapes).  Supports any game via custom CSV.",
            font=ctk.CTkFont(size=12), text_color="#8899aa", justify="left",
        ).grid(row=1, column=0, columnspan=2, padx=24, pady=(0, 16), sticky="w")

        _SectionLabel(self, "INPUT").grid(row=2, column=0, columnspan=2, **pad)

        self._csv = _BrowseRow(
            self, "Scan Results CSV", mode="file",
            file_types=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        self._csv.grid(row=3, column=0, columnspan=2, **pad)

        self._output = _BrowseRow(self, "Output Folder", mode="directory")
        self._output.grid(row=4, column=0, columnspan=2, **pad)

        ctk.CTkLabel(self, text="Project Name", width=130, anchor="w",
                     font=ctk.CTkFont(size=13)).grid(row=5, column=0, padx=24, pady=6, sticky="w")
        self._name = ctk.CTkEntry(self, width=360,
                                   placeholder_text='e.g. "My Game"',
                                   font=ctk.CTkFont(size=12))
        self._name.grid(row=5, column=1, padx=(0, 24), pady=6, sticky="w")

        _SectionLabel(self, "TYPE DATA SOURCE").grid(row=6, column=0, columnspan=2,
                                                       padx=24, pady=(16, 4), sticky="w")

        self._type_file = _BrowseRow(
            self, "Type Data CSV/JSON", mode="file",
            file_types=[("CSV / JSON", "*.csv *.json"), ("All files", "*.*")],
        )
        self._type_file.grid(row=7, column=0, columnspan=2, **pad)

        self._fetch_api = ctk.CTkSwitch(
            self, text="Fetch character types from external API",
            font=ctk.CTkFont(size=12),
        )
        self._fetch_api.grid(row=8, column=0, columnspan=2, padx=24, pady=4, sticky="w")

        self._save_types = _BrowseRow(self, "Save fetched types to", mode="file",
                                       file_types=[("CSV files", "*.csv")])
        self._save_types.grid(row=9, column=0, columnspan=2, **pad)

        self._run_btn = ctk.CTkButton(
            self, text="▶   Run Type Analysis",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=40, width=230, fg_color=_ACCENT, hover_color=_ACCENT_HOVER,
            command=self._on_run,
        )
        self._run_btn.grid(row=10, column=0, columnspan=2, padx=24, pady=16, sticky="w")

        self._status = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=12))
        self._status.grid(row=11, column=0, columnspan=2, padx=24, sticky="w")

    def _on_run(self):
        csv_path = self._csv.get()
        if not csv_path:
            messagebox.showerror("Missing Input", "Please select a scan results CSV.")
            return
        if not self._type_file.get() and not self._fetch_api.get():
            messagebox.showerror(
                "No Type Data",
                "Please provide a type data CSV/JSON or enable 'Fetch from external API'.",
            )
            return

        self._run_btn.configure(state="disabled", text="⏳  Analyzing…")
        self._run(
            {
                "command":       "types",
                "csv":           csv_path,
                "output":        self._output.get() or "output/analysis",
                "name":          self._name.get() or "Character",
                "type_data":     self._type_file.get() or None,
                "fetch_api":  bool(self._fetch_api.get()),
                "save_types": self._save_types.get() or None,
            },
            done_callback=lambda ok: self._finish(ok),
        )

    def _finish(self, success: bool):
        self._run_btn.configure(state="normal", text="▶   Run Type Analysis")
        self._status.configure(
            text="✔  Done!" if success else "✖  Error — see log.",
            text_color=_SUCCESS if success else _ERROR,
        )


# ---------------------------------------------------------------------------
# Main application class
# ---------------------------------------------------------------------------

class GameImageAnalyzerGUI(ctk.CTk):
    """
    Root application window for the Game Image Analyzer GUI.

    Responsibilities:
      - Build and lay out the sidebar, content area, and log panel.
      - Own the navigation state (which panel is visible).
      - Own the log queue and the periodic drain timer.
      - Dispatch analysis commands to worker threads, redirecting stdout
        to the log panel for the duration of the operation.

    Usage::

        if __name__ == "__main__":
            app = GameImageAnalyzerGUI()
            app.run()
    """

    # Navigation items: (display label, panel class)
    _NAV_ITEMS = [
        ("⚡  Full Pipeline",  _FullPipelinePanel),
        ("🔍  Scan Images",     _ScanPanel),
        ("📊  Charts",          _ChartsPanel),
        ("🖼   Overviews",      _OverviewPanel),
        ("📄  PDF Report",      _ReportPanel),
        ("🧬  Type Analysis",   _TypesPanel),
    ]

    def __init__(self):
        super().__init__()

        self.title("Game Image Analyzer")
        self.geometry("1100x780")
        self.minsize(900, 640)

        # Taskbar / title-bar icon
        # On Windows, iconbitmap() with an .ico file is the only reliable way
        # to set the taskbar icon.  We convert the PNG to a temporary ICO at
        # startup using Pillow (already a project dependency).
        _icon_path = Path(__file__).parent.parent / "assets" / "app_icon.png"
        if _icon_path.exists():
            try:
                import tempfile
                from PIL import Image as _PILImage
                _ico_fd, _ico_path = tempfile.mkstemp(suffix=".ico")
                import os as _os
                _os.close(_ico_fd)
                _PILImage.open(_icon_path).save(_ico_path, format="ICO",
                                                sizes=[(256, 256), (48, 48), (32, 32), (16, 16)])
                self.iconbitmap(_ico_path)
            except Exception:
                # Fallback: title-bar only (non-Windows or PIL unavailable)
                self._icon_img = tk.PhotoImage(file=str(_icon_path))
                self.iconphoto(True, self._icon_img)

        self._log_queue:  queue.Queue = queue.Queue()
        self._active_nav: int = 0        # index into _NAV_ITEMS
        self._nav_buttons: list = []
        self._panels:      dict = {}     # label → panel widget

        self._build_ui()
        self._switch_panel(0)
        self._start_log_drain()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        """Construct the three main regions: header, body, log panel."""
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_body()
        self._build_log_panel()

    def _build_header(self):
        """Top bar with application title and appearance toggle."""
        header = ctk.CTkFrame(self, fg_color=_HEADER_BG, corner_radius=0, height=52)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            header,
            text="  Game Image Analyzer",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color="white",
        ).grid(row=0, column=0, padx=12, pady=12, sticky="w")

        ctk.CTkLabel(
            header,
            text="Color · Shape · Type  Analysis Toolkit",
            font=ctk.CTkFont(size=11),
            text_color="#8899aa",
        ).grid(row=0, column=1, padx=0, pady=12, sticky="w")

        self._theme_switch = ctk.CTkSwitch(
            header, text="Dark mode",
            font=ctk.CTkFont(size=11),
            command=self._toggle_theme,
            onvalue="dark", offvalue="light",
        )
        self._theme_switch.select()    # dark on by default
        self._theme_switch.grid(row=0, column=2, padx=16, pady=12, sticky="e")

    def _build_body(self):
        """Middle section: sidebar on the left, content frame on the right."""
        body = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)

        self._build_sidebar(body)
        self._build_content(body)

    def _build_sidebar(self, parent):
        """Left navigation panel with one button per pipeline step."""
        sidebar = ctk.CTkFrame(parent, fg_color=_SIDEBAR_BG, corner_radius=0, width=200)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)

        ctk.CTkLabel(
            sidebar,
            text="PIPELINE STEPS",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#556677",
        ).pack(pady=(20, 8), padx=16, anchor="w")

        for i, (label, _) in enumerate(self._NAV_ITEMS):
            btn = ctk.CTkButton(
                sidebar,
                text=label,
                anchor="w",
                fg_color="transparent",
                hover_color="#2a2a4a",
                text_color="#aabbcc",
                font=ctk.CTkFont(size=13),
                corner_radius=6,
                height=38,
                command=lambda idx=i: self._switch_panel(idx),
            )
            btn.pack(fill="x", padx=8, pady=2)
            self._nav_buttons.append(btn)

        # Separator
        ctk.CTkFrame(sidebar, height=1, fg_color="#2a3a4a").pack(
            fill="x", padx=12, pady=16)

        ctk.CTkLabel(
            sidebar, text="v1.0.0",
            font=ctk.CTkFont(size=10), text_color="#334455",
        ).pack(side="bottom", pady=12)

    def _build_content(self, parent):
        """Right content area that hosts the swappable panel frames."""
        self._content_frame = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0)
        self._content_frame.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        self._content_frame.grid_rowconfigure(0, weight=1)
        self._content_frame.grid_columnconfigure(0, weight=1)

        for label, PanelClass in self._NAV_ITEMS:
            panel = PanelClass(self._content_frame, run_callback=self._dispatch)
            panel.grid(row=0, column=0, sticky="nsew")
            self._panels[label] = panel

    def _build_log_panel(self):
        """Bottom log panel with a scrollable textbox, clear and copy buttons."""
        log_frame = ctk.CTkFrame(self, fg_color=_HEADER_BG, corner_radius=0, height=210)
        log_frame.grid(row=2, column=0, sticky="ew")
        log_frame.grid_propagate(False)
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(1, weight=1)

        # Header row
        top = ctk.CTkFrame(log_frame, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 4))
        top.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            top, text="Output Log",
            font=ctk.CTkFont(size=11, weight="bold"), text_color="#8899aa",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            top, text="Copy", width=60, height=24,
            fg_color="#2a3a4a", hover_color="#3a4a5a",
            font=ctk.CTkFont(size=11),
            command=self._copy_log,
        ).grid(row=0, column=1, padx=(0, 6))

        ctk.CTkButton(
            top, text="Clear", width=60, height=24,
            fg_color="#2a3a4a", hover_color="#3a4a5a",
            font=ctk.CTkFont(size=11),
            command=self._clear_log,
        ).grid(row=0, column=2)

        # Log textbox
        self._log_box = ctk.CTkTextbox(
            log_frame,
            font=ctk.CTkFont(family="Courier New", size=11),
            fg_color="#0d1117",
            text_color="#c9d1d9",
            corner_radius=6,
            state="disabled",
            wrap="word",
        )
        self._log_box.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 10))

        # Progress bar (shown during operations)
        self._progress = ctk.CTkProgressBar(log_frame, mode="indeterminate", height=4)
        self._progress.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 8))
        self._progress.set(0)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _switch_panel(self, index: int):
        """
        Show the panel at *index* and update sidebar button styling.

        Args:
            index (int): Index into _NAV_ITEMS.
        """
        self._active_nav = index
        label, _ = self._NAV_ITEMS[index]

        # Raise the selected panel to the top of the grid stack
        for lbl, panel in self._panels.items():
            panel.grid_remove()
        self._panels[label].grid()

        # Update button highlight
        for i, btn in enumerate(self._nav_buttons):
            if i == index:
                btn.configure(
                    fg_color="#2a2a5a", text_color="white",
                    font=ctk.CTkFont(size=13, weight="bold"),
                )
            else:
                btn.configure(
                    fg_color="transparent", text_color="#aabbcc",
                    font=ctk.CTkFont(size=13),
                )

    # ------------------------------------------------------------------
    # Command dispatch & threading
    # ------------------------------------------------------------------

    def _dispatch(self, args: dict, done_callback=None):
        """
        Run an analysis command in a background daemon thread.

        Redirects sys.stdout to the log queue for the duration of the
        operation, restores it afterwards, and calls *done_callback(success)*
        on the main thread when the worker finishes.

        Args:
            args          (dict): Command arguments matching the CLI arg names.
            done_callback (callable | None): Called with True/False when done.
        """
        self._progress.start()

        def worker():
            original_stdout = sys.stdout
            sys.stdout = LogRedirector(self._log_queue)
            success = False
            try:
                success = self._execute(args)
            except Exception as e:
                self._log_queue.put(f"ERROR: {e}\n")
            finally:
                sys.stdout = original_stdout
                self.after(0, lambda: self._on_worker_done(success, done_callback))

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def _on_worker_done(self, success: bool, done_callback):
        """Called on the main thread after a worker thread finishes."""
        self._progress.stop()
        self._progress.set(0)
        if done_callback:
            done_callback(success)

    def _execute(self, args: dict) -> bool:
        """
        Route a command dict to the appropriate SBS class and execute it.

        Args:
            args (dict): Must contain a 'command' key matching one of
                         scan | charts | overview | report | types | full.

        Returns:
            bool: True on success, False if an exception was raised.
        """
        cmd = args.get("command")
        try:
            if cmd == "full":
                self._exec_full(args)
            elif cmd == "scan":
                self._exec_scan(args)
            elif cmd == "charts":
                self._exec_charts(args)
            elif cmd == "overview":
                self._exec_overview(args)
            elif cmd == "report":
                self._exec_report(args)
            elif cmd == "types":
                self._exec_types(args)
            else:
                print(f"Unknown command: {cmd}")
                return False
            return True
        except Exception as e:
            print(f"Error during '{cmd}': {e}")
            return False

    # ------------------------------------------------------------------
    # Per-command execution helpers
    # ------------------------------------------------------------------

    def _exec_full(self, a: dict):
        from SBS.ImageScanner import ImageScanner
        from SBS.ChartGenerator import ChartGenerator
        from SBS.OverviewGenerator import OverviewGenerator
        from SBS.PDFReportGenerator import PDFReportGenerator
        from SBS.TypeAnalyzer import TypeAnalyzer

        out  = Path(a["output"])
        out.mkdir(parents=True, exist_ok=True)
        name = a.get("name") or "Game Characters"

        print(f"\n{'='*55}\nGAME IMAGE ANALYZER — {name}\n{'='*55}")

        print("\n[STEP 1] Scanning images…")
        scanner    = ImageScanner(output_dir=str(out))
        input_path = Path(a["input"])
        results = scanner.scan_directory(input_path) if input_path.is_dir() else (
            [r for r in [scanner.scan_image(input_path)] if r]
        )
        if not results:
            print("No images scanned successfully.")
            return
        csv_path = scanner.export_to_csv(results, "scan_results.csv")

        print("\n[STEP 2] Generating charts…")
        ChartGenerator(str(csv_path), output_dir=str(out / "charts")).generate_all_charts()

        print("\n[STEP 3] Generating overviews…")
        OverviewGenerator(str(csv_path), output_dir=str(out / "overviews")).generate_all_overviews()

        print("\n[STEP 4] Generating PDF report…")
        PDFReportGenerator(str(csv_path), output_dir=str(out), project_name=name).generate_report()

        if a.get("fetch_api") or a.get("type_data"):
            print("\n[STEP 5] Running type analysis…")
            ta = TypeAnalyzer(str(csv_path), type_data_path=a.get("type_data"),
                              output_dir=str(out / "analysis"), project_name=name)
            if a.get("fetch_api"):
                ta.fetch_api_types(save_path=str(out / "type_data.csv"))
            if ta.type_df is not None:
                ta.generate_all_analysis()

        print(f"\n{'='*55}\nPIPELINE COMPLETE!  Outputs saved to: {out}\n{'='*55}")

    def _exec_scan(self, a: dict):
        from SBS.ImageScanner import ImageScanner
        scanner = ImageScanner(output_dir=a.get("output", "output"))
        p = Path(a["input"])
        if p.is_file():
            result = scanner.scan_image(p, name=a.get("name"))
            if result:
                scanner.export_to_csv([result], a.get("csv", "scan_results.csv"))
        else:
            results = scanner.scan_directory(p)
            if results:
                scanner.export_to_csv(results, a.get("csv", "scan_results.csv"))

    def _exec_charts(self, a: dict):
        from SBS.ChartGenerator import ChartGenerator
        g = ChartGenerator(a["csv"], output_dir=a.get("output", "output/charts"))
        if a.get("static_only"):
            g.create_color_frequency_chart_static()
            g.create_shape_frequency_chart_static()
            g.create_color_shape_heatmap_static()
            g.create_color_category_chart_static()
        elif a.get("interactive_only"):
            g.create_color_frequency_chart_interactive()
            g.create_shape_frequency_chart_interactive()
            g.create_color_shape_heatmap_interactive()
            g.create_sunburst_chart()
            g.create_treemap_chart()
        else:
            g.generate_all_charts()

    def _exec_overview(self, a: dict):
        from SBS.OverviewGenerator import OverviewGenerator
        g       = OverviewGenerator(a["csv"], output_dir=a.get("output", "output/overviews"))
        static  = not a.get("interactive_only", False)
        inter   = not a.get("static_only", False)
        if a.get("compare"):
            g.generate_comparison_overview(names=a["compare"])
        elif a.get("all"):
            g.generate_all_overviews(static=static, interactive=inter)
        elif a.get("name"):
            if static: g.generate_overview_static(name=a["name"])
            if inter:  g.generate_overview_interactive(name=a["name"])
        elif a.get("index") is not None:
            if static: g.generate_overview_static(row_index=a["index"])
            if inter:  g.generate_overview_interactive(row_index=a["index"])

    def _exec_report(self, a: dict):
        from SBS.PDFReportGenerator import PDFReportGenerator
        PDFReportGenerator(
            a["csv"], output_dir=a.get("output", "output"),
            project_name=a.get("name"),
        ).generate_report(output_filename=a.get("filename"))

    def _exec_types(self, a: dict):
        from SBS.TypeAnalyzer import TypeAnalyzer
        ta = TypeAnalyzer(
            a["csv"], type_data_path=a.get("type_data"),
            output_dir=a.get("output", "output/analysis"),
            project_name=a.get("name", "Character"),
        )
        if a.get("fetch_api"):
            ta.fetch_api_types(save_path=a.get("save_types"))
        if ta.type_df is not None:
            ta.generate_all_analysis()
        else:
            print("No type data available — provide a type CSV or enable external API fetch.")

    # ------------------------------------------------------------------
    # Log panel helpers
    # ------------------------------------------------------------------

    def _start_log_drain(self):
        """Schedule the recurring queue-drain timer (every 100 ms)."""
        self._drain_log()

    def _drain_log(self):
        """
        Drain the log queue and append any pending messages to the textbox.
        Reschedules itself every 100 ms.
        """
        try:
            while True:
                text = self._log_queue.get_nowait()
                self._log_box.configure(state="normal")
                self._log_box.insert("end", text + "\n")
                self._log_box.see("end")
                self._log_box.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self._drain_log)

    def _clear_log(self):
        """Erase all text from the log textbox."""
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

    def _copy_log(self):
        """Copy the full log content to the system clipboard."""
        content = self._log_box.get("1.0", "end")
        self.clipboard_clear()
        self.clipboard_append(content)

    # ------------------------------------------------------------------
    # Theme toggle
    # ------------------------------------------------------------------

    def _toggle_theme(self):
        """Switch between dark and light appearance modes."""
        mode = self._theme_switch.get()
        ctk.set_appearance_mode(mode)
        self._theme_switch.configure(text=f"{mode.capitalize()} mode")

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self):
        """Start the Tk event loop."""
        self.mainloop()
