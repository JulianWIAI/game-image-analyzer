"""
SBS (Step-By-Step) Analysis Package
=====================================
This package contains all core analysis components for the Game Image Analyzer toolkit.
Each module exposes exactly one class, following single-responsibility principles.

Modules:
    - config          : Global constants — color palettes, shape definitions, analysis settings.
    - ImageScanner    : Scans image files for dominant colors and shape distributions.
    - ChartGenerator  : Produces static (PNG) and interactive (HTML) charts from scan data.
    - OverviewGenerator: Generates per-character visual overview reports (static + interactive).
    - PDFReportGenerator: Compiles a professional PDF summary of the full analysis dataset.
    - TypeAnalyzer    : Correlates character types/attributes with their detected visual properties.

Usage example:
    from SBS import ImageScanner, ChartGenerator, PDFReportGenerator
"""

__all__ = [
    "ImageScanner",
    "ChartGenerator",
    "OverviewGenerator",
    "PDFReportGenerator",
    "TypeAnalyzer",
]

_module_map = {
    "ImageScanner":       ".ImageScanner",
    "ChartGenerator":     ".ChartGenerator",
    "OverviewGenerator":  ".OverviewGenerator",
    "PDFReportGenerator": ".PDFReportGenerator",
    "TypeAnalyzer":       ".TypeAnalyzer",
}


def __getattr__(name: str):
    """Lazily import analysis classes on first access.

    This avoids loading heavy dependencies (pandas, opencv, scikit-learn, …)
    at package-import time, which lets lightweight consumers such as the GUI
    module start up without requiring the full scientific stack to be present.
    """
    if name in _module_map:
        import importlib
        module = importlib.import_module(_module_map[name], package=__name__)
        obj = getattr(module, name)
        # Cache on the package so subsequent accesses skip __getattr__
        globals()[name] = obj
        return obj
    raise AttributeError(f"module 'SBS' has no attribute {name!r}")
