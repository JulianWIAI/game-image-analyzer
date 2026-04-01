"""
SBS/TypeAnalyzer.py — Type / Attribute Visual Correlation Analyzer
===================================================================
Provides the TypeAnalyzer class, which correlates character types or
gameplay attributes (e.g. "fire", "hero", "villain") with the visual
properties extracted by ImageScanner (dominant colors, shape distributions).

Type data sources
-----------------
The analyzer is game-agnostic by design:
  - **Custom CSV / JSON** : Provide your own type file via ``load_type_data()``.
    Required columns: ``name``, ``type_primary``.
    Optional columns: ``type_secondary``, plus any numeric attributes such as
    ``attack``, ``defense``, ``base_happiness``, ``is_legendary``, etc.
  - **External API** (optional): ``fetch_api_types()`` queries a public
    character database API and builds the type dataframe automatically.

Custom CSV format example::

    name,type_primary,type_secondary,attribute
    Warrior,hero,fire,aggressive
    Mage,hero,ice,calm

Outputs
-------
  - ``type_color_heatmap.png``       — static heatmap of type × color matrix
  - ``type_shape_heatmap.png``       — static heatmap of type × shape matrix
  - ``attribute_correlations.png``   — four-panel attribute correlation chart
  - ``type_analysis_dashboard.html`` — interactive Plotly dashboard
  - ``type_analysis_report.txt``     — plain-text summary report

Dependencies: Pandas, NumPy, Matplotlib, Plotly, Requests, SBS.config
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

from .config import (
    COLOR_PALETTE, COLOR_CATEGORIES, SHAPE_DEFINITIONS,
    ATTRIBUTE_SHAPE_ASSOCIATIONS, ATTRIBUTE_COLOR_ASSOCIATIONS,
    OUTPUT_SETTINGS,
)


class TypeAnalyzer:
    """
    Analyzes correlations between character types / attributes and visual properties.

    The analyzer merges scan data (from ImageScanner) with type/attribute data
    (loaded from a file or fetched from an external API) and then generates heatmaps,
    dashboards, and a plain-text report.

    Attributes:
        scan_csv     (Path): Path to the scan-results CSV.
        output_dir   (Path): Directory where analysis outputs are saved.
        project_name (str): Display name used in chart titles.
        scan_df      (DataFrame): Scan results with JSON columns decoded.
        type_df      (DataFrame | None): Type / attribute data; None until loaded.
    """

    def __init__(
        self,
        scan_csv_path: str,
        type_data_path: str = None,
        output_dir: str = "output/analysis",
        project_name: str = None,
    ):
        """
        Initialize the analyzer and optionally load type data immediately.

        Args:
            scan_csv_path  (str): Path to the scan-results CSV from ImageScanner.
            type_data_path (str | None): Path to type data CSV or JSON.
                If None, type data must be loaded later via ``load_type_data()``
                or ``fetch_api_types()``.
            output_dir     (str): Directory for output files.
            project_name   (str | None): Display name for chart titles.
                Defaults to "Character".
        """
        self.scan_csv  = Path(scan_csv_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.scan_df = pd.read_csv(scan_csv_path)
        self._parse_json_columns()

        self.project_name = project_name if project_name else "Character"
        self.type_df = None

        if type_data_path:
            self.load_type_data(type_data_path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_json_columns(self):
        """Decode JSON-string columns in the scan dataframe to Python dicts."""
        for col in ["colors_json", "shapes_json", "color_shape_combos_json"]:
            if col in self.scan_df.columns:
                self.scan_df[col] = self.scan_df[col].apply(
                    lambda x: json.loads(x) if pd.notna(x) and isinstance(x, str) else x
                )

    def _get_color_hex(self, color_name: str) -> str:
        """
        Return the hex color code for a named palette color.

        Args:
            color_name (str): A key from COLOR_PALETTE.

        Returns:
            str: Hex string, or '#888888' as a neutral fallback.
        """
        if color_name in COLOR_PALETTE:
            return COLOR_PALETTE[color_name]["hex"]
        return "#888888"

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def load_type_data(self, path: str):
        """
        Load type / attribute data from a CSV or JSON file.

        The file must contain at minimum a ``name`` column (matching scan
        result names) and a ``type_primary`` column.  Additional columns such
        as ``type_secondary``, ``attack``, ``defense``, or ``is_legendary`` are
        used when available for deeper analysis.

        If ``type_primary`` is not found, the method searches for common
        alternative column names: ``type``, ``category``, ``class``, ``kind``.

        Args:
            path (str): File path to the type data CSV or JSON.
        """
        path = Path(path)

        if path.suffix == ".csv":
            self.type_df = pd.read_csv(path)
        elif path.suffix == ".json":
            with open(path) as f:
                data = json.load(f)
            self.type_df = pd.DataFrame(data)
        else:
            print(f"Unsupported file format: {path.suffix}")
            return

        if "name" not in self.type_df.columns:
            print("Warning: 'name' column not found in type data")

        if "type_primary" not in self.type_df.columns:
            print("Warning: 'type_primary' column not found. Looking for alternatives...")
            for alt in ("type", "category", "class", "kind"):
                if alt in self.type_df.columns:
                    self.type_df["type_primary"] = self.type_df[alt]
                    print(f"  Using '{alt}' column as type_primary")
                    break

        print(f"Loaded type data with columns: {list(self.type_df.columns)}")
        print(f"Total entries: {len(self.type_df)}")

    def fetch_api_types(self, character_names: list = None, save_path: str | None = None) -> pd.DataFrame:
        """
        Fetch type and stats data from an external character database API.

        Queries both the ``/pokemon`` and ``/pokemon-species`` endpoints of the
        public API for every character name in the scan results (or an explicit
        list) and stores type, egg group, official color, habitat, legendary
        status, base stats, happiness, and capture rate.

        For games without a supported external API use ``load_type_data()``
        with a custom CSV instead.

        Args:
            character_names (list[str] | None): Names to query.  Defaults to
                all names in ``scan_df``.
            save_path       (str | None): If given, saves the fetched dataframe
                to this CSV or JSON file.

        Returns:
            pd.DataFrame: The fetched type dataframe (also stored in
                ``self.type_df``).
        """
        if character_names is None:
            character_names = self.scan_df["name"].str.lower().tolist()

        print(f"Fetching API data for {len(character_names)} entries...")
        print("(For games without a supported API, use load_type_data() with your own CSV instead)")

        type_data = []

        for i, name in enumerate(character_names):
            clean_name = name.lower().strip().replace(" ", "-")

            try:
                species_resp = requests.get(
                    f"https://pokeapi.co/api/v2/pokemon-species/{clean_name}", timeout=10
                )
                pokemon_resp = requests.get(
                    f"https://pokeapi.co/api/v2/pokemon/{clean_name}", timeout=10
                )

                if species_resp.status_code == 200 and pokemon_resp.status_code == 200:
                    species_data = species_resp.json()
                    pokemon_data = pokemon_resp.json()

                    types      = [t["type"]["name"] for t in pokemon_data["types"]]
                    egg_groups = [eg["name"] for eg in species_data.get("egg_groups", [])]
                    color      = species_data.get("color", {}).get("name", "unknown")
                    shape      = (species_data.get("shape") or {}).get("name", "unknown")
                    habitat    = (species_data.get("habitat") or {}).get("name", "unknown")
                    stats      = {s["stat"]["name"]: s["base_stat"] for s in pokemon_data["stats"]}

                    type_data.append({
                        "name":            name,
                        "type_primary":    types[0] if types else "unknown",
                        "type_secondary":  types[1] if len(types) > 1 else None,
                        "types":           ",".join(types),
                        "egg_groups":      ",".join(egg_groups),
                        "official_color":  color,
                        "official_shape":  shape,
                        "habitat":         habitat,
                        "is_legendary":    species_data.get("is_legendary", False),
                        "is_mythical":     species_data.get("is_mythical", False),
                        "is_baby":         species_data.get("is_baby", False),
                        "base_happiness":  species_data.get("base_happiness", 0),
                        "capture_rate":    species_data.get("capture_rate", 0),
                        "hp":              stats.get("hp", 0),
                        "attack":          stats.get("attack", 0),
                        "defense":         stats.get("defense", 0),
                        "special_attack":  stats.get("special-attack", 0),
                        "special_defense": stats.get("special-defense", 0),
                        "speed":           stats.get("speed", 0),
                    })
                    print(f"  [{i + 1}/{len(character_names)}] {name}: {types}")
                else:
                    print(f"  [{i + 1}/{len(character_names)}] {name}: Not found")
                    type_data.append({"name": name, "type_primary": "unknown"})

                # Respectful rate-limiting to stay within API guidelines
                time.sleep(0.1)

            except Exception as e:
                print(f"  [{i + 1}/{len(character_names)}] {name}: Error — {e}")
                type_data.append({"name": name, "type_primary": "unknown"})

        self.type_df = pd.DataFrame(type_data)

        if save_path:
            save_path = Path(save_path)
            if save_path.suffix == ".csv":
                self.type_df.to_csv(save_path, index=False)
            else:
                self.type_df.to_json(save_path, orient="records", indent=2)
            print(f"\nType data saved to: {save_path}")

        return self.type_df

    # ------------------------------------------------------------------
    # Data merging
    # ------------------------------------------------------------------

    def merge_data(self) -> pd.DataFrame:
        """
        Merge the scan dataframe with the type dataframe on the character name.

        The merge is performed case-insensitively after stripping leading/
        trailing whitespace to handle minor naming inconsistencies.

        Returns:
            pd.DataFrame | None: Merged dataframe, or None if type data is not
                loaded or the merge produces an empty result.
        """
        if self.type_df is None:
            print("No type data loaded.")
            print("Options:")
            print("  1. Use load_type_data('your_types.csv') for custom type data")
            print("  2. Use fetch_api_types() for datasets with a supported external API")
            return None

        self.scan_df["name_lower"] = self.scan_df["name"].str.lower().str.strip()
        self.type_df["name_lower"] = self.type_df["name"].str.lower().str.strip()

        merged = pd.merge(
            self.scan_df, self.type_df,
            on="name_lower", how="inner", suffixes=("", "_type"),
        )
        print(f"Merged data: {len(merged)} entries "
              f"(scan: {len(self.scan_df)}, types: {len(self.type_df)})")
        return merged

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def analyze_type_colors(self, merged_df: pd.DataFrame = None) -> tuple:
        """
        Calculate the color distribution for each primary type.

        Args:
            merged_df (DataFrame | None): Pre-merged dataframe.  If None,
                ``merge_data()`` is called automatically.

        Returns:
            tuple[dict, dict]: A pair of:
                - normalized   : {type: {color: percentage}}
                - type_counts  : {type: character_count}
        """
        if merged_df is None:
            merged_df = self.merge_data()
        if merged_df is None or merged_df.empty:
            return {}, {}

        type_colors = defaultdict(lambda: defaultdict(float))
        type_counts = defaultdict(int)

        for _, row in merged_df.iterrows():
            primary_type = row.get("type_primary", "unknown")
            row_colors   = row.get("colors_json", {})
            if isinstance(row_colors, str):
                row_colors = json.loads(row_colors)

            type_counts[primary_type] += 1
            for color, pct in row_colors.items():
                type_colors[primary_type][color] += pct

        normalized = {}
        for ptype, clrs in type_colors.items():
            total = sum(clrs.values())
            if total > 0:
                normalized[ptype] = {c: round(p / total * 100, 2) for c, p in clrs.items()}

        return normalized, type_counts

    def analyze_type_shapes(self, merged_df: pd.DataFrame = None) -> tuple:
        """
        Calculate the shape distribution for each primary type.

        Args:
            merged_df (DataFrame | None): Pre-merged dataframe.  If None,
                ``merge_data()`` is called automatically.

        Returns:
            tuple[dict, dict]: A pair of:
                - normalized  : {type: {shape: percentage}}
                - type_counts : {type: character_count}
        """
        if merged_df is None:
            merged_df = self.merge_data()
        if merged_df is None or merged_df.empty:
            return {}, {}

        type_shapes = defaultdict(lambda: defaultdict(float))
        type_counts = defaultdict(int)

        for _, row in merged_df.iterrows():
            primary_type = row.get("type_primary", "unknown")
            row_shapes   = row.get("shapes_json", {})
            if isinstance(row_shapes, str):
                row_shapes = json.loads(row_shapes)

            type_counts[primary_type] += 1
            for shape, pct in row_shapes.items():
                type_shapes[primary_type][shape] += pct

        normalized = {}
        for ptype, shps in type_shapes.items():
            total = sum(shps.values())
            if total > 0:
                normalized[ptype] = {s: round(p / total * 100, 2) for s, p in shps.items()}

        return normalized, type_counts

    # ------------------------------------------------------------------
    # Static charts (Matplotlib / PNG)
    # ------------------------------------------------------------------

    def create_type_color_heatmap_static(
        self, merged_df: pd.DataFrame = None, top_colors: int = 15
    ) -> Path:
        """
        Save a static heatmap of color percentages per type.

        Rows = character types; columns = the top N most-prevalent colors
        across all types.  Cell values show the percentage of that color
        within that type's character set.

        Args:
            merged_df  (DataFrame | None): Pre-merged data.
            top_colors (int): Number of color columns to display.

        Returns:
            Path | None: Path to the saved PNG, or None if no data.
        """
        type_colors, type_counts = self.analyze_type_colors(merged_df)

        if not type_colors:
            print("No data to visualize")
            return None

        color_totals = defaultdict(float)
        for clrs in type_colors.values():
            for c, p in clrs.items():
                color_totals[c] += p

        top_color_names = sorted(color_totals.keys(), key=lambda x: color_totals[x], reverse=True)[:top_colors]
        type_names      = sorted(type_colors.keys())

        matrix = np.zeros((len(type_names), len(top_color_names)))
        for i, ptype in enumerate(type_names):
            for j, color in enumerate(top_color_names):
                matrix[i, j] = type_colors.get(ptype, {}).get(color, 0)

        fig, ax = plt.subplots(figsize=(14, 10))
        im = ax.imshow(matrix, cmap="YlOrRd", aspect="auto")

        ax.set_xticks(range(len(top_color_names)))
        ax.set_xticklabels(top_color_names, rotation=45, ha="right")
        ax.set_yticks(range(len(type_names)))
        ax.set_yticklabels([f"{t} ({type_counts[t]})" for t in type_names])

        for i in range(len(type_names)):
            for j in range(len(top_color_names)):
                val = matrix[i, j]
                if val > 0:
                    cell_color = "white" if val > matrix.max() * 0.5 else "black"
                    ax.text(j, i, f"{val:.1f}", ha="center", va="center",
                            color=cell_color, fontsize=7)

        plt.colorbar(im, label="Color Percentage (%)")
        ax.set_title(f"Color Distribution by {self.project_name} Type",
                     fontsize=14, fontweight="bold")
        ax.set_xlabel("Colors")
        ax.set_ylabel("Types (count)")

        plt.tight_layout()
        output_path = self.output_dir / "type_color_heatmap.png"
        plt.savefig(output_path, dpi=OUTPUT_SETTINGS["chart_dpi"], bbox_inches="tight")
        plt.close()

        print(f"Saved: {output_path}")
        return output_path

    def create_type_shape_heatmap_static(self, merged_df: pd.DataFrame = None) -> Path:
        """
        Save a static heatmap of shape percentages per type.

        Args:
            merged_df (DataFrame | None): Pre-merged data.

        Returns:
            Path | None: Path to the saved PNG, or None if no data.
        """
        type_shapes, type_counts = self.analyze_type_shapes(merged_df)

        if not type_shapes:
            print("No data to visualize")
            return None

        all_shapes  = set()
        for shps in type_shapes.values():
            all_shapes.update(shps.keys())

        shape_names = sorted(all_shapes)
        type_names  = sorted(type_shapes.keys())

        matrix = np.zeros((len(type_names), len(shape_names)))
        for i, ptype in enumerate(type_names):
            for j, shape in enumerate(shape_names):
                matrix[i, j] = type_shapes.get(ptype, {}).get(shape, 0)

        fig, ax = plt.subplots(figsize=(12, 10))
        im = ax.imshow(matrix, cmap="Blues", aspect="auto")

        ax.set_xticks(range(len(shape_names)))
        ax.set_xticklabels(shape_names, rotation=45, ha="right")
        ax.set_yticks(range(len(type_names)))
        ax.set_yticklabels([f"{t} ({type_counts[t]})" for t in type_names])

        for i in range(len(type_names)):
            for j in range(len(shape_names)):
                val = matrix[i, j]
                if val > 0:
                    cell_color = "white" if val > matrix.max() * 0.5 else "black"
                    ax.text(j, i, f"{val:.1f}", ha="center", va="center",
                            color=cell_color, fontsize=8)

        plt.colorbar(im, label="Shape Percentage (%)")
        ax.set_title(f"Shape Distribution by {self.project_name} Type",
                     fontsize=14, fontweight="bold")
        ax.set_xlabel("Shapes")
        ax.set_ylabel("Types (count)")

        plt.tight_layout()
        output_path = self.output_dir / "type_shape_heatmap.png"
        plt.savefig(output_path, dpi=OUTPUT_SETTINGS["chart_dpi"], bbox_inches="tight")
        plt.close()

        print(f"Saved: {output_path}")
        return output_path

    def create_attribute_correlation_chart(self, merged_df: pd.DataFrame = None) -> Path:
        """
        Save a four-panel chart correlating visual features with numeric attributes.

        The four panels adapt to the available columns in the merged dataframe:
          1. Color vs. ``base_happiness`` or placeholder.
          2. Shape vs. ``attack`` stat or placeholder.
          3. Special vs. Regular color distribution or placeholder.
          4. Type scatter: average ``attack`` vs. average ``defense`` or placeholder.

        Args:
            merged_df (DataFrame | None): Pre-merged data.

        Returns:
            Path | None: Path to the saved PNG, or None if merge fails.
        """
        if merged_df is None:
            merged_df = self.merge_data()
        if merged_df is None or merged_df.empty:
            return None

        fig, axes = plt.subplots(2, 2, figsize=(14, 12))

        has_happiness = "base_happiness" in merged_df.columns
        has_attack    = "attack"         in merged_df.columns
        has_legendary = "is_legendary"   in merged_df.columns
        has_defense   = "defense"        in merged_df.columns

        # ---- Panel 1: Color vs base_happiness ----
        ax1 = axes[0, 0]
        if has_happiness:
            happiness_colors = defaultdict(list)
            for _, row in merged_df.iterrows():
                happiness = row.get("base_happiness", 0)
                dom_color = row.get("dominant_color", "unknown")
                if happiness and dom_color != "unknown":
                    happiness_colors[dom_color].append(happiness)

            avg_happiness = {c: np.mean(h) for c, h in happiness_colors.items() if len(h) >= 2}
            if avg_happiness:
                sorted_colors = sorted(avg_happiness.items(), key=lambda x: x[1], reverse=True)[:15]
                colors_list, values = zip(*sorted_colors)
                ax1.barh(range(len(colors_list)), values,
                         color=[self._get_color_hex(c) for c in colors_list], edgecolor="black")
                ax1.set_yticks(range(len(colors_list)))
                ax1.set_yticklabels(colors_list)
                ax1.set_xlabel("Average Base Happiness")
                ax1.set_title("Color vs Base Happiness", fontweight="bold")
                ax1.invert_yaxis()
            else:
                ax1.text(0.5, 0.5, "Not enough data", ha="center", va="center", transform=ax1.transAxes)
                ax1.set_title("Color vs Base Happiness", fontweight="bold")
        else:
            ax1.text(0.5, 0.5, "No happiness data\n(add 'base_happiness' column to type CSV)",
                     ha="center", va="center", transform=ax1.transAxes)
            ax1.set_title("Color vs Attribute", fontweight="bold")

        # ---- Panel 2: Shape vs attack ----
        ax2 = axes[0, 1]
        if has_attack:
            attack_shapes = defaultdict(list)
            for _, row in merged_df.iterrows():
                attack    = row.get("attack", 0)
                dom_shape = row.get("dominant_shape", "unknown")
                if attack and dom_shape != "unknown":
                    attack_shapes[dom_shape].append(attack)

            avg_attack = {s: np.mean(a) for s, a in attack_shapes.items() if len(a) >= 2}
            if avg_attack:
                sorted_shapes = sorted(avg_attack.items(), key=lambda x: x[1], reverse=True)
                shapes, values = zip(*sorted_shapes)
                ax2.bar(range(len(shapes)), values,
                        color=plt.cm.Reds(np.linspace(0.3, 0.9, len(shapes))), edgecolor="black")
                ax2.set_xticks(range(len(shapes)))
                ax2.set_xticklabels(shapes, rotation=45, ha="right")
                ax2.set_ylabel("Average Attack Stat")
                ax2.set_title("Shape vs Attack Stat", fontweight="bold")
            else:
                ax2.text(0.5, 0.5, "Not enough data", ha="center", va="center", transform=ax2.transAxes)
                ax2.set_title("Shape vs Attack Stat", fontweight="bold")
        else:
            ax2.text(0.5, 0.5, "No attack data\n(Add 'attack' column to type CSV)",
                     ha="center", va="center", transform=ax2.transAxes)
            ax2.set_title("Shape vs Attribute", fontweight="bold")

        # ---- Panel 3: Legendary vs Regular color distribution ----
        ax3 = axes[1, 0]
        if has_legendary:
            legendary_colors = defaultdict(int)
            regular_colors   = defaultdict(int)
            for _, row in merged_df.iterrows():
                is_leg    = row.get("is_legendary", False) or row.get("is_mythical", False)
                dom_color = row.get("dominant_color", "unknown")
                if dom_color != "unknown":
                    if is_leg:
                        legendary_colors[dom_color] += 1
                    else:
                        regular_colors[dom_color] += 1

            if legendary_colors:
                all_cols  = set(legendary_colors.keys()) | set(regular_colors.keys())
                top_cols  = sorted(all_cols,
                                   key=lambda x: legendary_colors.get(x, 0) + regular_colors.get(x, 0),
                                   reverse=True)[:10]
                x     = np.arange(len(top_cols))
                width = 0.35

                ax3.bar(x - width / 2, [regular_colors.get(c, 0) for c in top_cols],
                        width, label="Regular", color="steelblue")
                ax3.bar(x + width / 2, [legendary_colors.get(c, 0) for c in top_cols],
                        width, label="Legendary/Mythical", color="gold")
                ax3.set_xticks(x)
                ax3.set_xticklabels(top_cols, rotation=45, ha="right")
                ax3.set_ylabel("Count")
                ax3.set_title("Legendary vs Regular: Color Distribution", fontweight="bold")
                ax3.legend()
            else:
                ax3.text(0.5, 0.5, "No legendary data", ha="center", va="center", transform=ax3.transAxes)
                ax3.set_title("Category Comparison", fontweight="bold")
        else:
            ax3.text(0.5, 0.5, "No category data\n(Add 'is_legendary' or similar)",
                     ha="center", va="center", transform=ax3.transAxes)
            ax3.set_title("Category Comparison", fontweight="bold")

        # ---- Panel 4: Type scatter — attack vs defense ----
        ax4 = axes[1, 1]
        if has_attack and has_defense:
            type_stats = defaultdict(lambda: {"attack": [], "defense": []})
            for _, row in merged_df.iterrows():
                ptype   = row.get("type_primary", "unknown")
                attack  = row.get("attack", 0)
                defense = row.get("defense", 0)
                if ptype != "unknown" and attack and defense:
                    type_stats[ptype]["attack"].append(attack)
                    type_stats[ptype]["defense"].append(defense)

            if type_stats:
                types       = list(type_stats.keys())
                avg_attacks  = [np.mean(type_stats[t]["attack"])  for t in types]
                avg_defenses = [np.mean(type_stats[t]["defense"]) for t in types]

                ax4.scatter(avg_attacks, avg_defenses, s=100, alpha=0.7,
                            c="teal", edgecolors="black")
                for i, t in enumerate(types):
                    ax4.annotate(t, (avg_attacks[i], avg_defenses[i]), fontsize=8, ha="center")
                ax4.set_xlabel("Average Attack")
                ax4.set_ylabel("Average Defense")
                ax4.set_title("Type: Attack vs Defense", fontweight="bold")
            else:
                ax4.text(0.5, 0.5, "Not enough data", ha="center", va="center", transform=ax4.transAxes)
                ax4.set_title("Type: Attack vs Defense", fontweight="bold")
        else:
            ax4.text(0.5, 0.5, "No attack/defense data\n(Add to type CSV)",
                     ha="center", va="center", transform=ax4.transAxes)
            ax4.set_title("Type Stats Comparison", fontweight="bold")

        plt.tight_layout()
        output_path = self.output_dir / "attribute_correlations.png"
        plt.savefig(output_path, dpi=OUTPUT_SETTINGS["chart_dpi"], bbox_inches="tight")
        plt.close()

        print(f"Saved: {output_path}")
        return output_path

    # ------------------------------------------------------------------
    # Interactive dashboard (Plotly / HTML)
    # ------------------------------------------------------------------

    def create_type_analysis_interactive(self, merged_df: pd.DataFrame = None) -> Path:
        """
        Save a four-panel interactive Plotly dashboard for type analysis.

        Panels:
          1. Color distribution heatmap (type × color).
          2. Shape distribution heatmap (type × shape).
          3. Character count per type (bar chart).
          4. Dominant color percentage per type (bar chart, colored with actual palette).

        Args:
            merged_df (DataFrame | None): Pre-merged data.

        Returns:
            Path | None: Path to the saved HTML, or None if merge fails.
        """
        if merged_df is None:
            merged_df = self.merge_data()
        if merged_df is None or merged_df.empty:
            return None

        type_colors, color_counts = self.analyze_type_colors(merged_df)
        type_shapes, shape_counts = self.analyze_type_shapes(merged_df)

        # Determine top 15 colors by total prevalence across all types
        color_totals = defaultdict(float)
        for clrs in type_colors.values():
            for c, p in clrs.items():
                color_totals[c] += p
        top_color_names = sorted(color_totals.keys(), key=lambda x: color_totals[x], reverse=True)[:15]

        all_shapes  = set()
        for shps in type_shapes.values():
            all_shapes.update(shps.keys())
        shape_names = sorted(all_shapes)
        type_names  = sorted(type_colors.keys())

        color_matrix = [[type_colors.get(t, {}).get(c, 0) for c in top_color_names] for t in type_names]
        shape_matrix = [[type_shapes.get(t, {}).get(s, 0) for s in shape_names]     for t in type_names]

        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=["Color Distribution by Type", "Shape Distribution by Type",
                            "Type Count Overview",         "Top Colors per Type"],
            specs=[[{"type": "heatmap"}, {"type": "heatmap"}],
                   [{"type": "bar"},     {"type": "bar"}]],
            vertical_spacing=0.12, horizontal_spacing=0.1,
        )

        fig.add_trace(
            go.Heatmap(
                z=color_matrix, x=top_color_names,
                y=[f"{t} ({color_counts[t]})" for t in type_names],
                colorscale="YlOrRd",
                hovertemplate="Type: %{y}<br>Color: %{x}<br>Percentage: %{z:.2f}%<extra></extra>",
            ),
            row=1, col=1,
        )
        fig.add_trace(
            go.Heatmap(
                z=shape_matrix, x=shape_names,
                y=[f"{t} ({shape_counts[t]})" for t in type_names],
                colorscale="Blues",
                hovertemplate="Type: %{y}<br>Shape: %{x}<br>Percentage: %{z:.2f}%<extra></extra>",
            ),
            row=1, col=2,
        )
        fig.add_trace(
            go.Bar(
                x=type_names, y=[color_counts[t] for t in type_names],
                marker_color="rgb(55, 83, 109)",
                hovertemplate="Type: %{x}<br>Count: %{y}<extra></extra>",
            ),
            row=2, col=1,
        )

        # Bar chart showing the percentage share of each type's dominant color,
        # using the actual palette hex so the bar itself is that color.
        top_colors_per_type = []
        bar_colors = []
        for ptype in type_names:
            clrs = type_colors.get(ptype, {})
            if clrs:
                top_color = max(clrs.items(), key=lambda x: x[1])
                top_colors_per_type.append(top_color[1])
                bar_colors.append(self._get_color_hex(top_color[0]))
            else:
                top_colors_per_type.append(0)
                bar_colors.append("#888888")

        fig.add_trace(
            go.Bar(
                x=type_names, y=top_colors_per_type,
                marker_color=bar_colors,
                hovertemplate="Type: %{x}<br>Top Color %: %{y:.1f}%<extra></extra>",
            ),
            row=2, col=2,
        )

        fig.update_layout(
            title=dict(text=f"{self.project_name} Type Visual Analysis Dashboard",
                       font=dict(size=20)),
            height=900, showlegend=False, template="plotly_white",
        )
        for r, c in [(1, 1), (1, 2), (2, 1), (2, 2)]:
            fig.update_xaxes(tickangle=45, row=r, col=c)

        output_path = self.output_dir / "type_analysis_dashboard.html"
        fig.write_html(str(output_path))
        print(f"Saved: {output_path}")
        return output_path

    # ------------------------------------------------------------------
    # Text report
    # ------------------------------------------------------------------

    def generate_type_report(self, merged_df: pd.DataFrame = None) -> Path:
        """
        Generate and save a plain-text type analysis report.

        The report lists each type's top colors and shapes, then checks which
        attribute-color associations from config are met.

        Args:
            merged_df (DataFrame | None): Pre-merged data.

        Returns:
            Path | None: Path to the saved .txt file, or None if merge fails.
        """
        if merged_df is None:
            merged_df = self.merge_data()
        if merged_df is None or merged_df.empty:
            return None

        type_colors, color_counts = self.analyze_type_colors(merged_df)
        type_shapes, shape_counts = self.analyze_type_shapes(merged_df)

        lines = [
            "=" * 60,
            f"{self.project_name.upper()} TYPE VISUAL ANALYSIS REPORT",
            "=" * 60,
            f"\nTotal {self.project_name}s Analyzed: {len(merged_df)}",
            f"Total Types: {len(type_colors)}",
            "\n" + "-" * 40,
            "TYPE BREAKDOWN",
            "-" * 40,
        ]

        for ptype in sorted(type_colors.keys()):
            count      = color_counts.get(ptype, 0)
            clrs       = type_colors.get(ptype, {})
            shps       = type_shapes.get(ptype, {})
            top_colors = sorted(clrs.items(), key=lambda x: x[1], reverse=True)[:5]
            top_shapes = sorted(shps.items(), key=lambda x: x[1], reverse=True)[:3]

            lines.append(f"\n{ptype.upper()} ({count} {self.project_name}s)")
            lines.append(f"  Top Colors: {', '.join(f'{c}({p:.1f}%)' for c, p in top_colors)}")
            lines.append(f"  Top Shapes: {', '.join(f'{s}({p:.1f}%)' for s, p in top_shapes)}")

        lines += ["\n" + "-" * 40, "VISUAL PATTERNS", "-" * 40]

        for attr, expected_colors in ATTRIBUTE_COLOR_ASSOCIATIONS.items():
            matching_types = []
            for ptype, clrs in type_colors.items():
                top_type_colors = set(list(clrs.keys())[:5])
                if len(set(expected_colors) & top_type_colors) >= 2:
                    matching_types.append(ptype)
            if matching_types:
                lines.append(f"\n'{attr.upper()}' visual pattern matches: {', '.join(matching_types)}")

        report_text = "\n".join(lines)
        output_path = self.output_dir / "type_analysis_report.txt"
        with open(output_path, "w") as f:
            f.write(report_text)

        print(f"Saved: {output_path}")
        print("\n" + report_text)
        return output_path

    # ------------------------------------------------------------------
    # Batch generation
    # ------------------------------------------------------------------

    def generate_all_analysis(self):
        """
        Run the full type analysis pipeline and save all outputs.

        Calls (in order):
          1. ``merge_data()``
          2. ``create_type_color_heatmap_static()``
          3. ``create_type_shape_heatmap_static()``
          4. ``create_attribute_correlation_chart()``
          5. ``create_type_analysis_interactive()``
          6. ``generate_type_report()``
        """
        print(f"\n=== Starting {self.project_name} Type Analysis ===\n")

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
