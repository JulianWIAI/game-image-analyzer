"""
Game Image Analyzer - Main Runner Script
A comprehensive toolkit for analyzing colors, shapes, and patterns in game character images.

Usage Examples:
---------------
# Scan a directory of images
python main.py scan ./pokemon_images -o ./output

# Generate charts from scan results
python main.py charts ./output/scan_results.csv

# Generate character overviews
python main.py overview ./output/scan_results.csv --all

# Analyze types (with Pokemon data)
python main.py types ./output/scan_results.csv --fetch-pokemon

# Full pipeline
python main.py full ./pokemon_images --fetch-pokemon
"""

import argparse
import sys
from pathlib import Path


def cmd_scan(args):
    """Run the image scanner."""
    from scanner import ImageScanner
    
    scanner = ImageScanner(output_dir=args.output)
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


def cmd_charts(args):
    """Generate charts from scan results."""
    from chart_generator import ChartGenerator
    
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


def cmd_overview(args):
    """Generate character overviews."""
    from overview_generator import OverviewGenerator
    
    generator = OverviewGenerator(args.csv, output_dir=args.output)
    
    static = not args.interactive_only
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


def cmd_types(args):
    """Run type analysis."""
    from type_analyzer import TypeAnalyzer
    
    analyzer = TypeAnalyzer(args.csv, type_data_path=args.type_data, output_dir=args.output)
    
    if args.fetch_pokemon:
        analyzer.fetch_pokemon_types(save_path=args.save_types)
    
    if analyzer.type_df is not None:
        analyzer.generate_all_analysis()
    else:
        print("No type data available. Use --type-data to load or --fetch-pokemon to fetch.")
        return 1
    
    return 0


def cmd_full(args):
    """Run the full pipeline: scan -> charts -> overviews -> type analysis."""
    from scanner import ImageScanner
    from chart_generator import ChartGenerator
    from overview_generator import OverviewGenerator
    from type_analyzer import TypeAnalyzer
    
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("\n" + "=" * 60)
    print("STEP 1: SCANNING IMAGES")
    print("=" * 60)
    
    scanner = ImageScanner(output_dir=str(output_dir))
    input_path = Path(args.input)
    
    if input_path.is_dir():
        results = scanner.scan_directory(input_path)
    else:
        results = [scanner.scan_image(input_path)]
        results = [r for r in results if r]
    
    if not results:
        print("No images scanned successfully.")
        return 1
    
    csv_path = scanner.export_to_csv(results, "scan_results.csv")
    
    print("\n" + "=" * 60)
    print("STEP 2: GENERATING CHARTS")
    print("=" * 60)
    
    chart_generator = ChartGenerator(str(csv_path), output_dir=str(output_dir / "charts"))
    chart_generator.generate_all_charts()
    
    print("\n" + "=" * 60)
    print("STEP 3: GENERATING OVERVIEWS")
    print("=" * 60)
    
    overview_generator = OverviewGenerator(str(csv_path), output_dir=str(output_dir / "overviews"))
    overview_generator.generate_all_overviews(static=True, interactive=True)
    
    if args.fetch_pokemon or args.type_data:
        print("\n" + "=" * 60)
        print("STEP 4: TYPE ANALYSIS")
        print("=" * 60)
        
        type_analyzer = TypeAnalyzer(str(csv_path), type_data_path=args.type_data,
                                     output_dir=str(output_dir / "analysis"))
        
        if args.fetch_pokemon:
            type_data_save = str(output_dir / "pokemon_types.csv")
            type_analyzer.fetch_pokemon_types(save_path=type_data_save)
        
        if type_analyzer.type_df is not None:
            type_analyzer.generate_all_analysis()
    
    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE!")
    print("=" * 60)
    print(f"\nAll outputs saved to: {output_dir}")
    print("\nDirectory structure:")
    print(f"  {output_dir}/")
    print(f"  ├── scan_results.csv")
    print(f"  ├── charts/")
    print(f"  │   ├── *.png (static charts)")
    print(f"  │   └── *.html (interactive charts)")
    print(f"  ├── overviews/")
    print(f"  │   ├── *_overview.png")
    print(f"  │   └── *_overview.html")
    if args.fetch_pokemon or args.type_data:
        print(f"  └── analysis/")
        print(f"      ├── type_*.png")
        print(f"      ├── type_analysis_dashboard.html")
        print(f"      └── type_analysis_report.txt")
    
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Game Image Analyzer - Analyze colors, shapes, and patterns in game character images",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py scan ./images -o ./output
  python main.py charts ./output/scan_results.csv
  python main.py overview ./output/scan_results.csv --all
  python main.py types ./output/scan_results.csv --fetch-pokemon
  python main.py full ./images --fetch-pokemon
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Scan command
    scan_parser = subparsers.add_parser("scan", help="Scan images for colors and shapes")
    scan_parser.add_argument("input", help="Image file or directory to scan")
    scan_parser.add_argument("-o", "--output", default="output", help="Output directory")
    scan_parser.add_argument("-n", "--name", help="Name for single image scan")
    scan_parser.add_argument("--csv", default="scan_results.csv", help="Output CSV filename")
    
    # Charts command
    charts_parser = subparsers.add_parser("charts", help="Generate charts from scan results")
    charts_parser.add_argument("csv", help="Path to scan results CSV")
    charts_parser.add_argument("-o", "--output", default="output/charts", help="Output directory")
    charts_parser.add_argument("--static-only", action="store_true", help="Generate only static PNG charts")
    charts_parser.add_argument("--interactive-only", action="store_true", help="Generate only interactive HTML charts")
    
    # Overview command
    overview_parser = subparsers.add_parser("overview", help="Generate character overviews")
    overview_parser.add_argument("csv", help="Path to scan results CSV")
    overview_parser.add_argument("-o", "--output", default="output/overviews", help="Output directory")
    overview_parser.add_argument("-n", "--name", help="Generate for specific character")
    overview_parser.add_argument("-i", "--index", type=int, help="Generate for character at index")
    overview_parser.add_argument("--all", action="store_true", help="Generate for all characters")
    overview_parser.add_argument("--static-only", action="store_true", help="Generate only static PNG")
    overview_parser.add_argument("--interactive-only", action="store_true", help="Generate only interactive HTML")
    overview_parser.add_argument("--compare", nargs="+", help="Compare multiple characters")
    
    # Types command
    types_parser = subparsers.add_parser("types", help="Analyze type-visual correlations")
    types_parser.add_argument("csv", help="Path to scan results CSV")
    types_parser.add_argument("-t", "--type-data", help="Path to type data CSV/JSON")
    types_parser.add_argument("-o", "--output", default="output/analysis", help="Output directory")
    types_parser.add_argument("--fetch-pokemon", action="store_true", help="Fetch Pokemon types from PokeAPI")
    types_parser.add_argument("--save-types", help="Save fetched type data to file")
    
    # Full pipeline command
    full_parser = subparsers.add_parser("full", help="Run full analysis pipeline")
    full_parser.add_argument("input", help="Image directory to scan")
    full_parser.add_argument("-o", "--output", default="output", help="Output directory")
    full_parser.add_argument("-t", "--type-data", help="Path to type data CSV/JSON")
    full_parser.add_argument("--fetch-pokemon", action="store_true", help="Fetch Pokemon types from PokeAPI")
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        return 1
    
    commands = {
        "scan": cmd_scan,
        "charts": cmd_charts,
        "overview": cmd_overview,
        "types": cmd_types,
        "full": cmd_full,
    }
    
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
