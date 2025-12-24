"""
Chart Generator for Game Image Analysis
Creates static (PNG) and interactive (HTML) visualizations from CSV data.
Generates both RAW and FILTERED versions of all charts.

Filtered version removes:
- Outline colors (black, onyx, charcoal) when below threshold
- Low-percentage colors that are likely artifacts
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


# Colors typically associated with outlines, shadows, and anti-aliasing
OUTLINE_COLORS = {"black", "onyx", "charcoal", "slate"}

# Default threshold: if an outline color is below this %, it's likely an artifact
DEFAULT_OUTLINE_THRESHOLD = 8.0

# Minimum percentage to include any color in filtered results
MIN_COLOR_THRESHOLD = 1.0


class ChartGenerator:
    def __init__(self, csv_path, output_dir="output/charts", 
                 outline_threshold=DEFAULT_OUTLINE_THRESHOLD,
                 min_color_threshold=MIN_COLOR_THRESHOLD):
        self.csv_path = Path(csv_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.df = pd.read_csv(csv_path)
        self._parse_json_columns()
        
        # Filtering settings
        self.outline_threshold = outline_threshold
        self.min_color_threshold = min_color_threshold
        
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
    
    def _filter_colors(self, color_dict):
        """
        Filter out outline/artifact colors from a color dictionary.
        
        Rules:
        - Remove outline colors (black, onyx, charcoal, slate) if below threshold
        - Remove any color below minimum threshold
        - Renormalize percentages after filtering
        """
        filtered = {}
        
        for color, pct in color_dict.items():
            # Skip outline colors below threshold
            if color in OUTLINE_COLORS and pct < self.outline_threshold:
                continue
            # Skip any color below minimum threshold
            if pct < self.min_color_threshold:
                continue
            filtered[color] = pct
        
        # Renormalize to 100%
        total = sum(filtered.values())
        if total > 0:
            filtered = {k: (v / total) * 100 for k, v in filtered.items()}
        
        return dict(sorted(filtered.items(), key=lambda x: x[1], reverse=True))
    
    def aggregate_colors(self, filtered=False):
        """Aggregate color data across all entries."""
        color_totals = defaultdict(float)
        
        for colors in self.df["colors_json"]:
            if filtered:
                colors = self._filter_colors(colors)
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
    
    def aggregate_color_shape_combos(self, filtered=False):
        """Aggregate color-shape combination data."""
        combos = defaultdict(lambda: defaultdict(float))
        
        for combo_data in self.df["color_shape_combos_json"]:
            for shape, colors in combo_data.items():
                if filtered:
                    colors = self._filter_colors(colors)
                for color, pct in colors.items():
                    combos[shape][color] += pct
        
        for shape in combos:
            total = sum(combos[shape].values())
            if total > 0:
                combos[shape] = {k: v/total * 100 for k, v in combos[shape].items()}
        
        return dict(combos)
    
    def aggregate_color_combinations(self, filtered=False, min_pct=5.0, top_n_colors=50):
        """
        Analyze which colors appear together in the same character.
        
        Args:
            filtered: Whether to filter out outline colors
            min_pct: Minimum percentage for a color to be considered "present" in a character
            top_n_colors: Only consider the top N colors per character
            
        Returns:
            Dictionary with:
            - 'pairs': {(color1, color2): count} - how many characters have this pair
            - 'triplets': {(color1, color2, color3): count} - how many have this triplet
            - 'palettes': [{colors: [...], count: N, examples: [...]}] - full palettes
        """
        from itertools import combinations
        
        pair_counts = defaultdict(int)
        triplet_counts = defaultdict(int)
        palette_counts = defaultdict(list)  # palette tuple -> list of character names
        
        for idx, row in self.df.iterrows():
            colors = row["colors_json"]
            name = row.get("name", f"character_{idx}")
            
            if filtered:
                colors = self._filter_colors(colors)
            
            # Get significant colors for this character
            significant_colors = []
            for color, pct in colors.items():
                if pct >= min_pct:
                    significant_colors.append(color)
                if len(significant_colors) >= top_n_colors:
                    break
            
            if len(significant_colors) < 2:
                continue
            
            # Sort colors alphabetically to ensure consistent keys
            significant_colors_sorted = tuple(sorted(significant_colors))
            palette_counts[significant_colors_sorted].append(name)
            
            # Count pairs
            for pair in combinations(sorted(significant_colors), 2):
                pair_counts[pair] += 1
            
            # Count triplets (if at least 3 colors)
            if len(significant_colors) >= 3:
                for triplet in combinations(sorted(significant_colors), 3):
                    triplet_counts[triplet] += 1
        
        # Sort by frequency
        sorted_pairs = dict(sorted(pair_counts.items(), key=lambda x: x[1], reverse=True))
        sorted_triplets = dict(sorted(triplet_counts.items(), key=lambda x: x[1], reverse=True))
        
        # Convert palette_counts to list format
        palettes = []
        for palette, names in sorted(palette_counts.items(), key=lambda x: len(x[1]), reverse=True):
            palettes.append({
                "colors": list(palette),
                "count": len(names),
                "examples": names[:5]  # First 5 examples
            })
        
        return {
            "pairs": sorted_pairs,
            "triplets": sorted_triplets,
            "palettes": palettes
        }
    
    # ========== STATIC CHARTS (Matplotlib) ==========
    
    def create_color_frequency_chart_static(self, top_n=100, filtered=False):
        """Create a static bar chart of color frequencies."""
        colors = self.aggregate_colors(filtered=filtered)
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
        
        title_suffix = " (Filtered)" if filtered else " (Raw)"
        ax.set_title(f"Top {top_n} Colors Across All Characters{title_suffix}", fontsize=14, fontweight='bold')
        
        for i, (bar, val) in enumerate(zip(bars, values)):
            ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height()/2,
                   f'{val:.1f}%', va='center', fontsize=9)
        
        plt.tight_layout()
        
        filename = "color_frequency_filtered.png" if filtered else "color_frequency_raw.png"
        output_path = self.output_dir / filename
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
    
    def create_color_shape_heatmap_static(self, top_colors=100, top_shapes=12, filtered=False):
        """Create a static heatmap of color-shape combinations."""
        combos = self.aggregate_color_shape_combos(filtered=filtered)
        
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
        title_suffix = " (Filtered)" if filtered else " (Raw)"
        ax.set_title(f"Color-Shape Combinations Heatmap{title_suffix}", fontsize=14, fontweight='bold')
        
        plt.tight_layout()
        filename = "color_shape_heatmap_filtered.png" if filtered else "color_shape_heatmap_raw.png"
        output_path = self.output_dir / filename
        plt.savefig(output_path, dpi=OUTPUT_SETTINGS["chart_dpi"], bbox_inches='tight')
        plt.close()
        print(f"Saved: {output_path}")
        return output_path
    
    def create_color_category_chart_static(self, filtered=False):
        """Create a pie chart of color categories (warm, cool, neutral, etc.)."""
        colors = self.aggregate_colors(filtered=filtered)
        
        category_totals = defaultdict(float)
        for color, pct in colors.items():
            for category, category_colors in COLOR_CATEGORIES.items():
                if color in category_colors:
                    category_totals[category] += pct
                    break
        
        fig, ax = plt.subplots(figsize=(15, 8))
        
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
        
        title_suffix = " (Filtered)" if filtered else " (Raw)"
        ax.set_title(f"Color Category Distribution{title_suffix}", fontsize=14, fontweight='bold')
        
        plt.tight_layout()
        filename = "color_categories_filtered.png" if filtered else "color_categories_raw.png"
        output_path = self.output_dir / filename
        plt.savefig(output_path, dpi=OUTPUT_SETTINGS["chart_dpi"], bbox_inches='tight')
        plt.close()
        print(f"Saved: {output_path}")
        return output_path
    
    def create_color_pairs_chart_static(self, top_n=100, filtered=False):
        """Create a static bar chart showing most common color pairs."""
        combo_data = self.aggregate_color_combinations(filtered=filtered)
        pairs = combo_data["pairs"]
        
        if not pairs:
            print("No color pairs found")
            return None
        
        # Get top pairs
        top_pairs = dict(list(pairs.items())[:top_n])
        
        fig, ax = plt.subplots(figsize=(14, 10))
        
        labels = []
        values = []
        bar_colors = []
        
        for (color1, color2), count in top_pairs.items():
            labels.append(f"{color1} + {color2}")
            values.append(count)
            # Use gradient between the two colors
            bar_colors.append(self._get_color_hex(color1))
        
        y_pos = range(len(labels))
        bars = ax.barh(y_pos, values, color=bar_colors, edgecolor='black', linewidth=0.5)
        
        # Add second color as a marker or annotation
        for i, ((color1, color2), count) in enumerate(top_pairs.items()):
            # Draw a small square of the second color at the end of the bar
            rect = plt.Rectangle((values[i] + 0.5, i - 0.3), max(values) * 0.03, 0.6,
                                 color=self._get_color_hex(color2), ec='black', linewidth=0.5)
            ax.add_patch(rect)
            ax.text(values[i] + max(values) * 0.05, i, f'{count}', va='center', fontsize=9)
        
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels)
        ax.invert_yaxis()
        ax.set_xlabel("Number of Characters")
        
        title_suffix = " (Filtered)" if filtered else " (Raw)"
        ax.set_title(f"Most Common Color Pairs{title_suffix}", fontsize=14, fontweight='bold')
        
        plt.tight_layout()
        filename = "color_pairs_filtered.png" if filtered else "color_pairs_raw.png"
        output_path = self.output_dir / filename
        plt.savefig(output_path, dpi=OUTPUT_SETTINGS["chart_dpi"], bbox_inches='tight')
        plt.close()
        print(f"Saved: {output_path}")
        return output_path
    
    def create_color_triplets_chart_static(self, top_n=100, filtered=False):
        """Create a static bar chart showing most common color triplets."""
        combo_data = self.aggregate_color_combinations(filtered=filtered)
        triplets = combo_data["triplets"]
        
        if not triplets:
            print("No color triplets found")
            return None
        
        # Get top triplets
        top_triplets = dict(list(triplets.items())[:top_n])
        
        fig, ax = plt.subplots(figsize=(14, 10))
        
        labels = []
        values = []
        
        for (color1, color2, color3), count in top_triplets.items():
            labels.append(f"{color1} + {color2} + {color3}")
            values.append(count)
        
        y_pos = range(len(labels))
        
        # Create stacked bars showing all three colors
        bar_height = 0.6
        for i, ((color1, color2, color3), count) in enumerate(top_triplets.items()):
            # Draw three color segments
            segment_width = count / 3
            ax.barh(i, segment_width, height=bar_height, left=0,
                   color=self._get_color_hex(color1), edgecolor='black', linewidth=0.5)
            ax.barh(i, segment_width, height=bar_height, left=segment_width,
                   color=self._get_color_hex(color2), edgecolor='black', linewidth=0.5)
            ax.barh(i, segment_width, height=bar_height, left=segment_width*2,
                   color=self._get_color_hex(color3), edgecolor='black', linewidth=0.5)
            ax.text(count + 0.5, i, f'{count}', va='center', fontsize=9)
        
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels)
        ax.invert_yaxis()
        ax.set_xlabel("Number of Characters")
        
        title_suffix = " (Filtered)" if filtered else " (Raw)"
        ax.set_title(f"Most Common Color Triplets{title_suffix}", fontsize=14, fontweight='bold')
        
        plt.tight_layout()
        filename = "color_triplets_filtered.png" if filtered else "color_triplets_raw.png"
        output_path = self.output_dir / filename
        plt.savefig(output_path, dpi=OUTPUT_SETTINGS["chart_dpi"], bbox_inches='tight')
        plt.close()
        print(f"Saved: {output_path}")
        return output_path

    # ========== INTERACTIVE CHARTS (Plotly) ==========
    
    def create_color_frequency_chart_interactive(self, top_n=100, filtered=False):
        """Create an interactive bar chart of color frequencies."""
        colors = self.aggregate_colors(filtered=filtered)
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
        
        title_suffix = " (Filtered)" if filtered else " (Raw)"
        fig.update_layout(
            title=dict(text=f"Top {top_n} Colors Across All Characters{title_suffix}", font=dict(size=18)),
            xaxis_title="Frequency (%)",
            yaxis=dict(autorange="reversed"),
            height=max(600, top_n * 25),
            template="plotly_white",
            hoverlabel=dict(bgcolor="white")
        )
        
        filename = "color_frequency_filtered.html" if filtered else "color_frequency_raw.html"
        output_path = self.output_dir / filename
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
    
    def create_color_shape_heatmap_interactive(self, top_colors=100, top_shapes=12, filtered=False):
        """Create an interactive heatmap of color-shape combinations."""
        combos = self.aggregate_color_shape_combos(filtered=filtered)
        
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
        
        title_suffix = " (Filtered)" if filtered else " (Raw)"
        fig.update_layout(
            title=dict(text=f"Color-Shape Combinations Heatmap{title_suffix}", font=dict(size=18)),
            xaxis=dict(tickangle=45),
            height=600,
            template="plotly_white"
        )
        
        filename = "color_shape_heatmap_filtered.html" if filtered else "color_shape_heatmap_raw.html"
        output_path = self.output_dir / filename
        fig.write_html(str(output_path))
        print(f"Saved: {output_path}")
        return output_path
    
    def create_sunburst_chart(self, filtered=False):
        """Create a sunburst chart showing shape -> color hierarchy."""
        combos = self.aggregate_color_shape_combos(filtered=filtered)
        
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
        
        title_suffix = " (Filtered)" if filtered else " (Raw)"
        fig.update_layout(
            title=dict(text=f"Shape-Color Hierarchy{title_suffix}", font=dict(size=18)),
            height=700,
            template="plotly_white"
        )
        
        filename = "shape_color_sunburst_filtered.html" if filtered else "shape_color_sunburst_raw.html"
        output_path = self.output_dir / filename
        fig.write_html(str(output_path))
        print(f"Saved: {output_path}")
        return output_path
    
    def create_treemap_chart(self, filtered=False):
        """Create a treemap showing color distributions."""
        colors = self.aggregate_colors(filtered=filtered)
        
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
        
        title_suffix = " (Filtered)" if filtered else " (Raw)"
        fig.update_layout(
            title=dict(text=f"Color Distribution Treemap{title_suffix}", font=dict(size=18)),
            height=700,
            template="plotly_white"
        )
        
        filename = "color_treemap_filtered.html" if filtered else "color_treemap_raw.html"
        output_path = self.output_dir / filename
        fig.write_html(str(output_path))
        print(f"Saved: {output_path}")
        return output_path
    
    def create_comparison_chart(self):
        """Create a side-by-side comparison of raw vs filtered top colors."""
        raw_colors = self.aggregate_colors(filtered=False)
        filtered_colors = self.aggregate_colors(filtered=True)
        
        # Get top 15 from each
        raw_top = dict(list(raw_colors.items())[:100])
        filtered_top = dict(list(filtered_colors.items())[:100])
        
        fig = make_subplots(rows=1, cols=2, subplot_titles=["Raw Data", "Filtered Data"])
        
        # Raw data
        fig.add_trace(
            go.Bar(
                y=list(raw_top.keys()),
                x=list(raw_top.values()),
                orientation='h',
                marker=dict(color=[self._get_color_hex(c) for c in raw_top.keys()],
                           line=dict(color='black', width=1)),
                name="Raw",
                hovertemplate='<b>%{y}</b>: %{x:.1f}%<extra></extra>'
            ),
            row=1, col=1
        )
        
        # Filtered data
        fig.add_trace(
            go.Bar(
                y=list(filtered_top.keys()),
                x=list(filtered_top.values()),
                orientation='h',
                marker=dict(color=[self._get_color_hex(c) for c in filtered_top.keys()],
                           line=dict(color='black', width=1)),
                name="Filtered",
                hovertemplate='<b>%{y}</b>: %{x:.1f}%<extra></extra>'
            ),
            row=1, col=2
        )
        
        fig.update_yaxes(autorange="reversed", row=1, col=1)
        fig.update_yaxes(autorange="reversed", row=1, col=2)
        
        fig.update_layout(
            title=dict(text="Raw vs Filtered Color Distribution Comparison", font=dict(size=18)),
            height=600,
            showlegend=False,
            template="plotly_white"
        )
        
        output_path = self.output_dir / "raw_vs_filtered_comparison.html"
        fig.write_html(str(output_path))
        print(f"Saved: {output_path}")
        return output_path
    
    def create_color_combinations_interactive(self, top_n=100, filtered=False):
        """Create an interactive visualization of color combinations."""
        combo_data = self.aggregate_color_combinations(filtered=filtered)
        pairs = combo_data["pairs"]
        triplets = combo_data["triplets"]
        palettes = combo_data["palettes"]
        
        if not pairs:
            print("No color combinations found")
            return None
        
        # Create subplots
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=["Top Color Pairs", "Top Color Triplets", 
                           "Color Pair Network", "Common Palettes"],
            specs=[[{"type": "bar"}, {"type": "bar"}],
                   [{"type": "scatter"}, {"type": "table"}]],
            vertical_spacing=0.12,
            horizontal_spacing=0.1
        )
        
        # 1. Top pairs bar chart
        top_pairs = dict(list(pairs.items())[:top_n])
        pair_labels = [f"{c1} + {c2}" for (c1, c2) in top_pairs.keys()]
        pair_values = list(top_pairs.values())
        pair_colors = [self._get_color_hex(list(top_pairs.keys())[i][0]) for i in range(len(top_pairs))]
        
        fig.add_trace(
            go.Bar(
                y=pair_labels,
                x=pair_values,
                orientation='h',
                marker=dict(color=pair_colors, line=dict(color='black', width=1)),
                hovertemplate='<b>%{y}</b><br>Characters: %{x}<extra></extra>'
            ),
            row=1, col=1
        )
        
        # 2. Top triplets bar chart
        if triplets:
            top_triplets = dict(list(triplets.items())[:15])
            triplet_labels = [f"{c1}+{c2}+{c3}" for (c1, c2, c3) in top_triplets.keys()]
            triplet_values = list(top_triplets.values())
            triplet_colors = [self._get_color_hex(list(top_triplets.keys())[i][0]) for i in range(len(top_triplets))]
            
            fig.add_trace(
                go.Bar(
                    y=triplet_labels,
                    x=triplet_values,
                    orientation='h',
                    marker=dict(color=triplet_colors, line=dict(color='black', width=1)),
                    hovertemplate='<b>%{y}</b><br>Characters: %{x}<extra></extra>'
                ),
                row=1, col=2
            )
        
        # 3. Network-style scatter plot showing color relationships
        # Create nodes for each unique color and edges for pairs
        color_nodes = set()
        for (c1, c2) in list(pairs.keys())[:50]:
            color_nodes.add(c1)
            color_nodes.add(c2)
        
        color_list = list(color_nodes)
        n_colors = len(color_list)
        
        # Position colors in a circle
        angles = np.linspace(0, 2 * np.pi, n_colors, endpoint=False)
        x_pos = {c: np.cos(angles[i]) for i, c in enumerate(color_list)}
        y_pos = {c: np.sin(angles[i]) for i, c in enumerate(color_list)}
        
        # Draw edges (lines between paired colors)
        edge_x = []
        edge_y = []
        for (c1, c2), count in list(pairs.items())[:30]:
            if c1 in x_pos and c2 in x_pos:
                edge_x.extend([x_pos[c1], x_pos[c2], None])
                edge_y.extend([y_pos[c1], y_pos[c2], None])
        
        fig.add_trace(
            go.Scatter(
                x=edge_x, y=edge_y,
                mode='lines',
                line=dict(width=0.5, color='#888'),
                hoverinfo='none'
            ),
            row=2, col=1
        )
        
        # Draw nodes
        fig.add_trace(
            go.Scatter(
                x=[x_pos[c] for c in color_list],
                y=[y_pos[c] for c in color_list],
                mode='markers+text',
                marker=dict(
                    size=15,
                    color=[self._get_color_hex(c) for c in color_list],
                    line=dict(width=1, color='black')
                ),
                text=color_list,
                textposition="top center",
                textfont=dict(size=8),
                hovertemplate='<b>%{text}</b><extra></extra>'
            ),
            row=2, col=1
        )
        
        # 4. Palettes table
        if palettes:
            top_palettes = palettes[:10]
            palette_strs = [", ".join(p["colors"]) for p in top_palettes]
            palette_counts = [p["count"] for p in top_palettes]
            palette_examples = [", ".join(p["examples"][:3]) for p in top_palettes]
            
            fig.add_trace(
                go.Table(
                    header=dict(
                        values=["Color Palette", "Count", "Examples"],
                        fill_color='paleturquoise',
                        align='left',
                        font=dict(size=11)
                    ),
                    cells=dict(
                        values=[palette_strs, palette_counts, palette_examples],
                        fill_color='lavender',
                        align='left',
                        font=dict(size=10)
                    )
                ),
                row=2, col=2
            )
        
        fig.update_yaxes(autorange="reversed", row=1, col=1)
        fig.update_yaxes(autorange="reversed", row=1, col=2)
        fig.update_xaxes(showgrid=False, zeroline=False, showticklabels=False, row=2, col=1)
        fig.update_yaxes(showgrid=False, zeroline=False, showticklabels=False, row=2, col=1)
        
        title_suffix = " (Filtered)" if filtered else " (Raw)"
        fig.update_layout(
            title=dict(text=f"Color Combinations Analysis{title_suffix}", font=dict(size=18)),
            height=900,
            showlegend=False,
            template="plotly_white"
        )
        
        filename = "color_combinations_filtered.html" if filtered else "color_combinations_raw.html"
        output_path = self.output_dir / filename
        fig.write_html(str(output_path))
        print(f"Saved: {output_path}")
        return output_path
    
    def generate_all_charts(self):
        """Generate all static and interactive charts (both raw and filtered)."""
        
        print("\n" + "=" * 60)
        print("GENERATING RAW CHARTS (unfiltered data)")
        print("=" * 60)
        
        print("\n--- Static Charts (PNG) - Raw ---")
        self.create_color_frequency_chart_static(filtered=False)
        self.create_shape_frequency_chart_static()
        self.create_color_shape_heatmap_static(filtered=False)
        self.create_color_category_chart_static(filtered=False)
        self.create_color_pairs_chart_static(filtered=False)
        self.create_color_triplets_chart_static(filtered=False)
        
        print("\n--- Interactive Charts (HTML) - Raw ---")
        self.create_color_frequency_chart_interactive(filtered=False)
        self.create_shape_frequency_chart_interactive()
        self.create_color_shape_heatmap_interactive(filtered=False)
        self.create_sunburst_chart(filtered=False)
        self.create_treemap_chart(filtered=False)
        self.create_color_combinations_interactive(filtered=False)
        
        print("\n" + "=" * 60)
        print("GENERATING FILTERED CHARTS (outline colors removed)")
        print(f"  - Outline colors ({', '.join(OUTLINE_COLORS)}) removed if < {self.outline_threshold}%")
        print(f"  - All colors < {self.min_color_threshold}% removed")
        print("=" * 60)
        
        print("\n--- Static Charts (PNG) - Filtered ---")
        self.create_color_frequency_chart_static(filtered=True)
        self.create_color_shape_heatmap_static(filtered=True)
        self.create_color_category_chart_static(filtered=True)
        self.create_color_pairs_chart_static(filtered=True)
        self.create_color_triplets_chart_static(filtered=True)
        
        print("\n--- Interactive Charts (HTML) - Filtered ---")
        self.create_color_frequency_chart_interactive(filtered=True)
        self.create_color_shape_heatmap_interactive(filtered=True)
        self.create_sunburst_chart(filtered=True)
        self.create_treemap_chart(filtered=True)
        self.create_color_combinations_interactive(filtered=True)
        
        print("\n--- Comparison Chart ---")
        self.create_comparison_chart()
        
        print(f"\n{'=' * 60}")
        print(f"All charts saved to: {self.output_dir}")
        print(f"{'=' * 60}")
        print("\nGenerated files:")
        print("  RAW: *_raw.png, *_raw.html")
        print("  FILTERED: *_filtered.png, *_filtered.html")
        print("  COMPARISON: raw_vs_filtered_comparison.html")
        print("  COLOR COMBOS: color_pairs_*.png, color_triplets_*.png, color_combinations_*.html")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate charts from scan results")
    parser.add_argument("csv", help="Path to scan results CSV")
    parser.add_argument("-o", "--output", default="output/charts", help="Output directory")
    parser.add_argument("--static-only", action="store_true", help="Generate only static charts")
    parser.add_argument("--interactive-only", action="store_true", help="Generate only interactive charts")
    parser.add_argument("--raw-only", action="store_true", help="Generate only raw (unfiltered) charts")
    parser.add_argument("--filtered-only", action="store_true", help="Generate only filtered charts")
    parser.add_argument("--outline-threshold", type=float, default=DEFAULT_OUTLINE_THRESHOLD,
                       help=f"Threshold for outline colors (default: {DEFAULT_OUTLINE_THRESHOLD}%%)")
    parser.add_argument("--min-color", type=float, default=MIN_COLOR_THRESHOLD,
                       help=f"Minimum color percentage to include (default: {MIN_COLOR_THRESHOLD}%%)")
    
    args = parser.parse_args()
    
    generator = ChartGenerator(
        args.csv, 
        output_dir=args.output,
        outline_threshold=args.outline_threshold,
        min_color_threshold=args.min_color
    )
    
    if args.raw_only:
        print("Generating RAW charts only...")
        generator.create_color_frequency_chart_static(filtered=False)
        generator.create_shape_frequency_chart_static()
        generator.create_color_shape_heatmap_static(filtered=False)
        generator.create_color_category_chart_static(filtered=False)
        generator.create_color_frequency_chart_interactive(filtered=False)
        generator.create_shape_frequency_chart_interactive()
        generator.create_color_shape_heatmap_interactive(filtered=False)
        generator.create_sunburst_chart(filtered=False)
        generator.create_treemap_chart(filtered=False)
    elif args.filtered_only:
        print("Generating FILTERED charts only...")
        generator.create_color_frequency_chart_static(filtered=True)
        generator.create_shape_frequency_chart_static()
        generator.create_color_shape_heatmap_static(filtered=True)
        generator.create_color_category_chart_static(filtered=True)
        generator.create_color_frequency_chart_interactive(filtered=True)
        generator.create_shape_frequency_chart_interactive()
        generator.create_color_shape_heatmap_interactive(filtered=True)
        generator.create_sunburst_chart(filtered=True)
        generator.create_treemap_chart(filtered=True)
    else:
        generator.generate_all_charts()


if __name__ == "__main__":
    main()
