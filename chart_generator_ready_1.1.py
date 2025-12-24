"""
Chart Generator for Game Image Analysis
Creates static (PNG) and interactive (HTML) visualizations from CSV data.
"""

import pandas as pd
import numpy as np
import json
import os
from pathlib import Path
from collections import defaultdict
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import to_rgba
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from config import COLOR_PALETTE, COLOR_CATEGORIES, SHAPE_DEFINITIONS, OUTPUT_SETTINGS


class ChartGenerator:
    def __init__(self, csv_path, output_dir="output/charts"):
        self.csv_path = Path(csv_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.df = pd.read_csv(csv_path)
        self._parse_json_columns()
        
    def _parse_json_columns(self):
        """Parse JSON columns in the dataframe."""
        json_cols = ["colors_json", "shapes_json", "color_shape_combos_json"]
        for col in json_cols:
            if col in self.df.columns:
                self.df[col] = self.df[col].apply(lambda x: json.loads(x) if pd.notna(x) else {})
    
    def _get_color_hex(self, color_name):
        """Get hex color code for a color name."""
        if color_name in COLOR_PALETTE:
            return COLOR_PALETTE[color_name]["hex"]
        return "#888888"
    
    def aggregate_colors(self):
        """Aggregate color data across all entries."""
        color_totals = defaultdict(float)
        for colors in self.df["colors_json"]:
            for color, pct in colors.items():
                color_totals[color] += pct
        
        total = sum(color_totals.values())
        if total > 0:
            color_totals = {k: v/total * 100 for k, v in color_totals.items()}
        
        return dict(sorted(color_totals.items(), key=lambda x: x[1], reverse=True))
    
    def aggregate_shapes(self):
        """Aggregate shape data across all entries."""
        shape_totals = defaultdict(float)
        for shapes in self.df["shapes_json"]:
            for shape, pct in shapes.items():
                shape_totals[shape] += pct
        
        total = sum(shape_totals.values())
        if total > 0:
            shape_totals = {k: v/total * 100 for k, v in shape_totals.items()}
        
        return dict(sorted(shape_totals.items(), key=lambda x: x[1], reverse=True))
    
    def aggregate_color_shape_combos(self):
        """Aggregate color-shape combination data."""
        combos = defaultdict(lambda: defaultdict(float))
        
        for combo_data in self.df["color_shape_combos_json"]:
            for shape, colors in combo_data.items():
                for color, pct in colors.items():
                    combos[shape][color] += pct
        
        for shape in combos:
            total = sum(combos[shape].values())
            if total > 0:
                combos[shape] = {k: v/total * 100 for k, v in combos[shape].items()}
        
        return dict(combos)
    
    # ========== STATIC CHARTS (Matplotlib) ==========
    
    def create_color_frequency_chart_static(self, top_n=20):
        """Create a static bar chart of color frequencies."""
        colors = self.aggregate_colors()
        top_colors = dict(list(colors.items())[:top_n])
        
        fig, ax = plt.subplots(figsize=OUTPUT_SETTINGS["figure_size"])
        
        names = list(top_colors.keys())
        values = list(top_colors.values())
        hex_colors = [self._get_color_hex(c) for c in names]
        
        bars = ax.barh(range(len(names)), values, color=hex_colors, edgecolor='black', linewidth=0.5)
        
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(names)
        ax.invert_yaxis()
        ax.set_xlabel("Frequency (%)")
        ax.set_title(f"Top {top_n} Colors Across All Characters", fontsize=14, fontweight='bold')
        
        for i, (bar, val) in enumerate(zip(bars, values)):
            ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height()/2,
                   f'{val:.1f}%', va='center', fontsize=9)
        
        plt.tight_layout()
        output_path = self.output_dir / "color_frequency_static.png"
        plt.savefig(output_path, dpi=OUTPUT_SETTINGS["chart_dpi"], bbox_inches='tight')
        plt.close()
        print(f"Saved: {output_path}")
        return output_path
    
    def create_shape_frequency_chart_static(self):
        """Create a static bar chart of shape frequencies."""
        shapes = self.aggregate_shapes()
        
        fig, ax = plt.subplots(figsize=(10, 6))
        
        names = list(shapes.keys())
        values = list(shapes.values())
        
        colors = plt.cm.viridis(np.linspace(0.2, 0.8, len(names)))
        bars = ax.bar(range(len(names)), values, color=colors, edgecolor='black', linewidth=0.5)
        
        ax.set_xticks(range(len(names)))
        ax.set_xticklabels(names, rotation=45, ha='right')
        ax.set_ylabel("Frequency (%)")
        ax.set_title("Shape Distribution Across All Characters", fontsize=14, fontweight='bold')
        
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                   f'{val:.1f}%', ha='center', fontsize=9)
        
        plt.tight_layout()
        output_path = self.output_dir / "shape_frequency_static.png"
        plt.savefig(output_path, dpi=OUTPUT_SETTINGS["chart_dpi"], bbox_inches='tight')
        plt.close()
        print(f"Saved: {output_path}")
        return output_path
    
    def create_color_shape_heatmap_static(self, top_colors=15, top_shapes=10):
        """Create a static heatmap of color-shape combinations."""
        combos = self.aggregate_color_shape_combos()
        
        all_colors = set()
        for shape_colors in combos.values():
            all_colors.update(shape_colors.keys())
        
        color_totals = defaultdict(float)
        for shape_colors in combos.values():
            for color, pct in shape_colors.items():
                color_totals[color] += pct
        
        top_color_names = sorted(color_totals.keys(), key=lambda x: color_totals[x], reverse=True)[:top_colors]
        shape_names = list(combos.keys())[:top_shapes]
        
        matrix = np.zeros((len(shape_names), len(top_color_names)))
        for i, shape in enumerate(shape_names):
            for j, color in enumerate(top_color_names):
                matrix[i, j] = combos.get(shape, {}).get(color, 0)
        
        fig, ax = plt.subplots(figsize=(14, 8))
        
        im = ax.imshow(matrix, cmap='YlOrRd', aspect='auto')
        
        ax.set_xticks(range(len(top_color_names)))
        ax.set_xticklabels(top_color_names, rotation=45, ha='right')
        ax.set_yticks(range(len(shape_names)))
        ax.set_yticklabels(shape_names)
        
        for i in range(len(shape_names)):
            for j in range(len(top_color_names)):
                val = matrix[i, j]
                if val > 0:
                    color = 'white' if val > matrix.max() * 0.5 else 'black'
                    ax.text(j, i, f'{val:.1f}', ha='center', va='center', color=color, fontsize=8)
        
        plt.colorbar(im, label='Frequency (%)')
        ax.set_title("Color-Shape Combinations Heatmap", fontsize=14, fontweight='bold')
        
        plt.tight_layout()
        output_path = self.output_dir / "color_shape_heatmap_static.png"
        plt.savefig(output_path, dpi=OUTPUT_SETTINGS["chart_dpi"], bbox_inches='tight')
        plt.close()
        print(f"Saved: {output_path}")
        return output_path
    
    def create_color_category_chart_static(self):
        """Create a pie chart of color categories (warm, cool, neutral, etc.)."""
        colors = self.aggregate_colors()
        
        category_totals = defaultdict(float)
        for color, pct in colors.items():
            for category, category_colors in COLOR_CATEGORIES.items():
                if color in category_colors:
                    category_totals[category] += pct
                    break
        
        fig, ax = plt.subplots(figsize=(10, 8))
        
        labels = list(category_totals.keys())
        sizes = list(category_totals.values())
        
        category_colors = {
            "warm": "#FF6B6B",
            "cool": "#4ECDC4",
            "neutral": "#95A5A6",
            "vibrant": "#FF00FF",
            "pastel": "#FFB6C1",
            "dark": "#2C3E50"
        }
        pie_colors = [category_colors.get(l, "#888888") for l in labels]
        
        wedges, texts, autotexts = ax.pie(sizes, labels=labels, autopct='%1.1f%%',
                                          colors=pie_colors, startangle=90,
                                          explode=[0.02] * len(labels))
        
        ax.set_title("Color Category Distribution", fontsize=14, fontweight='bold')
        
        plt.tight_layout()
        output_path = self.output_dir / "color_categories_static.png"
        plt.savefig(output_path, dpi=OUTPUT_SETTINGS["chart_dpi"], bbox_inches='tight')
        plt.close()
        print(f"Saved: {output_path}")
        return output_path
    
    # ========== INTERACTIVE CHARTS (Plotly) ==========
    
    def create_color_frequency_chart_interactive(self, top_n=25):
        """Create an interactive bar chart of color frequencies."""
        colors = self.aggregate_colors()
        top_colors = dict(list(colors.items())[:top_n])
        
        names = list(top_colors.keys())
        values = list(top_colors.values())
        hex_colors = [self._get_color_hex(c) for c in names]
        
        fig = go.Figure(go.Bar(
            y=names,
            x=values,
            orientation='h',
            marker=dict(color=hex_colors, line=dict(color='black', width=1)),
            text=[f'{v:.1f}%' for v in values],
            textposition='outside',
            hovertemplate='<b>%{y}</b><br>Frequency: %{x:.2f}%<extra></extra>'
        ))
        
        fig.update_layout(
            title=dict(text=f"Top {top_n} Colors Across All Characters", font=dict(size=18)),
            xaxis_title="Frequency (%)",
            yaxis=dict(autorange="reversed"),
            height=max(600, top_n * 25),
            template="plotly_white",
            hoverlabel=dict(bgcolor="white")
        )
        
        output_path = self.output_dir / "color_frequency_interactive.html"
        fig.write_html(str(output_path))
        print(f"Saved: {output_path}")
        return output_path
    
    def create_shape_frequency_chart_interactive(self):
        """Create an interactive bar chart of shape frequencies."""
        shapes = self.aggregate_shapes()
        
        names = list(shapes.keys())
        values = list(shapes.values())
        
        fig = go.Figure(go.Bar(
            x=names,
            y=values,
            marker=dict(
                color=values,
                colorscale='Viridis',
                line=dict(color='black', width=1)
            ),
            text=[f'{v:.1f}%' for v in values],
            textposition='outside',
            hovertemplate='<b>%{x}</b><br>Frequency: %{y:.2f}%<extra></extra>'
        ))
        
        fig.update_layout(
            title=dict(text="Shape Distribution Across All Characters", font=dict(size=18)),
            yaxis_title="Frequency (%)",
            height=500,
            template="plotly_white"
        )
        
        output_path = self.output_dir / "shape_frequency_interactive.html"
        fig.write_html(str(output_path))
        print(f"Saved: {output_path}")
        return output_path
    
    def create_color_shape_heatmap_interactive(self, top_colors=20, top_shapes=12):
        """Create an interactive heatmap of color-shape combinations."""
        combos = self.aggregate_color_shape_combos()
        
        color_totals = defaultdict(float)
        for shape_colors in combos.values():
            for color, pct in shape_colors.items():
                color_totals[color] += pct
        
        top_color_names = sorted(color_totals.keys(), key=lambda x: color_totals[x], reverse=True)[:top_colors]
        shape_names = list(combos.keys())[:top_shapes]
        
        matrix = []
        for shape in shape_names:
            row = [combos.get(shape, {}).get(color, 0) for color in top_color_names]
            matrix.append(row)
        
        fig = go.Figure(go.Heatmap(
            z=matrix,
            x=top_color_names,
            y=shape_names,
            colorscale='YlOrRd',
            hovertemplate='<b>Shape:</b> %{y}<br><b>Color:</b> %{x}<br><b>Frequency:</b> %{z:.2f}%<extra></extra>'
        ))
        
        fig.update_layout(
            title=dict(text="Color-Shape Combinations Heatmap", font=dict(size=18)),
            xaxis=dict(tickangle=45),
            height=600,
            template="plotly_white"
        )
        
        output_path = self.output_dir / "color_shape_heatmap_interactive.html"
        fig.write_html(str(output_path))
        print(f"Saved: {output_path}")
        return output_path
    
    def create_sunburst_chart(self):
        """Create a sunburst chart showing shape -> color hierarchy."""
        combos = self.aggregate_color_shape_combos()
        
        ids = ["All"]
        labels = ["All Characters"]
        parents = [""]
        values = [100]
        colors_list = ["#FFFFFF"]
        
        for shape, shape_colors in combos.items():
            shape_total = sum(shape_colors.values())
            if shape_total > 0:
                ids.append(shape)
                labels.append(shape.capitalize())
                parents.append("All")
                values.append(shape_total)
                colors_list.append("#DDDDDD")
                
                for color, pct in sorted(shape_colors.items(), key=lambda x: x[1], reverse=True)[:8]:
                    if pct > 1:
                        ids.append(f"{shape}_{color}")
                        labels.append(color)
                        parents.append(shape)
                        values.append(pct)
                        colors_list.append(self._get_color_hex(color))
        
        fig = go.Figure(go.Sunburst(
            ids=ids,
            labels=labels,
            parents=parents,
            values=values,
            marker=dict(colors=colors_list),
            branchvalues="total",
            hovertemplate='<b>%{label}</b><br>Value: %{value:.1f}%<extra></extra>'
        ))
        
        fig.update_layout(
            title=dict(text="Shape-Color Hierarchy", font=dict(size=18)),
            height=700,
            template="plotly_white"
        )
        
        output_path = self.output_dir / "shape_color_sunburst.html"
        fig.write_html(str(output_path))
        print(f"Saved: {output_path}")
        return output_path
    
    def create_treemap_chart(self):
        """Create a treemap showing color distributions."""
        colors = self.aggregate_colors()
        
        ids = ["All"]
        labels = ["All Colors"]
        parents = [""]
        values = [100]
        hex_colors = ["#FFFFFF"]
        
        category_totals = defaultdict(float)
        color_to_category = {}
        
        for color, pct in colors.items():
            for category, category_colors in COLOR_CATEGORIES.items():
                if color in category_colors:
                    category_totals[category] += pct
                    color_to_category[color] = category
                    break
        
        for category, total in category_totals.items():
            ids.append(category)
            labels.append(category.capitalize())
            parents.append("All")
            values.append(total)
            hex_colors.append("#CCCCCC")
        
        for color, pct in colors.items():
            if pct > 0.5:
                category = color_to_category.get(color, "neutral")
                ids.append(f"{category}_{color}")
                labels.append(color)
                parents.append(category)
                values.append(pct)
                hex_colors.append(self._get_color_hex(color))
        
        fig = go.Figure(go.Treemap(
            ids=ids,
            labels=labels,
            parents=parents,
            values=values,
            marker=dict(colors=hex_colors),
            branchvalues="total",
            hovertemplate='<b>%{label}</b><br>Frequency: %{value:.2f}%<extra></extra>'
        ))
        
        fig.update_layout(
            title=dict(text="Color Distribution Treemap", font=dict(size=18)),
            height=700,
            template="plotly_white"
        )
        
        output_path = self.output_dir / "color_treemap.html"
        fig.write_html(str(output_path))
        print(f"Saved: {output_path}")
        return output_path
    
    def generate_all_charts(self):
        """Generate all static and interactive charts."""
        print("\n=== Generating Static Charts (PNG) ===")
        self.create_color_frequency_chart_static()
        self.create_shape_frequency_chart_static()
        self.create_color_shape_heatmap_static()
        self.create_color_category_chart_static()
        
        print("\n=== Generating Interactive Charts (HTML) ===")
        self.create_color_frequency_chart_interactive()
        self.create_shape_frequency_chart_interactive()
        self.create_color_shape_heatmap_interactive()
        self.create_sunburst_chart()
        self.create_treemap_chart()
        
        print(f"\nAll charts saved to: {self.output_dir}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate charts from scan results")
    parser.add_argument("csv", help="Path to scan results CSV")
    parser.add_argument("-o", "--output", default="output/charts", help="Output directory")
    parser.add_argument("--static-only", action="store_true", help="Generate only static charts")
    parser.add_argument("--interactive-only", action="store_true", help="Generate only interactive charts")
    
    args = parser.parse_args()
    
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


if __name__ == "__main__":
    main()
