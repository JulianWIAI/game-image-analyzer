"""
SBS/ChartGenerator.py — Static & Interactive Chart Generator
=============================================================
Provides the ChartGenerator class, which reads a scan-results CSV produced
by ImageScanner and generates a comprehensive set of visualizations.

Two variants are produced for most charts:
  - **Raw**      : uses all detected colors, including outline/shadow colors.
  - **Filtered** : removes outline colors (black, onyx, charcoal, slate) when
                   they fall below a configurable threshold, and drops any color
                   below a minimum percentage.  This highlights the "real"
                   palette of the subject rather than rendering artifacts.

Output formats:
  - Static PNG via Matplotlib
  - Interactive HTML via Plotly

Chart types generated:
  - Color frequency bar chart  (horizontal)
  - Shape frequency bar chart
  - Color-shape combination heatmap
  - Color category pie chart   (warm / cool / neutral / vibrant / pastel / dark)
  - Color pairs bar chart      (most common two-color combinations)
  - Color triplets bar chart   (most common three-color combinations)
  - Color frequency interactive bar chart
  - Shape frequency interactive bar chart
  - Color-shape heatmap        (interactive)
  - Sunburst chart             (shape → color hierarchy)
  - Treemap chart              (color category → individual color)
  - Color combinations interactive dashboard (pairs + triplets + network + table)
  - Raw vs Filtered comparison (side-by-side)

Dependencies: Pandas, NumPy, Matplotlib, Plotly, SBS.config
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path
from collections import defaultdict
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import to_rgba
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .config import COLOR_PALETTE, COLOR_CATEGORIES, SHAPE_DEFINITIONS, OUTPUT_SETTINGS


# ---------------------------------------------------------------------------
# Module-level filtering constants
# ---------------------------------------------------------------------------

# Colors commonly produced by anti-aliasing, outlines, and shadows rather
# than the character's actual color design.
OUTLINE_COLORS = {"black", "onyx", "charcoal", "slate"}

# If an outline color's percentage is below this threshold, treat it as an
# artifact and remove it from filtered charts.
DEFAULT_OUTLINE_THRESHOLD = 8.0

# Remove any color from filtered results that is below this percentage —
# covers noise colors that are neither outline nor meaningful palette entries.
MIN_COLOR_THRESHOLD = 1.0


class ChartGenerator:
    """
    Generates static (PNG) and interactive (HTML) charts from scan-result CSV data.

    The generator supports two data modes — raw and filtered — so consumers
    can compare unprocessed detection output against a noise-reduced view.

    Attributes:
        csv_path           (Path): Path to the input CSV file.
        output_dir         (Path): Directory where chart files are saved.
        df                 (DataFrame): Parsed scan results with JSON columns
                           already decoded to Python dicts.
        outline_threshold  (float): Percentage below which an outline color is
                           removed in filtered mode.
        min_color_threshold(float): Minimum percentage for any color to survive
                           filtering.
    """

    def __init__(
        self,
        csv_path: str,
        output_dir: str = "output/charts",
        outline_threshold: float = DEFAULT_OUTLINE_THRESHOLD,
        min_color_threshold: float = MIN_COLOR_THRESHOLD,
    ):
        """
        Load and prepare the scan-results CSV for chart generation.

        Args:
            csv_path             (str): Path to the CSV produced by ImageScanner.
            output_dir           (str): Directory for output chart files.
            outline_threshold    (float): Outline-color removal threshold (%).
            min_color_threshold  (float): Minimum color percentage to keep (%).
        """
        self.csv_path = Path(csv_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.df = pd.read_csv(csv_path)
        self._parse_json_columns()
        self.outline_threshold = outline_threshold
        self.min_color_threshold = min_color_threshold

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_json_columns(self):
        """Decode JSON-string columns in the dataframe to Python dicts."""
        for col in ["colors_json", "shapes_json", "color_shape_combos_json"]:
            if col in self.df.columns:
                self.df[col] = self.df[col].apply(
                    lambda x: json.loads(x) if pd.notna(x) else {}
                )

    def _get_color_hex(self, color_name: str) -> str:
        """
        Return the hex color code for a palette name.

        Args:
            color_name (str): A key from COLOR_PALETTE.

        Returns:
            str: Hex string (e.g. '#DC143C'), or '#888888' if not found.
        """
        if color_name in COLOR_PALETTE:
            return COLOR_PALETTE[color_name]["hex"]
        return "#888888"

    def _filter_colors(self, color_dict: dict) -> dict:
        """
        Remove outline / artifact colors from a color-percentage dict.

        Rules applied in order:
          1. Drop colors in OUTLINE_COLORS whose percentage is below
             ``self.outline_threshold``.
          2. Drop any remaining color below ``self.min_color_threshold``.
          3. Renormalize the surviving colors so they sum to 100 %.

        Args:
            color_dict (dict): {color_name: percentage} mapping.

        Returns:
            dict: Filtered and renormalized color-percentage mapping,
                sorted by descending percentage.
        """
        filtered = {}
        for color, pct in color_dict.items():
            if color in OUTLINE_COLORS and pct < self.outline_threshold:
                continue
            if pct < self.min_color_threshold:
                continue
            filtered[color] = pct

        total = sum(filtered.values())
        if total > 0:
            filtered = {k: (v / total) * 100 for k, v in filtered.items()}

        return dict(sorted(filtered.items(), key=lambda x: x[1], reverse=True))

    # ------------------------------------------------------------------
    # Aggregation helpers
    # ------------------------------------------------------------------

    def aggregate_colors(self, filtered: bool = False) -> dict:
        """
        Aggregate color percentages across all characters in the dataset.

        Args:
            filtered (bool): Whether to apply outline / artifact filtering
                before aggregating.

        Returns:
            dict: {color_name: aggregated_percentage}, sorted descending.
        """
        color_totals = defaultdict(float)
        for colors in self.df["colors_json"]:
            if filtered:
                colors = self._filter_colors(colors)
            for color, pct in colors.items():
                color_totals[color] += pct

        total = sum(color_totals.values())
        if total > 0:
            color_totals = {k: v / total * 100 for k, v in color_totals.items()}

        return dict(sorted(color_totals.items(), key=lambda x: x[1], reverse=True))

    def aggregate_shapes(self) -> dict:
        """
        Aggregate shape percentages across all characters in the dataset.

        Returns:
            dict: {shape_type: aggregated_percentage}, sorted descending.
        """
        shape_totals = defaultdict(float)
        for shapes in self.df["shapes_json"]:
            for shape, pct in shapes.items():
                shape_totals[shape] += pct

        total = sum(shape_totals.values())
        if total > 0:
            shape_totals = {k: v / total * 100 for k, v in shape_totals.items()}

        return dict(sorted(shape_totals.items(), key=lambda x: x[1], reverse=True))

    def aggregate_color_shape_combos(self, filtered: bool = False) -> dict:
        """
        Aggregate color-per-shape combination data across all characters.

        Args:
            filtered (bool): Whether to filter artifact colors within each
                shape's color distribution before accumulating.

        Returns:
            dict: Nested {shape_type: {color_name: normalized_percentage}}.
        """
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
                combos[shape] = {k: v / total * 100 for k, v in combos[shape].items()}

        return dict(combos)

    def aggregate_color_combinations(
        self,
        filtered: bool = False,
        min_pct: float = 5.0,
        top_n_colors: int = 50,
    ) -> dict:
        """
        Analyze how colors co-occur within the same character's palette.

        For each character, finds all "significant" colors (those that meet
        ``min_pct``) and counts every pair and triplet combination across
        the entire dataset.  Also collects full palette tuples.

        Args:
            filtered    (bool): Whether to apply artifact filtering first.
            min_pct     (float): Minimum % for a color to count as "present".
            top_n_colors(int): Maximum colors considered per character.

        Returns:
            dict with three keys:
                'pairs'    – {(color1, color2): count}
                'triplets' – {(color1, color2, color3): count}
                'palettes' – [{colors: [...], count: N, examples: [...]}]
        """
        from itertools import combinations

        pair_counts    = defaultdict(int)
        triplet_counts = defaultdict(int)
        palette_counts = defaultdict(list)

        for idx, row in self.df.iterrows():
            colors = row["colors_json"]
            name   = row.get("name", f"character_{idx}")

            if filtered:
                colors = self._filter_colors(colors)

            significant_colors = []
            for color, pct in colors.items():
                if pct >= min_pct:
                    significant_colors.append(color)
                if len(significant_colors) >= top_n_colors:
                    break

            if len(significant_colors) < 2:
                continue

            # Alphabetical sort ensures consistent tuple keys
            significant_colors_sorted = tuple(sorted(significant_colors))
            palette_counts[significant_colors_sorted].append(name)

            for pair in combinations(sorted(significant_colors), 2):
                pair_counts[pair] += 1

            if len(significant_colors) >= 3:
                for triplet in combinations(sorted(significant_colors), 3):
                    triplet_counts[triplet] += 1

        sorted_pairs    = dict(sorted(pair_counts.items(),    key=lambda x: x[1], reverse=True))
        sorted_triplets = dict(sorted(triplet_counts.items(), key=lambda x: x[1], reverse=True))

        palettes = []
        for palette, names in sorted(palette_counts.items(), key=lambda x: len(x[1]), reverse=True):
            palettes.append({
                "colors":   list(palette),
                "count":    len(names),
                "examples": names[:5],
            })

        return {"pairs": sorted_pairs, "triplets": sorted_triplets, "palettes": palettes}

    # ------------------------------------------------------------------
    # Static charts (Matplotlib / PNG)
    # ------------------------------------------------------------------

    def create_color_frequency_chart_static(self, top_n: int = 100, filtered: bool = False) -> Path:
        """
        Save a horizontal bar chart of the top N color frequencies.

        Args:
            top_n    (int): Maximum number of colors to display.
            filtered (bool): Whether to use the filtered color data.

        Returns:
            Path: Path to the saved PNG file.
        """
        colors     = self.aggregate_colors(filtered=filtered)
        top_colors = dict(list(colors.items())[:top_n])

        fig, ax = plt.subplots(figsize=OUTPUT_SETTINGS["figure_size"])
        names      = list(top_colors.keys())
        values     = list(top_colors.values())
        hex_colors = [self._get_color_hex(c) for c in names]

        bars = ax.barh(range(len(names)), values, color=hex_colors, edgecolor="black", linewidth=0.5)
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(names)
        ax.invert_yaxis()
        ax.set_xlabel("Frequency (%)")

        suffix = " (Filtered)" if filtered else " (Raw)"
        ax.set_title(f"Top {top_n} Colors Across All Characters{suffix}", fontsize=14, fontweight="bold")

        for bar, val in zip(bars, values):
            ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height() / 2,
                    f"{val:.1f}%", va="center", fontsize=9)

        plt.tight_layout()
        filename   = "color_frequency_filtered.png" if filtered else "color_frequency_raw.png"
        output_path = self.output_dir / filename
        plt.savefig(output_path, dpi=OUTPUT_SETTINGS["chart_dpi"], bbox_inches="tight")
        plt.close()
        print(f"Saved: {output_path}")
        return output_path

    def create_shape_frequency_chart_static(self) -> Path:
        """
        Save a vertical bar chart of shape frequencies.

        Returns:
            Path: Path to the saved PNG file.
        """
        shapes = self.aggregate_shapes()
        fig, ax = plt.subplots(figsize=(10, 6))
        names  = list(shapes.keys())
        values = list(shapes.values())
        colors = plt.cm.viridis(np.linspace(0.2, 0.8, len(names)))

        bars = ax.bar(range(len(names)), values, color=colors, edgecolor="black", linewidth=0.5)
        ax.set_xticks(range(len(names)))
        ax.set_xticklabels(names, rotation=45, ha="right")
        ax.set_ylabel("Frequency (%)")
        ax.set_title("Shape Distribution Across All Characters", fontsize=14, fontweight="bold")

        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                    f"{val:.1f}%", ha="center", fontsize=9)

        plt.tight_layout()
        output_path = self.output_dir / "shape_frequency_static.png"
        plt.savefig(output_path, dpi=OUTPUT_SETTINGS["chart_dpi"], bbox_inches="tight")
        plt.close()
        print(f"Saved: {output_path}")
        return output_path

    def create_color_shape_heatmap_static(
        self, top_colors: int = 100, top_shapes: int = 12, filtered: bool = False
    ) -> Path:
        """
        Save a heatmap showing which colors appear inside which shape regions.

        Args:
            top_colors (int): Maximum number of colors on the x-axis.
            top_shapes (int): Maximum number of shapes on the y-axis.
            filtered   (bool): Whether to use filtered color data.

        Returns:
            Path: Path to the saved PNG file.
        """
        combos = self.aggregate_color_shape_combos(filtered=filtered)

        color_totals = defaultdict(float)
        for shape_colors in combos.values():
            for color, pct in shape_colors.items():
                color_totals[color] += pct

        top_color_names = sorted(color_totals.keys(), key=lambda x: color_totals[x], reverse=True)[:top_colors]
        shape_names     = list(combos.keys())[:top_shapes]

        matrix = np.zeros((len(shape_names), len(top_color_names)))
        for i, shape in enumerate(shape_names):
            for j, color in enumerate(top_color_names):
                matrix[i, j] = combos.get(shape, {}).get(color, 0)

        fig, ax = plt.subplots(figsize=(14, 8))
        im = ax.imshow(matrix, cmap="YlOrRd", aspect="auto")

        ax.set_xticks(range(len(top_color_names)))
        ax.set_xticklabels(top_color_names, rotation=45, ha="right")
        ax.set_yticks(range(len(shape_names)))
        ax.set_yticklabels(shape_names)

        for i in range(len(shape_names)):
            for j in range(len(top_color_names)):
                val = matrix[i, j]
                if val > 0:
                    color = "white" if val > matrix.max() * 0.5 else "black"
                    ax.text(j, i, f"{val:.1f}", ha="center", va="center", color=color, fontsize=8)

        plt.colorbar(im, label="Frequency (%)")
        suffix = " (Filtered)" if filtered else " (Raw)"
        ax.set_title(f"Color-Shape Combinations Heatmap{suffix}", fontsize=14, fontweight="bold")

        plt.tight_layout()
        filename    = "color_shape_heatmap_filtered.png" if filtered else "color_shape_heatmap_raw.png"
        output_path = self.output_dir / filename
        plt.savefig(output_path, dpi=OUTPUT_SETTINGS["chart_dpi"], bbox_inches="tight")
        plt.close()
        print(f"Saved: {output_path}")
        return output_path

    def create_color_category_chart_static(self, filtered: bool = False) -> Path:
        """
        Save a pie chart of the six color-category shares (warm / cool / etc.).

        Args:
            filtered (bool): Whether to use filtered color data.

        Returns:
            Path: Path to the saved PNG file.
        """
        colors = self.aggregate_colors(filtered=filtered)

        category_totals = defaultdict(float)
        for color, pct in colors.items():
            for category, category_colors in COLOR_CATEGORIES.items():
                if color in category_colors:
                    category_totals[category] += pct
                    break

        fig, ax = plt.subplots(figsize=(15, 8))
        labels = list(category_totals.keys())
        sizes  = list(category_totals.values())

        category_colors_map = {
            "warm":    "#FF6B6B",
            "cool":    "#4ECDC4",
            "neutral": "#95A5A6",
            "vibrant": "#FF00FF",
            "pastel":  "#FFB6C1",
            "dark":    "#2C3E50",
        }
        pie_colors = [category_colors_map.get(l, "#888888") for l in labels]

        wedges, texts, autotexts = ax.pie(
            sizes, labels=labels, autopct="%1.1f%%",
            colors=pie_colors, startangle=90,
            explode=[0.02] * len(labels),
        )

        suffix = " (Filtered)" if filtered else " (Raw)"
        ax.set_title(f"Color Category Distribution{suffix}", fontsize=14, fontweight="bold")

        plt.tight_layout()
        filename    = "color_categories_filtered.png" if filtered else "color_categories_raw.png"
        output_path = self.output_dir / filename
        plt.savefig(output_path, dpi=OUTPUT_SETTINGS["chart_dpi"], bbox_inches="tight")
        plt.close()
        print(f"Saved: {output_path}")
        return output_path

    def create_color_pairs_chart_static(self, top_n: int = 100, filtered: bool = False) -> Path:
        """
        Save a horizontal bar chart of the most common two-color co-occurrences.

        Each bar is colored with the first color of the pair; a small swatch of
        the second color is drawn at the right end of each bar.

        Args:
            top_n    (int): Maximum number of pairs to show.
            filtered (bool): Whether to use filtered color data.

        Returns:
            Path | None: Path to the saved PNG, or None if no pairs found.
        """
        combo_data = self.aggregate_color_combinations(filtered=filtered)
        pairs      = combo_data["pairs"]

        if not pairs:
            print("No color pairs found")
            return None

        top_pairs = dict(list(pairs.items())[:top_n])
        fig, ax   = plt.subplots(figsize=(14, 10))

        labels     = []
        values     = []
        bar_colors = []

        for (color1, color2), count in top_pairs.items():
            labels.append(f"{color1} + {color2}")
            values.append(count)
            bar_colors.append(self._get_color_hex(color1))

        y_pos = range(len(labels))
        bars  = ax.barh(y_pos, values, color=bar_colors, edgecolor="black", linewidth=0.5)

        # Draw a small swatch showing the second color at the bar's end
        for i, ((color1, color2), count) in enumerate(top_pairs.items()):
            rect = plt.Rectangle(
                (values[i] + 0.5, i - 0.3), max(values) * 0.03, 0.6,
                color=self._get_color_hex(color2), ec="black", linewidth=0.5,
            )
            ax.add_patch(rect)
            ax.text(values[i] + max(values) * 0.05, i, f"{count}", va="center", fontsize=9)

        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels)
        ax.invert_yaxis()
        ax.set_xlabel("Number of Characters")
        suffix = " (Filtered)" if filtered else " (Raw)"
        ax.set_title(f"Most Common Color Pairs{suffix}", fontsize=14, fontweight="bold")

        plt.tight_layout()
        filename    = "color_pairs_filtered.png" if filtered else "color_pairs_raw.png"
        output_path = self.output_dir / filename
        plt.savefig(output_path, dpi=OUTPUT_SETTINGS["chart_dpi"], bbox_inches="tight")
        plt.close()
        print(f"Saved: {output_path}")
        return output_path

    def create_color_triplets_chart_static(self, top_n: int = 100, filtered: bool = False) -> Path:
        """
        Save a horizontal bar chart of the most common three-color co-occurrences.

        Each bar is split into three equal segments, one per color in the triplet.

        Args:
            top_n    (int): Maximum number of triplets to show.
            filtered (bool): Whether to use filtered color data.

        Returns:
            Path | None: Path to the saved PNG, or None if no triplets found.
        """
        combo_data = self.aggregate_color_combinations(filtered=filtered)
        triplets   = combo_data["triplets"]

        if not triplets:
            print("No color triplets found")
            return None

        top_triplets = dict(list(triplets.items())[:top_n])
        fig, ax      = plt.subplots(figsize=(14, 10))

        labels = [f"{c1} + {c2} + {c3}" for (c1, c2, c3) in top_triplets.keys()]
        values = list(top_triplets.values())
        y_pos  = range(len(labels))

        bar_height = 0.6
        for i, ((color1, color2, color3), count) in enumerate(top_triplets.items()):
            seg = count / 3
            ax.barh(i, seg,     height=bar_height, left=0,      color=self._get_color_hex(color1), edgecolor="black", linewidth=0.5)
            ax.barh(i, seg,     height=bar_height, left=seg,    color=self._get_color_hex(color2), edgecolor="black", linewidth=0.5)
            ax.barh(i, seg,     height=bar_height, left=seg * 2, color=self._get_color_hex(color3), edgecolor="black", linewidth=0.5)
            ax.text(count + 0.5, i, f"{count}", va="center", fontsize=9)

        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels)
        ax.invert_yaxis()
        ax.set_xlabel("Number of Characters")
        suffix = " (Filtered)" if filtered else " (Raw)"
        ax.set_title(f"Most Common Color Triplets{suffix}", fontsize=14, fontweight="bold")

        plt.tight_layout()
        filename    = "color_triplets_filtered.png" if filtered else "color_triplets_raw.png"
        output_path = self.output_dir / filename
        plt.savefig(output_path, dpi=OUTPUT_SETTINGS["chart_dpi"], bbox_inches="tight")
        plt.close()
        print(f"Saved: {output_path}")
        return output_path

    # ------------------------------------------------------------------
    # Interactive charts (Plotly / HTML)
    # ------------------------------------------------------------------

    def create_color_frequency_chart_interactive(self, top_n: int = 100, filtered: bool = False) -> Path:
        """
        Save an interactive horizontal bar chart of color frequencies.

        Args:
            top_n    (int): Maximum number of colors to display.
            filtered (bool): Whether to use filtered color data.

        Returns:
            Path: Path to the saved HTML file.
        """
        colors     = self.aggregate_colors(filtered=filtered)
        top_colors = dict(list(colors.items())[:top_n])

        names      = list(top_colors.keys())
        values     = list(top_colors.values())
        hex_colors = [self._get_color_hex(c) for c in names]

        fig = go.Figure(go.Bar(
            y=names, x=values, orientation="h",
            marker=dict(color=hex_colors, line=dict(color="black", width=1)),
            text=[f"{v:.1f}%" for v in values], textposition="outside",
            hovertemplate="<b>%{y}</b><br>Frequency: %{x:.2f}%<extra></extra>",
        ))

        suffix = " (Filtered)" if filtered else " (Raw)"
        fig.update_layout(
            title=dict(text=f"Top {top_n} Colors Across All Characters{suffix}", font=dict(size=18)),
            xaxis_title="Frequency (%)",
            yaxis=dict(autorange="reversed"),
            height=max(600, top_n * 25),
            template="plotly_white",
            hoverlabel=dict(bgcolor="white"),
        )

        filename    = "color_frequency_filtered.html" if filtered else "color_frequency_raw.html"
        output_path = self.output_dir / filename
        fig.write_html(str(output_path))
        print(f"Saved: {output_path}")
        return output_path

    def create_shape_frequency_chart_interactive(self) -> Path:
        """
        Save an interactive vertical bar chart of shape frequencies.

        Returns:
            Path: Path to the saved HTML file.
        """
        shapes = self.aggregate_shapes()
        names  = list(shapes.keys())
        values = list(shapes.values())

        fig = go.Figure(go.Bar(
            x=names, y=values,
            marker=dict(color=values, colorscale="Viridis", line=dict(color="black", width=1)),
            text=[f"{v:.1f}%" for v in values], textposition="outside",
            hovertemplate="<b>%{x}</b><br>Frequency: %{y:.2f}%<extra></extra>",
        ))

        fig.update_layout(
            title=dict(text="Shape Distribution Across All Characters", font=dict(size=18)),
            yaxis_title="Frequency (%)",
            height=500,
            template="plotly_white",
        )

        output_path = self.output_dir / "shape_frequency_interactive.html"
        fig.write_html(str(output_path))
        print(f"Saved: {output_path}")
        return output_path

    def create_color_shape_heatmap_interactive(
        self, top_colors: int = 100, top_shapes: int = 12, filtered: bool = False
    ) -> Path:
        """
        Save an interactive heatmap of color-shape combination frequencies.

        Args:
            top_colors (int): Maximum colors on the x-axis.
            top_shapes (int): Maximum shapes on the y-axis.
            filtered   (bool): Whether to use filtered color data.

        Returns:
            Path: Path to the saved HTML file.
        """
        combos = self.aggregate_color_shape_combos(filtered=filtered)

        color_totals = defaultdict(float)
        for shape_colors in combos.values():
            for color, pct in shape_colors.items():
                color_totals[color] += pct

        top_color_names = sorted(color_totals.keys(), key=lambda x: color_totals[x], reverse=True)[:top_colors]
        shape_names     = list(combos.keys())[:top_shapes]

        matrix = [
            [combos.get(shape, {}).get(color, 0) for color in top_color_names]
            for shape in shape_names
        ]

        fig = go.Figure(go.Heatmap(
            z=matrix, x=top_color_names, y=shape_names,
            colorscale="YlOrRd",
            hovertemplate="<b>Shape:</b> %{y}<br><b>Color:</b> %{x}<br><b>Frequency:</b> %{z:.2f}%<extra></extra>",
        ))

        suffix = " (Filtered)" if filtered else " (Raw)"
        fig.update_layout(
            title=dict(text=f"Color-Shape Combinations Heatmap{suffix}", font=dict(size=18)),
            xaxis=dict(tickangle=45),
            height=600,
            template="plotly_white",
        )

        filename    = "color_shape_heatmap_filtered.html" if filtered else "color_shape_heatmap_raw.html"
        output_path = self.output_dir / filename
        fig.write_html(str(output_path))
        print(f"Saved: {output_path}")
        return output_path

    def create_sunburst_chart(self, filtered: bool = False) -> Path:
        """
        Save an interactive sunburst chart (shape → color hierarchy).

        The root node represents all characters; the first ring shows shape
        types; the second ring shows the top colors associated with each shape.

        Args:
            filtered (bool): Whether to use filtered color data.

        Returns:
            Path: Path to the saved HTML file.
        """
        combos = self.aggregate_color_shape_combos(filtered=filtered)

        ids         = ["All"]
        labels      = ["All Characters"]
        parents     = [""]
        values      = [100]
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
            ids=ids, labels=labels, parents=parents, values=values,
            marker=dict(colors=colors_list),
            branchvalues="total",
            hovertemplate="<b>%{label}</b><br>Value: %{value:.1f}%<extra></extra>",
        ))

        suffix = " (Filtered)" if filtered else " (Raw)"
        fig.update_layout(
            title=dict(text=f"Shape-Color Hierarchy{suffix}", font=dict(size=18)),
            height=700, template="plotly_white",
        )

        filename    = "shape_color_sunburst_filtered.html" if filtered else "shape_color_sunburst_raw.html"
        output_path = self.output_dir / filename
        fig.write_html(str(output_path))
        print(f"Saved: {output_path}")
        return output_path

    def create_treemap_chart(self, filtered: bool = False) -> Path:
        """
        Save an interactive treemap (color category → individual color).

        The treemap area encodes each color's share of the total palette
        and is rendered using the actual hex color of that palette entry.

        Args:
            filtered (bool): Whether to use filtered color data.

        Returns:
            Path: Path to the saved HTML file.
        """
        colors = self.aggregate_colors(filtered=filtered)

        ids        = ["All"]
        labels     = ["All Colors"]
        parents    = [""]
        values     = [100]
        hex_colors = ["#FFFFFF"]

        category_totals  = defaultdict(float)
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
            ids=ids, labels=labels, parents=parents, values=values,
            marker=dict(colors=hex_colors),
            branchvalues="total",
            hovertemplate="<b>%{label}</b><br>Frequency: %{value:.2f}%<extra></extra>",
        ))

        suffix = " (Filtered)" if filtered else " (Raw)"
        fig.update_layout(
            title=dict(text=f"Color Distribution Treemap{suffix}", font=dict(size=18)),
            height=700, template="plotly_white",
        )

        filename    = "color_treemap_filtered.html" if filtered else "color_treemap_raw.html"
        output_path = self.output_dir / filename
        fig.write_html(str(output_path))
        print(f"Saved: {output_path}")
        return output_path

    def create_comparison_chart(self) -> Path:
        """
        Save a side-by-side interactive chart comparing raw vs filtered color data.

        Returns:
            Path: Path to the saved HTML file.
        """
        raw_colors      = self.aggregate_colors(filtered=False)
        filtered_colors = self.aggregate_colors(filtered=True)

        raw_top      = dict(list(raw_colors.items())[:100])
        filtered_top = dict(list(filtered_colors.items())[:100])

        fig = make_subplots(rows=1, cols=2, subplot_titles=["Raw Data", "Filtered Data"])

        fig.add_trace(
            go.Bar(
                y=list(raw_top.keys()), x=list(raw_top.values()), orientation="h",
                marker=dict(color=[self._get_color_hex(c) for c in raw_top.keys()],
                            line=dict(color="black", width=1)),
                name="Raw",
                hovertemplate="<b>%{y}</b>: %{x:.1f}%<extra></extra>",
            ),
            row=1, col=1,
        )

        fig.add_trace(
            go.Bar(
                y=list(filtered_top.keys()), x=list(filtered_top.values()), orientation="h",
                marker=dict(color=[self._get_color_hex(c) for c in filtered_top.keys()],
                            line=dict(color="black", width=1)),
                name="Filtered",
                hovertemplate="<b>%{y}</b>: %{x:.1f}%<extra></extra>",
            ),
            row=1, col=2,
        )

        fig.update_yaxes(autorange="reversed", row=1, col=1)
        fig.update_yaxes(autorange="reversed", row=1, col=2)
        fig.update_layout(
            title=dict(text="Raw vs Filtered Color Distribution Comparison", font=dict(size=18)),
            height=600, showlegend=False, template="plotly_white",
        )

        output_path = self.output_dir / "raw_vs_filtered_comparison.html"
        fig.write_html(str(output_path))
        print(f"Saved: {output_path}")
        return output_path

    def create_color_combinations_interactive(self, top_n: int = 100, filtered: bool = False) -> Path:
        """
        Save a four-panel interactive dashboard for color-combination analysis.

        Panels:
          1. Top color pairs (horizontal bar chart).
          2. Top color triplets (horizontal bar chart).
          3. Color-pair network graph (circle layout with connecting edges).
          4. Common palette table (top 10 full palettes with example characters).

        Args:
            top_n    (int): Maximum pairs / triplets to display per panel.
            filtered (bool): Whether to use filtered color data.

        Returns:
            Path | None: Path to the saved HTML, or None if no pairs found.
        """
        combo_data = self.aggregate_color_combinations(filtered=filtered)
        pairs      = combo_data["pairs"]
        triplets   = combo_data["triplets"]
        palettes   = combo_data["palettes"]

        if not pairs:
            print("No color combinations found")
            return None

        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=["Top Color Pairs", "Top Color Triplets",
                            "Color Pair Network", "Common Palettes"],
            specs=[[{"type": "bar"}, {"type": "bar"}],
                   [{"type": "scatter"}, {"type": "table"}]],
            vertical_spacing=0.12, horizontal_spacing=0.1,
        )

        # Panel 1 — pairs
        top_pairs   = dict(list(pairs.items())[:top_n])
        pair_labels = [f"{c1} + {c2}" for (c1, c2) in top_pairs.keys()]
        pair_values = list(top_pairs.values())
        pair_colors = [self._get_color_hex(list(top_pairs.keys())[i][0]) for i in range(len(top_pairs))]

        fig.add_trace(
            go.Bar(y=pair_labels, x=pair_values, orientation="h",
                   marker=dict(color=pair_colors, line=dict(color="black", width=1)),
                   hovertemplate="<b>%{y}</b><br>Characters: %{x}<extra></extra>"),
            row=1, col=1,
        )

        # Panel 2 — triplets
        if triplets:
            top_triplets   = dict(list(triplets.items())[:15])
            triplet_labels = [f"{c1}+{c2}+{c3}" for (c1, c2, c3) in top_triplets.keys()]
            triplet_values = list(top_triplets.values())
            triplet_colors = [self._get_color_hex(list(top_triplets.keys())[i][0]) for i in range(len(top_triplets))]

            fig.add_trace(
                go.Bar(y=triplet_labels, x=triplet_values, orientation="h",
                       marker=dict(color=triplet_colors, line=dict(color="black", width=1)),
                       hovertemplate="<b>%{y}</b><br>Characters: %{x}<extra></extra>"),
                row=1, col=2,
            )

        # Panel 3 — network graph
        color_nodes = set()
        for (c1, c2) in list(pairs.keys())[:50]:
            color_nodes.update([c1, c2])

        color_list = list(color_nodes)
        n_colors   = len(color_list)
        angles     = np.linspace(0, 2 * np.pi, n_colors, endpoint=False)
        x_pos      = {c: np.cos(angles[i]) for i, c in enumerate(color_list)}
        y_pos      = {c: np.sin(angles[i]) for i, c in enumerate(color_list)}

        edge_x, edge_y = [], []
        for (c1, c2), _ in list(pairs.items())[:30]:
            if c1 in x_pos and c2 in x_pos:
                edge_x.extend([x_pos[c1], x_pos[c2], None])
                edge_y.extend([y_pos[c1], y_pos[c2], None])

        fig.add_trace(
            go.Scatter(x=edge_x, y=edge_y, mode="lines",
                       line=dict(width=0.5, color="#888"), hoverinfo="none"),
            row=2, col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=[x_pos[c] for c in color_list],
                y=[y_pos[c] for c in color_list],
                mode="markers+text",
                marker=dict(size=15, color=[self._get_color_hex(c) for c in color_list],
                            line=dict(width=1, color="black")),
                text=color_list, textposition="top center", textfont=dict(size=8),
                hovertemplate="<b>%{text}</b><extra></extra>",
            ),
            row=2, col=1,
        )

        # Panel 4 — palette table
        if palettes:
            top_palettes    = palettes[:10]
            palette_strs    = [", ".join(p["colors"]) for p in top_palettes]
            palette_counts  = [p["count"] for p in top_palettes]
            palette_examples = [", ".join(p["examples"][:3]) for p in top_palettes]

            fig.add_trace(
                go.Table(
                    header=dict(values=["Color Palette", "Count", "Examples"],
                                fill_color="paleturquoise", align="left", font=dict(size=11)),
                    cells=dict(values=[palette_strs, palette_counts, palette_examples],
                               fill_color="lavender", align="left", font=dict(size=10)),
                ),
                row=2, col=2,
            )

        fig.update_yaxes(autorange="reversed", row=1, col=1)
        fig.update_yaxes(autorange="reversed", row=1, col=2)
        fig.update_xaxes(showgrid=False, zeroline=False, showticklabels=False, row=2, col=1)
        fig.update_yaxes(showgrid=False, zeroline=False, showticklabels=False, row=2, col=1)

        suffix = " (Filtered)" if filtered else " (Raw)"
        fig.update_layout(
            title=dict(text=f"Color Combinations Analysis{suffix}", font=dict(size=18)),
            height=900, showlegend=False, template="plotly_white",
        )

        filename    = "color_combinations_filtered.html" if filtered else "color_combinations_raw.html"
        output_path = self.output_dir / filename
        fig.write_html(str(output_path))
        print(f"Saved: {output_path}")
        return output_path

    # ------------------------------------------------------------------
    # Batch generation
    # ------------------------------------------------------------------

    def generate_all_charts(self):
        """
        Generate every static and interactive chart in both raw and filtered modes.

        Output files follow this naming convention:
          - *_raw.png / *_raw.html       — unfiltered data
          - *_filtered.png / *_filtered.html — artifact-filtered data
          - raw_vs_filtered_comparison.html — side-by-side comparison
        """
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
        print("  RAW:       *_raw.png, *_raw.html")
        print("  FILTERED:  *_filtered.png, *_filtered.html")
        print("  COMPARISON: raw_vs_filtered_comparison.html")
        print("  COLOR COMBOS: color_pairs_*.png, color_triplets_*.png, color_combinations_*.html")
