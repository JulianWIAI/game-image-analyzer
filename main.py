"""
Game Image Analyzer — Main Entry Point
=======================================
A comprehensive toolkit for analyzing colors, shapes, and patterns in ANY game
character images.  Works with any game, franchise, or custom image collection.

All analysis classes live in the SBS (Step-By-Step) package under SBS/.
This file wires together the CLI argument parser and dispatches each subcommand
to the appropriate SBS class.

Usage examples
--------------
Scan a directory of images (any game):
    python main.py scan ./my_images -o ./output

Generate charts from scan results:
    python main.py charts ./output/scan_results.csv

Generate per-character overviews:
    python main.py overview ./output/scan_results.csv --all

Generate a PDF summary report:
    python main.py report ./output/scan_results.csv -n "My Game"

Analyze types with custom type data (any game):
    python main.py types ./output/scan_results.csv -t my_types.csv -n "MyGame"

Analyze types with an external character API:
    python main.py types ./output/scan_results.csv --fetch-api

Run the full pipeline (any game):
    python main.py full ./my_images -o ./output -n "My Game"

Run the full pipeline with external API type data:
    python main.py full ./game_images --fetch-api
"""

import argparse
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------
# Imports are deferred to each handler function so that only the modules
# needed for the requested command are loaded.  This keeps startup fast
# for simple single-step invocations.

def cmd_scan(args) -> int:
    """
    Handle the 'scan' subcommand.

    Scans a single image file or an entire directory and writes results to CSV.

    Args:
        args: Parsed argument namespace from argparse.

    Returns:
        int: 0 on success, 1 on error.
    """
    from SBS.ImageScanner import ImageScanner

    scanner    = ImageScanner(output_dir=args.output)
    input_path = Path(args.input)

    if input_path.is_file():
        result = scanner.scan_image(input_path, name=args.name)
        if result:
            scanner.export_to_csv([result], args.csv)
    elif input_path.is_dir():
        results = scanner.scan_directory(input_path)
        if results:
            scanner.export_to_csv(results, args.csv)
    else:
        print(f"Error: {args.input} is not a valid file or directory")
        return 1

    return 0


def cmd_charts(args) -> int:
    """
    Handle the 'charts' subcommand.

    Generates static PNG and interactive HTML charts from a scan-results CSV.

    Args:
        args: Parsed argument namespace from argparse.

    Returns:
        int: 0 on success.
    """
    from SBS.ChartGenerator import ChartGenerator

    generator = ChartGenerator(args.csv, output_dir=args.output)

    if args.static_only:
        generator.create_color_frequency_chart_static()
        generator.create_shape_frequency_chart_static()
        generator.create_color_shape_heatmap_static()
        generator.create_color_category_chart_static()
    elif args.interactive_only:
        generator.create_color_frequency_chart_interactive()
        generator.create_shape_frequency_chart_interactive()
        generator.create_color_shape_heatmap_interactive()
        generator.create_sunburst_chart()
        generator.create_treemap_chart()
    else:
        generator.generate_all_charts()

    return 0


def cmd_overview(args) -> int:
    """
    Handle the 'overview' subcommand.

    Generates per-character visual overview reports (static PNG, interactive HTML,
    or comparison views depending on flags).

    Args:
        args: Parsed argument namespace from argparse.

    Returns:
        int: 0 on success, 1 if required arguments are missing.
    """
    from SBS.OverviewGenerator import OverviewGenerator

    generator = OverviewGenerator(args.csv, output_dir=args.output)

    static      = not args.interactive_only
    interactive = not args.static_only

    if args.compare:
        generator.generate_comparison_overview(names=args.compare)
    elif args.all:
        generator.generate_all_overviews(static=static, interactive=interactive)
    elif args.name:
        if static:
            generator.generate_overview_static(name=args.name)
        if interactive:
            generator.generate_overview_interactive(name=args.name)
    elif args.index is not None:
        if static:
            generator.generate_overview_static(row_index=args.index)
        if interactive:
            generator.generate_overview_interactive(row_index=args.index)
    else:
        print("Please specify --name, --index, --all, or --compare")
        return 1

    return 0


def cmd_report(args) -> int:
    """
    Handle the 'report' subcommand.

    Generates a PDF analysis summary report from a scan-results CSV.

    Args:
        args: Parsed argument namespace from argparse.

    Returns:
        int: 0 on success.
    """
    from SBS.PDFReportGenerator import PDFReportGenerator

    generator = PDFReportGenerator(
        args.csv,
        output_dir=args.output,
        project_name=args.name,
    )
    generator.generate_report(output_filename=args.filename)
    return 0


def cmd_types(args) -> int:
    """
    Handle the 'types' subcommand.

    Performs type-visual correlation analysis.  Type data can be loaded from a
    custom CSV/JSON file or fetched from an external character API.

    Args:
        args: Parsed argument namespace from argparse.

    Returns:
        int: 0 on success, 1 if no type data is available.
    """
    from SBS.TypeAnalyzer import TypeAnalyzer

    analyzer = TypeAnalyzer(
        args.csv,
        type_data_path=args.type_data,
        output_dir=args.output,
        project_name=args.name,
    )

    if args.fetch_api:
        analyzer.fetch_api_types(save_path=args.save_types)

    if analyzer.type_df is not None:
        analyzer.generate_all_analysis()
    else:
        print("\nNo type data available.")
        print("Options:")
        print("  1. Provide your own type data: -t your_types.csv")
        print("  2. Use an external character API: --fetch-api")
        print("\nType CSV format:  name,type_primary,type_secondary,...")
        return 1

    return 0


def cmd_full(args) -> int:
    """
    Handle the 'full' subcommand.

    Runs the complete analysis pipeline in five ordered steps:
      1. Scan images → scan_results.csv
      2. Generate charts (PNG + HTML)
      3. Generate per-character overviews
      4. Generate PDF summary report
      5. (Optional) Type analysis if --fetch-api or -t is provided

    Args:
        args: Parsed argument namespace from argparse.

    Returns:
        int: 0 on success, 1 if no images were scanned successfully.
    """
    from SBS.ImageScanner import ImageScanner
    from SBS.ChartGenerator import ChartGenerator
    from SBS.OverviewGenerator import OverviewGenerator
    from SBS.PDFReportGenerator import PDFReportGenerator
    from SBS.TypeAnalyzer import TypeAnalyzer

    output_dir   = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    project_name = args.name or "Game Characters"

    print("\n" + "=" * 60)
    print(f"GAME IMAGE ANALYZER — {project_name}")
    print("=" * 60)

    # ---- Step 1: Scan ----
    print("\n" + "=" * 60)
    print("STEP 1: SCANNING IMAGES")
    print("=" * 60)

    scanner    = ImageScanner(output_dir=str(output_dir))
    input_path = Path(args.input)

    if input_path.is_dir():
        results = scanner.scan_directory(input_path)
    else:
        result  = scanner.scan_image(input_path)
        results = [result] if result else []

    if not results:
        print("No images scanned successfully.")
        return 1

    csv_path = scanner.export_to_csv(results, "scan_results.csv")

    # ---- Step 2: Charts ----
    print("\n" + "=" * 60)
    print("STEP 2: GENERATING CHARTS")
    print("=" * 60)

    ChartGenerator(str(csv_path), output_dir=str(output_dir / "charts")).generate_all_charts()

    # ---- Step 3: Overviews ----
    print("\n" + "=" * 60)
    print("STEP 3: GENERATING OVERVIEWS")
    print("=" * 60)

    OverviewGenerator(str(csv_path), output_dir=str(output_dir / "overviews")).generate_all_overviews(
        static=True, interactive=True
    )

    # ---- Step 4: PDF Report ----
    print("\n" + "=" * 60)
    print("STEP 4: GENERATING PDF REPORT")
    print("=" * 60)

    PDFReportGenerator(str(csv_path), output_dir=str(output_dir), project_name=project_name).generate_report()

    # ---- Step 5: Type Analysis (optional) ----
    if args.fetch_api or args.type_data:
        print("\n" + "=" * 60)
        print("STEP 5: TYPE ANALYSIS")
        print("=" * 60)

        type_analyzer = TypeAnalyzer(
            str(csv_path),
            type_data_path=args.type_data,
            output_dir=str(output_dir / "analysis"),
            project_name=project_name,
        )

        if args.fetch_api:
            type_analyzer.fetch_api_types(save_path=str(output_dir / "type_data.csv"))

        if type_analyzer.type_df is not None:
            type_analyzer.generate_all_analysis()

    # ---- Summary ----
    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE!")
    print("=" * 60)
    print(f"\nAll outputs saved to: {output_dir}")
    print("\nDirectory structure:")
    print(f"  {output_dir}/")
    print(f"  ├── scan_results.csv")
    print(f"  ├── {project_name.lower().replace(' ', '_')}_analysis_report.pdf")
    print(f"  ├── charts/")
    print(f"  │   ├── *_raw.png,      *_filtered.png")
    print(f"  │   └── *_raw.html,     *_filtered.html")
    print(f"  └── overviews/")
    print(f"      ├── *_overview.png")
    print(f"      └── *_overview.html")
    if args.fetch_api or args.type_data:
        print(f"  └── analysis/")
        print(f"      ├── type_*.png")
        print(f"      ├── type_analysis_dashboard.html")
        print(f"      └── type_analysis_report.txt")

    return 0


# ---------------------------------------------------------------------------
# CLI argument parser
# ---------------------------------------------------------------------------

def main() -> int:
    """
    Parse CLI arguments and dispatch to the appropriate subcommand handler.

    Returns:
        int: Exit code (0 = success, 1 = error).
    """
    parser = argparse.ArgumentParser(
        description="Game Image Analyzer — Analyze colors, shapes, and patterns in ANY game character images",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Works with ANY game or image collection!

Examples:
  # Basic usage (any game)
  python main.py scan ./my_images -o ./output
  python main.py charts ./output/scan_results.csv
  python main.py report ./output/scan_results.csv -n "My Game"
  python main.py full ./my_images -n "My Game"

  # With type analysis (custom CSV)
  python main.py types ./scan_results.csv -t my_types.csv -n "MyGame"

  # With external character API
  python main.py full ./game_images --fetch-api

Type CSV format for custom games:
  name,type_primary,type_secondary
  Mario,hero,fire
  Luigi,hero,none
  Bowser,villain,fire
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ---- scan ----
    scan_parser = subparsers.add_parser("scan", help="Scan images for colors and shapes")
    scan_parser.add_argument("input",                        help="Image file or directory to scan")
    scan_parser.add_argument("-o", "--output", default="output", help="Output directory")
    scan_parser.add_argument("-n", "--name",                 help="Name for single image scan")
    scan_parser.add_argument("--csv", default="scan_results.csv", help="Output CSV filename")

    # ---- charts ----
    charts_parser = subparsers.add_parser("charts", help="Generate charts from scan results")
    charts_parser.add_argument("csv",                              help="Path to scan results CSV")
    charts_parser.add_argument("-o", "--output", default="output/charts", help="Output directory")
    charts_parser.add_argument("--static-only",      action="store_true", help="Generate only static PNG charts")
    charts_parser.add_argument("--interactive-only", action="store_true", help="Generate only interactive HTML charts")

    # ---- overview ----
    overview_parser = subparsers.add_parser("overview", help="Generate character overviews")
    overview_parser.add_argument("csv",                               help="Path to scan results CSV")
    overview_parser.add_argument("-o", "--output", default="output/overviews", help="Output directory")
    overview_parser.add_argument("-n", "--name",                      help="Generate for specific character")
    overview_parser.add_argument("-i", "--index",   type=int,         help="Generate for character at index")
    overview_parser.add_argument("--all",           action="store_true", help="Generate for all characters")
    overview_parser.add_argument("--static-only",   action="store_true", help="Generate only static PNG")
    overview_parser.add_argument("--interactive-only", action="store_true", help="Generate only interactive HTML")
    overview_parser.add_argument("--compare",       nargs="+",        help="Compare multiple characters by name")

    # ---- report ----
    report_parser = subparsers.add_parser("report", help="Generate PDF summary report")
    report_parser.add_argument("csv",                          help="Path to scan results CSV")
    report_parser.add_argument("-o", "--output", default="output", help="Output directory")
    report_parser.add_argument("-n", "--name",                 help="Project name (e.g. 'My Game', 'RPG Heroes')")
    report_parser.add_argument("--filename",                   help="Output PDF filename")

    # ---- types ----
    types_parser = subparsers.add_parser("types", help="Analyze type-visual correlations")
    types_parser.add_argument("csv",                                     help="Path to scan results CSV")
    types_parser.add_argument("-t", "--type-data",                       help="Path to type data CSV/JSON (for any game)")
    types_parser.add_argument("-o", "--output", default="output/analysis", help="Output directory")
    types_parser.add_argument("-n", "--name",   default="Character",     help="Project name (e.g. 'My Game', 'RPG Heroes')")
    types_parser.add_argument("--fetch-api",     action="store_true",    help="Fetch character type data from an external API")
    types_parser.add_argument("--save-types",                            help="Save fetched type data to file")

    # ---- full ----
    full_parser = subparsers.add_parser("full", help="Run the full analysis pipeline")
    full_parser.add_argument("input",                          help="Image directory to scan")
    full_parser.add_argument("-o", "--output", default="output", help="Output directory")
    full_parser.add_argument("-n", "--name",                   help="Project name (e.g. 'My Game', 'RPG Heroes')")
    full_parser.add_argument("-t", "--type-data",              help="Path to type data CSV/JSON")
    full_parser.add_argument("--fetch-api", action="store_true", help="Fetch character type data from an external API")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    commands = {
        "scan":     cmd_scan,
        "charts":   cmd_charts,
        "overview": cmd_overview,
        "report":   cmd_report,
        "types":    cmd_types,
        "full":     cmd_full,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
