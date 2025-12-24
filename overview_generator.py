"""
Character Overview Generator
Creates visual overview reports for individual characters/monsters,
combining the original image with color and shape analysis diagrams.
"""

import cv2
import pandas as pd
import numpy as np
import json
import os
from pathlib import Path
from io import BytesIO
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.patches import Rectangle, FancyBboxPatch
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from PIL import Image
import base64
from config import COLOR_PALETTE, SHAPE_DEFINITIONS, OUTPUT_SETTINGS


class OverviewGenerator:
    def __init__(self, csv_path, output_dir="output/overviews"):
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
    
    def _load_image(self, image_path):
        """Load an image and convert to RGB."""
        img = cv2.imread(str(image_path))
        if img is not None:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        return img
    
    def generate_overview_static(self, row_index=None, name=None):
        """Generate a static PNG overview for a single character."""
        if row_index is not None:
            row = self.df.iloc[row_index]
        elif name is not None:
            matches = self.df[self.df["name"] == name]
            if matches.empty:
                print(f"Character '{name}' not found")
                return None
            row = matches.iloc[0]
        else:
            print("Please provide either row_index or name")
            return None
        
        char_name = row["name"]
        image_path = row["image_path"]
        colors = row["colors_json"]
        shapes = row["shapes_json"]
        combos = row.get("color_shape_combos_json", {})
        
        img = self._load_image(image_path)
        
        fig = plt.figure(figsize=(16, 10))
        gs = gridspec.GridSpec(2, 3, figure=fig, height_ratios=[1.2, 1], width_ratios=[1.2, 1, 1])
        
        ax_image = fig.add_subplot(gs[0, 0])
        if img is not None:
            ax_image.imshow(img)
        ax_image.set_title(char_name, fontsize=16, fontweight='bold', pad=10)
        ax_image.axis('off')
        
        ax_color_bar = fig.add_subplot(gs[0, 1])
        if colors:
            top_colors = dict(list(colors.items())[:10])
            color_names = list(top_colors.keys())
            color_values = list(top_colors.values())
            hex_colors = [self._get_color_hex(c) for c in color_names]
            
            bars = ax_color_bar.barh(range(len(color_names)), color_values, 
                                      color=hex_colors, edgecolor='black', linewidth=0.5)
            ax_color_bar.set_yticks(range(len(color_names)))
            ax_color_bar.set_yticklabels(color_names, fontsize=9)
            ax_color_bar.invert_yaxis()
            ax_color_bar.set_xlabel("Percentage (%)", fontsize=10)
            ax_color_bar.set_title("Color Distribution", fontsize=12, fontweight='bold')
            
            for bar, val in zip(bars, color_values):
                ax_color_bar.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height()/2,
                                 f'{val:.1f}%', va='center', fontsize=8)
        
        ax_color_pie = fig.add_subplot(gs[0, 2])
        if colors:
            top_colors = dict(list(colors.items())[:8])
            other_pct = 100 - sum(top_colors.values())
            if other_pct > 1:
                top_colors["other"] = other_pct
            
            pie_colors = [self._get_color_hex(c) if c != "other" else "#CCCCCC" 
                         for c in top_colors.keys()]
            
            wedges, texts, autotexts = ax_color_pie.pie(
                list(top_colors.values()), 
                labels=list(top_colors.keys()),
                autopct='%1.1f%%',
                colors=pie_colors,
                startangle=90,
                pctdistance=0.75,
                textprops={'fontsize': 8}
            )
            ax_color_pie.set_title("Color Breakdown", fontsize=12, fontweight='bold')
        
        ax_shape_bar = fig.add_subplot(gs[1, 0])
        if shapes:
            shape_names = list(shapes.keys())
            shape_values = list(shapes.values())
            
            colors_map = plt.cm.viridis(np.linspace(0.2, 0.8, len(shape_names)))
            bars = ax_shape_bar.bar(range(len(shape_names)), shape_values, 
                                    color=colors_map, edgecolor='black', linewidth=0.5)
            ax_shape_bar.set_xticks(range(len(shape_names)))
            ax_shape_bar.set_xticklabels(shape_names, rotation=45, ha='right', fontsize=9)
            ax_shape_bar.set_ylabel("Percentage (%)", fontsize=10)
            ax_shape_bar.set_title("Shape Distribution", fontsize=12, fontweight='bold')
            
            for bar, val in zip(bars, shape_values):
                ax_shape_bar.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                                 f'{val:.1f}%', ha='center', fontsize=8)
        
        ax_info = fig.add_subplot(gs[1, 1:])
        ax_info.axis('off')
        
        info_text = f"""
Character Analysis Summary
{'='*40}

Name: {char_name}
Dominant Color: {row['dominant_color']}
Dominant Shape: {row['dominant_shape']}
Total Colors Detected: {row['color_count']}
Total Shapes Detected: {row['shape_count']}

Image Dimensions: {row['image_width']} x {row['image_height']} px
"""
        
        if combos:
            info_text += f"\nColor-Shape Associations:\n"
            for shape, shape_colors in list(combos.items())[:5]:
                top_color = max(shape_colors.items(), key=lambda x: x[1])[0] if shape_colors else "N/A"
                info_text += f"  • {shape.capitalize()}: primarily {top_color}\n"
        
        ax_info.text(0.05, 0.95, info_text, transform=ax_info.transAxes,
                    fontsize=10, verticalalignment='top', fontfamily='monospace',
                    bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        
        plt.tight_layout()
        
        output_path = self.output_dir / f"{char_name}_overview.png"
        plt.savefig(output_path, dpi=OUTPUT_SETTINGS["chart_dpi"], bbox_inches='tight',
                   facecolor='white', edgecolor='none')
        plt.close()
        
        print(f"Saved: {output_path}")
        return output_path
    
    def generate_overview_interactive(self, row_index=None, name=None):
        """Generate an interactive HTML overview for a single character."""
        if row_index is not None:
            row = self.df.iloc[row_index]
        elif name is not None:
            matches = self.df[self.df["name"] == name]
            if matches.empty:
                print(f"Character '{name}' not found")
                return None
            row = matches.iloc[0]
        else:
            print("Please provide either row_index or name")
            return None
        
        char_name = row["name"]
        image_path = row["image_path"]
        colors = row["colors_json"]
        shapes = row["shapes_json"]
        combos = row.get("color_shape_combos_json", {})
        
        fig = make_subplots(
            rows=2, cols=3,
            specs=[
                [{"type": "xy", "rowspan": 2}, {"type": "bar"}, {"type": "pie"}],
                [None, {"type": "bar"}, {"type": "table"}]
            ],
            subplot_titles=["", "Color Distribution", "Color Breakdown", 
                           "Shape Distribution", "Analysis Summary"],
            vertical_spacing=0.12,
            horizontal_spacing=0.08
        )
        
        if colors:
            top_colors = dict(list(colors.items())[:10])
            hex_colors = [self._get_color_hex(c) for c in top_colors.keys()]
            
            fig.add_trace(
                go.Bar(
                    y=list(top_colors.keys()),
                    x=list(top_colors.values()),
                    orientation='h',
                    marker=dict(color=hex_colors, line=dict(color='black', width=1)),
                    text=[f'{v:.1f}%' for v in top_colors.values()],
                    textposition='outside',
                    hovertemplate='<b>%{y}</b>: %{x:.2f}%<extra></extra>'
                ),
                row=1, col=2
            )
        
        if colors:
            top_colors = dict(list(colors.items())[:8])
            other_pct = 100 - sum(top_colors.values())
            if other_pct > 1:
                top_colors["other"] = other_pct
            
            pie_colors = [self._get_color_hex(c) if c != "other" else "#CCCCCC" 
                         for c in top_colors.keys()]
            
            fig.add_trace(
                go.Pie(
                    labels=list(top_colors.keys()),
                    values=list(top_colors.values()),
                    marker=dict(colors=pie_colors, line=dict(color='black', width=1)),
                    textinfo='label+percent',
                    hovertemplate='<b>%{label}</b>: %{value:.2f}%<extra></extra>'
                ),
                row=1, col=3
            )
        
        if shapes:
            shape_colors = [f'rgb({int(c[0]*255)},{int(c[1]*255)},{int(c[2]*255)})' 
                           for c in plt.cm.viridis(np.linspace(0.2, 0.8, len(shapes)))]
            
            fig.add_trace(
                go.Bar(
                    x=list(shapes.keys()),
                    y=list(shapes.values()),
                    marker=dict(color=shape_colors, line=dict(color='black', width=1)),
                    text=[f'{v:.1f}%' for v in shapes.values()],
                    textposition='outside',
                    hovertemplate='<b>%{x}</b>: %{y:.2f}%<extra></extra>'
                ),
                row=2, col=2
            )
        
        summary_data = [
            ["Name", char_name],
            ["Dominant Color", row['dominant_color']],
            ["Dominant Shape", row['dominant_shape']],
            ["Colors Detected", str(row['color_count'])],
            ["Shapes Detected", str(row['shape_count'])],
            ["Dimensions", f"{row['image_width']}x{row['image_height']}"]
        ]
        
        fig.add_trace(
            go.Table(
                header=dict(
                    values=["Property", "Value"],
                    fill_color='paleturquoise',
                    align='left',
                    font=dict(size=12)
                ),
                cells=dict(
                    values=[[r[0] for r in summary_data], [r[1] for r in summary_data]],
                    fill_color='lavender',
                    align='left',
                    font=dict(size=11)
                )
            ),
            row=2, col=3
        )
        
        fig.update_layout(
            title=dict(
                text=f"<b>{char_name}</b> - Character Analysis",
                font=dict(size=20),
                x=0.5
            ),
            height=800,
            showlegend=False,
            template="plotly_white"
        )
        
        fig.update_yaxes(autorange="reversed", row=1, col=2)
        
        output_path = self.output_dir / f"{char_name}_overview.html"
        fig.write_html(str(output_path))
        
        print(f"Saved: {output_path}")
        return output_path
    
    def generate_all_overviews(self, static=True, interactive=True):
        """Generate overviews for all characters in the dataset."""
        print(f"\nGenerating overviews for {len(self.df)} characters...")
        
        for idx in range(len(self.df)):
            char_name = self.df.iloc[idx]["name"]
            print(f"\nProcessing {idx+1}/{len(self.df)}: {char_name}")
            
            if static:
                self.generate_overview_static(row_index=idx)
            if interactive:
                self.generate_overview_interactive(row_index=idx)
        
        print(f"\nAll overviews saved to: {self.output_dir}")
    
    def generate_comparison_overview(self, names=None, indices=None):
        """Generate a comparison overview for multiple characters."""
        if names:
            rows = [self.df[self.df["name"] == n].iloc[0] for n in names if n in self.df["name"].values]
        elif indices:
            rows = [self.df.iloc[i] for i in indices if i < len(self.df)]
        else:
            rows = []
        
        if len(rows) < 2:
            print("Need at least 2 characters for comparison")
            return None
        
        n_chars = len(rows)
        fig = plt.figure(figsize=(6 * n_chars, 10))
        gs = gridspec.GridSpec(3, n_chars, figure=fig, height_ratios=[1, 0.8, 0.8])
        
        for i, row in enumerate(rows):
            ax_img = fig.add_subplot(gs[0, i])
            img = self._load_image(row["image_path"])
            if img is not None:
                ax_img.imshow(img)
            ax_img.set_title(row["name"], fontsize=14, fontweight='bold')
            ax_img.axis('off')
            
            ax_color = fig.add_subplot(gs[1, i])
            colors = row["colors_json"]
            if colors:
                top_colors = dict(list(colors.items())[:6])
                hex_colors = [self._get_color_hex(c) for c in top_colors.keys()]
                ax_color.barh(range(len(top_colors)), list(top_colors.values()),
                             color=hex_colors, edgecolor='black', linewidth=0.5)
                ax_color.set_yticks(range(len(top_colors)))
                ax_color.set_yticklabels(list(top_colors.keys()), fontsize=8)
                ax_color.invert_yaxis()
                ax_color.set_xlabel("%" , fontsize=9)
                ax_color.set_title("Colors", fontsize=10)
            
            ax_shape = fig.add_subplot(gs[2, i])
            shapes = row["shapes_json"]
            if shapes:
                shape_colors = plt.cm.viridis(np.linspace(0.2, 0.8, len(shapes)))
                ax_shape.bar(range(len(shapes)), list(shapes.values()),
                            color=shape_colors, edgecolor='black', linewidth=0.5)
                ax_shape.set_xticks(range(len(shapes)))
                ax_shape.set_xticklabels(list(shapes.keys()), rotation=45, ha='right', fontsize=8)
                ax_shape.set_ylabel("%", fontsize=9)
                ax_shape.set_title("Shapes", fontsize=10)
        
        plt.tight_layout()
        
        name_str = "_vs_".join([r["name"] for r in rows[:4]])
        output_path = self.output_dir / f"comparison_{name_str}.png"
        plt.savefig(output_path, dpi=OUTPUT_SETTINGS["chart_dpi"], bbox_inches='tight')
        plt.close()
        
        print(f"Saved: {output_path}")
        return output_path


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate character overview reports")
    parser.add_argument("csv", help="Path to scan results CSV")
    parser.add_argument("-o", "--output", default="output/overviews", help="Output directory")
    parser.add_argument("-n", "--name", help="Generate overview for specific character")
    parser.add_argument("-i", "--index", type=int, help="Generate overview for character at index")
    parser.add_argument("--all", action="store_true", help="Generate overviews for all characters")
    parser.add_argument("--static-only", action="store_true", help="Generate only static PNG")
    parser.add_argument("--interactive-only", action="store_true", help="Generate only interactive HTML")
    parser.add_argument("--compare", nargs="+", help="Compare multiple characters by name")
    
    args = parser.parse_args()
    
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


if __name__ == "__main__":
    main()
