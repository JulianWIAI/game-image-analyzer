"""
Type Analyzer for Game Character Analysis
Analyzes correlations between character types/attributes and their visual properties.
Supports loading type data from CSV/JSON or fetching from PokeAPI.
"""

import pandas as pd
import numpy as np
import json
import requests
import time
from pathlib import Path
from collections import defaultdict
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
from config import (COLOR_PALETTE, COLOR_CATEGORIES, SHAPE_DEFINITIONS,
                   ATTRIBUTE_SHAPE_ASSOCIATIONS, ATTRIBUTE_COLOR_ASSOCIATIONS,
                   OUTPUT_SETTINGS)


class TypeAnalyzer:
    def __init__(self, scan_csv_path, type_data_path=None, output_dir="output/analysis"):
        self.scan_csv = Path(scan_csv_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.scan_df = pd.read_csv(scan_csv_path)
        self._parse_json_columns()
        
        self.type_df = None
        if type_data_path:
            self.load_type_data(type_data_path)
    
    def _parse_json_columns(self):
        """Parse JSON columns in the scan dataframe."""
        json_cols = ["colors_json", "shapes_json", "color_shape_combos_json"]
        for col in json_cols:
            if col in self.scan_df.columns:
                self.scan_df[col] = self.scan_df[col].apply(
                    lambda x: json.loads(x) if pd.notna(x) and isinstance(x, str) else x
                )
    
    def _get_color_hex(self, color_name):
        """Get hex color code for a color name."""
        if color_name in COLOR_PALETTE:
            return COLOR_PALETTE[color_name]["hex"]
        return "#888888"
    
    def load_type_data(self, path):
        """Load type/attribute data from CSV or JSON file."""
        path = Path(path)
        
        if path.suffix == '.csv':
            self.type_df = pd.read_csv(path)
        elif path.suffix == '.json':
            with open(path) as f:
                data = json.load(f)
            self.type_df = pd.DataFrame(data)
        else:
            print(f"Unsupported file format: {path.suffix}")
            return
        
        print(f"Loaded type data with columns: {list(self.type_df.columns)}")
        print(f"Total entries: {len(self.type_df)}")
    
    def fetch_pokemon_types(self, pokemon_names=None, save_path=None):
        """
        Fetch Pokemon type data from PokeAPI.
        If pokemon_names is None, uses names from scan_df.
        """
        if pokemon_names is None:
            pokemon_names = self.scan_df["name"].str.lower().tolist()
        
        print(f"Fetching data for {len(pokemon_names)} Pokemon...")
        
        type_data = []
        
        for i, name in enumerate(pokemon_names):
            clean_name = name.lower().strip()
            clean_name = clean_name.replace(" ", "-")
            
            try:
                species_url = f"https://pokeapi.co/api/v2/pokemon-species/{clean_name}"
                species_resp = requests.get(species_url, timeout=10)
                
                pokemon_url = f"https://pokeapi.co/api/v2/pokemon/{clean_name}"
                pokemon_resp = requests.get(pokemon_url, timeout=10)
                
                if species_resp.status_code == 200 and pokemon_resp.status_code == 200:
                    species_data = species_resp.json()
                    pokemon_data = pokemon_resp.json()
                    
                    types = [t["type"]["name"] for t in pokemon_data["types"]]
                    egg_groups = [eg["name"] for eg in species_data.get("egg_groups", [])]
                    color = species_data.get("color", {}).get("name", "unknown")
                    shape = species_data.get("shape", {}).get("name", "unknown") if species_data.get("shape") else "unknown"
                    habitat = species_data.get("habitat", {}).get("name", "unknown") if species_data.get("habitat") else "unknown"
                    is_legendary = species_data.get("is_legendary", False)
                    is_mythical = species_data.get("is_mythical", False)
                    is_baby = species_data.get("is_baby", False)
                    base_happiness = species_data.get("base_happiness", 0)
                    capture_rate = species_data.get("capture_rate", 0)
                    stats = {s["stat"]["name"]: s["base_stat"] for s in pokemon_data["stats"]}
                    
                    entry = {
                        "name": name,
                        "type_primary": types[0] if types else "unknown",
                        "type_secondary": types[1] if len(types) > 1 else None,
                        "types": ",".join(types),
                        "egg_groups": ",".join(egg_groups),
                        "official_color": color,
                        "official_shape": shape,
                        "habitat": habitat,
                        "is_legendary": is_legendary,
                        "is_mythical": is_mythical,
                        "is_baby": is_baby,
                        "base_happiness": base_happiness,
                        "capture_rate": capture_rate,
                        "hp": stats.get("hp", 0),
                        "attack": stats.get("attack", 0),
                        "defense": stats.get("defense", 0),
                        "special_attack": stats.get("special-attack", 0),
                        "special_defense": stats.get("special-defense", 0),
                        "speed": stats.get("speed", 0),
                    }
                    
                    type_data.append(entry)
                    print(f"  [{i+1}/{len(pokemon_names)}] {name}: {types}")
                else:
                    print(f"  [{i+1}/{len(pokemon_names)}] {name}: Not found")
                    type_data.append({"name": name, "type_primary": "unknown"})
                
                time.sleep(0.1)
                
            except Exception as e:
                print(f"  [{i+1}/{len(pokemon_names)}] {name}: Error - {e}")
                type_data.append({"name": name, "type_primary": "unknown"})
        
        self.type_df = pd.DataFrame(type_data)
        
        if save_path:
            save_path = Path(save_path)
            if save_path.suffix == '.csv':
                self.type_df.to_csv(save_path, index=False)
            else:
                self.type_df.to_json(save_path, orient='records', indent=2)
            print(f"\nType data saved to: {save_path}")
        
        return self.type_df
    
    def merge_data(self):
        """Merge scan data with type data."""
        if self.type_df is None:
            print("No type data loaded. Use load_type_data() or fetch_pokemon_types() first.")
            return None
        
        self.scan_df["name_lower"] = self.scan_df["name"].str.lower().str.strip()
        self.type_df["name_lower"] = self.type_df["name"].str.lower().str.strip()
        
        merged = pd.merge(self.scan_df, self.type_df, on="name_lower", how="inner", suffixes=('', '_type'))
        
        print(f"Merged data: {len(merged)} entries (scan: {len(self.scan_df)}, types: {len(self.type_df)})")
        
        return merged
    
    def analyze_type_colors(self, merged_df=None):
        """Analyze which colors are associated with each type."""
        if merged_df is None:
            merged_df = self.merge_data()
        
        if merged_df is None or merged_df.empty:
            return {}, {}
        
        type_colors = defaultdict(lambda: defaultdict(float))
        type_counts = defaultdict(int)
        
        for _, row in merged_df.iterrows():
            primary_type = row.get("type_primary", "unknown")
            colors = row.get("colors_json", {})
            
            if isinstance(colors, str):
                colors = json.loads(colors)
            
            type_counts[primary_type] += 1
            for color, pct in colors.items():
                type_colors[primary_type][color] += pct
        
        normalized = {}
        for ptype, colors in type_colors.items():
            total = sum(colors.values())
            if total > 0:
                normalized[ptype] = {c: round(p/total * 100, 2) for c, p in colors.items()}
        
        return normalized, type_counts
    
    def analyze_type_shapes(self, merged_df=None):
        """Analyze which shapes are associated with each type."""
        if merged_df is None:
            merged_df = self.merge_data()
        
        if merged_df is None or merged_df.empty:
            return {}, {}
        
        type_shapes = defaultdict(lambda: defaultdict(float))
        type_counts = defaultdict(int)
        
        for _, row in merged_df.iterrows():
            primary_type = row.get("type_primary", "unknown")
            shapes = row.get("shapes_json", {})
            
            if isinstance(shapes, str):
                shapes = json.loads(shapes)
            
            type_counts[primary_type] += 1
            for shape, pct in shapes.items():
                type_shapes[primary_type][shape] += pct
        
        normalized = {}
        for ptype, shapes in type_shapes.items():
            total = sum(shapes.values())
            if total > 0:
                normalized[ptype] = {s: round(p/total * 100, 2) for s, p in shapes.items()}
        
        return normalized, type_counts
    
    def create_type_color_heatmap_static(self, merged_df=None, top_colors=15):
        """Create a static heatmap of type-color associations."""
        type_colors, type_counts = self.analyze_type_colors(merged_df)
        
        if not type_colors:
            print("No data to visualize")
            return None
        
        all_colors = set()
        for colors in type_colors.values():
            all_colors.update(colors.keys())
        
        color_totals = defaultdict(float)
        for colors in type_colors.values():
            for c, p in colors.items():
                color_totals[c] += p
        
        top_color_names = sorted(color_totals.keys(), key=lambda x: color_totals[x], reverse=True)[:top_colors]
        type_names = sorted(type_colors.keys())
        
        matrix = np.zeros((len(type_names), len(top_color_names)))
        for i, ptype in enumerate(type_names):
            for j, color in enumerate(top_color_names):
                matrix[i, j] = type_colors.get(ptype, {}).get(color, 0)
        
        fig, ax = plt.subplots(figsize=(14, 10))
        
        im = ax.imshow(matrix, cmap='YlOrRd', aspect='auto')
        
        ax.set_xticks(range(len(top_color_names)))
        ax.set_xticklabels(top_color_names, rotation=45, ha='right')
        ax.set_yticks(range(len(type_names)))
        ax.set_yticklabels([f"{t} ({type_counts[t]})" for t in type_names])
        
        for i in range(len(type_names)):
            for j in range(len(top_color_names)):
                val = matrix[i, j]
                if val > 0:
                    color = 'white' if val > matrix.max() * 0.5 else 'black'
                    ax.text(j, i, f'{val:.1f}', ha='center', va='center', color=color, fontsize=7)
        
        plt.colorbar(im, label='Color Percentage (%)')
        ax.set_title("Color Distribution by Pokemon Type", fontsize=14, fontweight='bold')
        ax.set_xlabel("Colors")
        ax.set_ylabel("Types (count)")
        
        plt.tight_layout()
        output_path = self.output_dir / "type_color_heatmap.png"
        plt.savefig(output_path, dpi=OUTPUT_SETTINGS["chart_dpi"], bbox_inches='tight')
        plt.close()
        
        print(f"Saved: {output_path}")
        return output_path
    
    def create_type_shape_heatmap_static(self, merged_df=None):
        """Create a static heatmap of type-shape associations."""
        type_shapes, type_counts = self.analyze_type_shapes(merged_df)
        
        if not type_shapes:
            print("No data to visualize")
            return None
        
        all_shapes = set()
        for shapes in type_shapes.values():
            all_shapes.update(shapes.keys())
        
        shape_names = sorted(all_shapes)
        type_names = sorted(type_shapes.keys())
        
        matrix = np.zeros((len(type_names), len(shape_names)))
        for i, ptype in enumerate(type_names):
            for j, shape in enumerate(shape_names):
                matrix[i, j] = type_shapes.get(ptype, {}).get(shape, 0)
        
        fig, ax = plt.subplots(figsize=(12, 10))
        
        im = ax.imshow(matrix, cmap='Blues', aspect='auto')
        
        ax.set_xticks(range(len(shape_names)))
        ax.set_xticklabels(shape_names, rotation=45, ha='right')
        ax.set_yticks(range(len(type_names)))
        ax.set_yticklabels([f"{t} ({type_counts[t]})" for t in type_names])
        
        for i in range(len(type_names)):
            for j in range(len(shape_names)):
                val = matrix[i, j]
                if val > 0:
                    color = 'white' if val > matrix.max() * 0.5 else 'black'
                    ax.text(j, i, f'{val:.1f}', ha='center', va='center', color=color, fontsize=8)
        
        plt.colorbar(im, label='Shape Percentage (%)')
        ax.set_title("Shape Distribution by Pokemon Type", fontsize=14, fontweight='bold')
        ax.set_xlabel("Shapes")
        ax.set_ylabel("Types (count)")
        
        plt.tight_layout()
        output_path = self.output_dir / "type_shape_heatmap.png"
        plt.savefig(output_path, dpi=OUTPUT_SETTINGS["chart_dpi"], bbox_inches='tight')
        plt.close()
        
        print(f"Saved: {output_path}")
        return output_path
    
    def create_type_analysis_interactive(self, merged_df=None):
        """Create an interactive dashboard for type analysis."""
        if merged_df is None:
            merged_df = self.merge_data()
        
        if merged_df is None or merged_df.empty:
            return None
        
        type_colors, color_counts = self.analyze_type_colors(merged_df)
        type_shapes, shape_counts = self.analyze_type_shapes(merged_df)
        
        all_colors = set()
        for colors in type_colors.values():
            all_colors.update(colors.keys())
        color_totals = defaultdict(float)
        for colors in type_colors.values():
            for c, p in colors.items():
                color_totals[c] += p
        top_color_names = sorted(color_totals.keys(), key=lambda x: color_totals[x], reverse=True)[:15]
        
        all_shapes = set()
        for shapes in type_shapes.values():
            all_shapes.update(shapes.keys())
        shape_names = sorted(all_shapes)
        type_names = sorted(type_colors.keys())
        
        color_matrix = []
        for ptype in type_names:
            row = [type_colors.get(ptype, {}).get(c, 0) for c in top_color_names]
            color_matrix.append(row)
        
        shape_matrix = []
        for ptype in type_names:
            row = [type_shapes.get(ptype, {}).get(s, 0) for s in shape_names]
            shape_matrix.append(row)
        
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=["Color Distribution by Type", "Shape Distribution by Type",
                           "Type Count Overview", "Top Colors per Type"],
            specs=[[{"type": "heatmap"}, {"type": "heatmap"}],
                   [{"type": "bar"}, {"type": "bar"}]],
            vertical_spacing=0.12,
            horizontal_spacing=0.1
        )
        
        fig.add_trace(
            go.Heatmap(
                z=color_matrix,
                x=top_color_names,
                y=[f"{t} ({color_counts[t]})" for t in type_names],
                colorscale='YlOrRd',
                hovertemplate='Type: %{y}<br>Color: %{x}<br>Percentage: %{z:.2f}%<extra></extra>'
            ),
            row=1, col=1
        )
        
        fig.add_trace(
            go.Heatmap(
                z=shape_matrix,
                x=shape_names,
                y=[f"{t} ({shape_counts[t]})" for t in type_names],
                colorscale='Blues',
                hovertemplate='Type: %{y}<br>Shape: %{x}<br>Percentage: %{z:.2f}%<extra></extra>'
            ),
            row=1, col=2
        )
        
        type_count_values = [color_counts[t] for t in type_names]
        fig.add_trace(
            go.Bar(
                x=type_names,
                y=type_count_values,
                marker_color='rgb(55, 83, 109)',
                hovertemplate='Type: %{x}<br>Count: %{y}<extra></extra>'
            ),
            row=2, col=1
        )
        
        top_colors_per_type = []
        for ptype in type_names:
            colors = type_colors.get(ptype, {})
            if colors:
                top_color = max(colors.items(), key=lambda x: x[1])
                top_colors_per_type.append(top_color[1])
            else:
                top_colors_per_type.append(0)
        
        bar_colors = []
        for ptype in type_names:
            colors = type_colors.get(ptype, {})
            if colors:
                top_color_name = max(colors.items(), key=lambda x: x[1])[0]
                bar_colors.append(self._get_color_hex(top_color_name))
            else:
                bar_colors.append("#888888")
        
        fig.add_trace(
            go.Bar(
                x=type_names,
                y=top_colors_per_type,
                marker_color=bar_colors,
                hovertemplate='Type: %{x}<br>Top Color %: %{y:.1f}%<extra></extra>'
            ),
            row=2, col=2
        )
        
        fig.update_layout(
            title=dict(text="Pokemon Type Visual Analysis Dashboard", font=dict(size=20)),
            height=900,
            showlegend=False,
            template="plotly_white"
        )
        
        fig.update_xaxes(tickangle=45, row=1, col=1)
        fig.update_xaxes(tickangle=45, row=1, col=2)
        fig.update_xaxes(tickangle=45, row=2, col=1)
        fig.update_xaxes(tickangle=45, row=2, col=2)
        
        output_path = self.output_dir / "type_analysis_dashboard.html"
        fig.write_html(str(output_path))
        
        print(f"Saved: {output_path}")
        return output_path
    
    def create_attribute_correlation_chart(self, merged_df=None):
        """Create a chart showing correlation between attributes and visual properties."""
        if merged_df is None:
            merged_df = self.merge_data()
        
        if merged_df is None or merged_df.empty:
            return None
        
        fig, axes = plt.subplots(2, 2, figsize=(14, 12))
        
        ax1 = axes[0, 0]
        happiness_colors = defaultdict(list)
        for _, row in merged_df.iterrows():
            happiness = row.get("base_happiness", 0)
            dom_color = row.get("dominant_color", "unknown")
            if happiness and dom_color != "unknown":
                happiness_colors[dom_color].append(happiness)
        
        avg_happiness = {c: np.mean(h) for c, h in happiness_colors.items() if len(h) >= 2}
        if avg_happiness:
            sorted_colors = sorted(avg_happiness.items(), key=lambda x: x[1], reverse=True)[:15]
            colors, values = zip(*sorted_colors)
            hex_colors = [self._get_color_hex(c) for c in colors]
            ax1.barh(range(len(colors)), values, color=hex_colors, edgecolor='black')
            ax1.set_yticks(range(len(colors)))
            ax1.set_yticklabels(colors)
            ax1.set_xlabel("Average Base Happiness")
            ax1.set_title("Color vs Base Happiness", fontweight='bold')
            ax1.invert_yaxis()
        
        ax2 = axes[0, 1]
        attack_shapes = defaultdict(list)
        for _, row in merged_df.iterrows():
            attack = row.get("attack", 0)
            dom_shape = row.get("dominant_shape", "unknown")
            if attack and dom_shape != "unknown":
                attack_shapes[dom_shape].append(attack)
        
        avg_attack = {s: np.mean(a) for s, a in attack_shapes.items() if len(a) >= 2}
        if avg_attack:
            sorted_shapes = sorted(avg_attack.items(), key=lambda x: x[1], reverse=True)
            shapes, values = zip(*sorted_shapes)
            colors = plt.cm.Reds(np.linspace(0.3, 0.9, len(shapes)))
            ax2.bar(range(len(shapes)), values, color=colors, edgecolor='black')
            ax2.set_xticks(range(len(shapes)))
            ax2.set_xticklabels(shapes, rotation=45, ha='right')
            ax2.set_ylabel("Average Attack Stat")
            ax2.set_title("Shape vs Attack Stat", fontweight='bold')
        
        ax3 = axes[1, 0]
        legendary_colors = defaultdict(int)
        regular_colors = defaultdict(int)
        for _, row in merged_df.iterrows():
            is_legendary = row.get("is_legendary", False) or row.get("is_mythical", False)
            dom_color = row.get("dominant_color", "unknown")
            if dom_color != "unknown":
                if is_legendary:
                    legendary_colors[dom_color] += 1
                else:
                    regular_colors[dom_color] += 1
        
        if legendary_colors:
            all_cols = set(legendary_colors.keys()) | set(regular_colors.keys())
            top_cols = sorted(all_cols, key=lambda x: legendary_colors.get(x, 0) + regular_colors.get(x, 0), reverse=True)[:10]
            
            x = np.arange(len(top_cols))
            width = 0.35
            
            leg_vals = [legendary_colors.get(c, 0) for c in top_cols]
            reg_vals = [regular_colors.get(c, 0) for c in top_cols]
            
            ax3.bar(x - width/2, reg_vals, width, label='Regular', color='steelblue')
            ax3.bar(x + width/2, leg_vals, width, label='Legendary/Mythical', color='gold')
            ax3.set_xticks(x)
            ax3.set_xticklabels(top_cols, rotation=45, ha='right')
            ax3.set_ylabel("Count")
            ax3.set_title("Legendary vs Regular: Color Distribution", fontweight='bold')
            ax3.legend()
        
        ax4 = axes[1, 1]
        type_stats = defaultdict(lambda: {"attack": [], "defense": []})
        for _, row in merged_df.iterrows():
            ptype = row.get("type_primary", "unknown")
            attack = row.get("attack", 0)
            defense = row.get("defense", 0)
            if ptype != "unknown" and attack and defense:
                type_stats[ptype]["attack"].append(attack)
                type_stats[ptype]["defense"].append(defense)
        
        if type_stats:
            types = list(type_stats.keys())
            avg_attacks = [np.mean(type_stats[t]["attack"]) for t in types]
            avg_defenses = [np.mean(type_stats[t]["defense"]) for t in types]
            
            ax4.scatter(avg_attacks, avg_defenses, s=100, alpha=0.7, c='teal', edgecolors='black')
            for i, t in enumerate(types):
                ax4.annotate(t, (avg_attacks[i], avg_defenses[i]), fontsize=8, ha='center')
            ax4.set_xlabel("Average Attack")
            ax4.set_ylabel("Average Defense")
            ax4.set_title("Type: Attack vs Defense", fontweight='bold')
        
        plt.tight_layout()
        output_path = self.output_dir / "attribute_correlations.png"
        plt.savefig(output_path, dpi=OUTPUT_SETTINGS["chart_dpi"], bbox_inches='tight')
        plt.close()
        
        print(f"Saved: {output_path}")
        return output_path
    
    def generate_type_report(self, merged_df=None):
        """Generate a comprehensive text report of type analysis."""
        if merged_df is None:
            merged_df = self.merge_data()
        
        if merged_df is None or merged_df.empty:
            return None
        
        type_colors, color_counts = self.analyze_type_colors(merged_df)
        type_shapes, shape_counts = self.analyze_type_shapes(merged_df)
        
        report_lines = [
            "=" * 60,
            "POKEMON TYPE VISUAL ANALYSIS REPORT",
            "=" * 60,
            f"\nTotal Pokemon Analyzed: {len(merged_df)}",
            f"Total Types: {len(type_colors)}",
            "\n" + "-" * 40,
            "TYPE BREAKDOWN",
            "-" * 40,
        ]
        
        for ptype in sorted(type_colors.keys()):
            count = color_counts.get(ptype, 0)
            colors = type_colors.get(ptype, {})
            shapes = type_shapes.get(ptype, {})
            
            top_colors = sorted(colors.items(), key=lambda x: x[1], reverse=True)[:5]
            top_shapes = sorted(shapes.items(), key=lambda x: x[1], reverse=True)[:3]
            
            report_lines.append(f"\n{ptype.upper()} ({count} Pokemon)")
            report_lines.append(f"  Top Colors: {', '.join([f'{c}({p:.1f}%)' for c, p in top_colors])}")
            report_lines.append(f"  Top Shapes: {', '.join([f'{s}({p:.1f}%)' for s, p in top_shapes])}")
        
        report_lines.extend([
            "\n" + "-" * 40,
            "VISUAL PATTERNS",
            "-" * 40,
        ])
        
        for attr, expected_colors in ATTRIBUTE_COLOR_ASSOCIATIONS.items():
            matching_types = []
            for ptype, colors in type_colors.items():
                top_type_colors = set(list(colors.keys())[:5])
                overlap = len(set(expected_colors) & top_type_colors)
                if overlap >= 2:
                    matching_types.append(ptype)
            if matching_types:
                report_lines.append(f"\n'{attr.upper()}' visual pattern matches: {', '.join(matching_types)}")
        
        report_text = "\n".join(report_lines)
        
        output_path = self.output_dir / "type_analysis_report.txt"
        with open(output_path, 'w') as f:
            f.write(report_text)
        
        print(f"Saved: {output_path}")
        print("\n" + report_text)
        
        return output_path
    
    def generate_all_analysis(self):
        """Generate all analysis outputs."""
        print("\n=== Starting Type Analysis ===\n")
        
        merged_df = self.merge_data()
        
        if merged_df is None or merged_df.empty:
            print("Cannot generate analysis without merged data.")
            return
        
        print("\n--- Generating Static Charts ---")
        self.create_type_color_heatmap_static(merged_df)
        self.create_type_shape_heatmap_static(merged_df)
        self.create_attribute_correlation_chart(merged_df)
        
        print("\n--- Generating Interactive Dashboard ---")
        self.create_type_analysis_interactive(merged_df)
        
        print("\n--- Generating Report ---")
        self.generate_type_report(merged_df)
        
        print(f"\n=== All analysis saved to: {self.output_dir} ===")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Analyze type-visual correlations")
    parser.add_argument("scan_csv", help="Path to scan results CSV")
    parser.add_argument("-t", "--types", help="Path to type data CSV/JSON")
    parser.add_argument("-o", "--output", default="output/analysis", help="Output directory")
    parser.add_argument("--fetch-pokemon", action="store_true", help="Fetch Pokemon type data from PokeAPI")
    parser.add_argument("--save-types", help="Save fetched type data to file")
    
    args = parser.parse_args()
    
    analyzer = TypeAnalyzer(args.scan_csv, type_data_path=args.types, output_dir=args.output)
    
    if args.fetch_pokemon:
        analyzer.fetch_pokemon_types(save_path=args.save_types)
    
    if analyzer.type_df is not None:
        analyzer.generate_all_analysis()
    else:
        print("No type data available. Use --types to load or --fetch-pokemon to fetch.")


if __name__ == "__main__":
    main()
