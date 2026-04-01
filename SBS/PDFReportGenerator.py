"""
SBS/PDFReportGenerator.py — PDF Summary Report Generator
=========================================================
Provides the PDFReportGenerator class, which compiles a single-page professional
PDF summary of all scan results.  The report is built with ReportLab and
contains the following sections:

  1. Title & generation timestamp
  2. Overview statistics table (total images, unique colors/shapes, dominants)
  3. Top 10 colors (filtered) with color-swatch column
  4. Shape distribution table
  5. Color-category breakdown table
  6. Most common color-pair combinations
  7. Key insights (auto-generated natural-language bullets)
  8. Footer

Works with any game or image collection — the project name is either provided
explicitly or inferred from the CSV directory path.

Outline colors (black, onyx, charcoal, slate) are filtered out of the "top
colors" section when they fall below a percentage threshold, mirroring the
filtered-mode behavior of ChartGenerator.

Dependencies: Pandas, NumPy, ReportLab, SBS.config
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from itertools import combinations

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table,
    TableStyle, HRFlowable,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT

from .config import COLOR_PALETTE, COLOR_CATEGORIES


# ---------------------------------------------------------------------------
# Module-level filtering constants (mirrors ChartGenerator settings)
# ---------------------------------------------------------------------------

# Colors that represent outlines / shadows rather than the character's design
OUTLINE_COLORS = {"black", "onyx", "charcoal", "slate"}

# Outline color percentage below which it is considered an artifact
OUTLINE_THRESHOLD = 8.0


class PDFReportGenerator:
    """
    Generates a professional PDF analysis report from scan-result CSV data.

    The report is always a single-page A4 document (by default) and is
    intended as a concise, shareable summary of the full analysis dataset.

    Attributes:
        csv_path     (Path): Path to the input CSV file.
        output_dir   (Path): Directory where the PDF is saved.
        project_name (str): Display name used in the report title.
        df           (DataFrame): Parsed scan results.
        styles       (StyleSheet1): ReportLab paragraph styles, extended with
                     five custom style entries.
    """

    def __init__(self, csv_path: str, output_dir: str = "output", project_name: str = None):
        """
        Load the CSV and prepare styles.

        Args:
            csv_path     (str): Path to the scan-results CSV.
            output_dir   (str): Directory for the output PDF file.
            project_name (str | None): Report title prefix.  If None, the name
                is inferred from the CSV's parent directory name.
        """
        self.csv_path  = Path(csv_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.df = pd.read_csv(csv_path)
        self._parse_json_columns()

        if project_name:
            self.project_name = project_name
        else:
            # Attempt to derive a human-readable name from the directory path
            inferred = self.csv_path.parent.name.replace("output_", "").replace("_", " ").title()
            self.project_name = inferred if inferred.lower() not in ("output", "charts", "") else "Image Analysis"

        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_json_columns(self):
        """Decode JSON-string columns in the dataframe to Python dicts."""
        for col in ["colors_json", "shapes_json", "color_shape_combos_json"]:
            if col in self.df.columns:
                self.df[col] = self.df[col].apply(
                    lambda x: json.loads(x) if pd.notna(x) and isinstance(x, str) else x
                )

    def _setup_custom_styles(self):
        """
        Register five custom ReportLab paragraph styles.

        Styles added:
          - Title_Custom       : 24 pt centered dark-grey heading.
          - Subtitle_Custom    : 12 pt centered grey sub-heading (used for the timestamp).
          - SectionHeader_Custom: 14 pt blue section heading.
          - BodyText_Custom    : 10 pt body text.
          - SmallText_Custom   : 8 pt grey footer text.
        """
        self.styles.add(ParagraphStyle(
            name="Title_Custom", parent=self.styles["Heading1"],
            fontSize=24, spaceAfter=20, alignment=TA_CENTER,
            textColor=colors.HexColor("#2C3E50"),
        ))
        self.styles.add(ParagraphStyle(
            name="Subtitle_Custom", parent=self.styles["Normal"],
            fontSize=12, spaceAfter=20, alignment=TA_CENTER,
            textColor=colors.HexColor("#7F8C8D"),
        ))
        self.styles.add(ParagraphStyle(
            name="SectionHeader_Custom", parent=self.styles["Heading2"],
            fontSize=14, spaceBefore=15, spaceAfter=10,
            textColor=colors.HexColor("#2980B9"),
        ))
        self.styles.add(ParagraphStyle(
            name="BodyText_Custom", parent=self.styles["Normal"],
            fontSize=10, spaceAfter=8,
        ))
        self.styles.add(ParagraphStyle(
            name="SmallText_Custom", parent=self.styles["Normal"],
            fontSize=8, textColor=colors.HexColor("#7F8C8D"),
        ))

    def _get_color_hex(self, color_name: str) -> str:
        """
        Return the hex color code for a named palette color.

        Args:
            color_name (str): A key from COLOR_PALETTE.

        Returns:
            str: Hex string, or '#888888' as a fallback.
        """
        if color_name in COLOR_PALETTE:
            return COLOR_PALETTE[color_name]["hex"]
        return "#888888"

    def _filter_colors(self, color_dict: dict) -> dict:
        """
        Remove outline / artifact colors from a color-percentage dict.

        Args:
            color_dict (dict): {color_name: percentage}.

        Returns:
            dict: Filtered and renormalized dict, sorted by descending percentage.
        """
        filtered = {}
        for color, pct in color_dict.items():
            if color in OUTLINE_COLORS and pct < OUTLINE_THRESHOLD:
                continue
            if pct < 1.0:
                continue
            filtered[color] = pct

        total = sum(filtered.values())
        if total > 0:
            filtered = {k: (v / total) * 100 for k, v in filtered.items()}
        return dict(sorted(filtered.items(), key=lambda x: x[1], reverse=True))

    def _aggregate_colors(self, filtered: bool = True) -> dict:
        """
        Aggregate color percentages across all characters.

        Args:
            filtered (bool): Whether to apply artifact filtering first.

        Returns:
            dict: {color_name: aggregated_percentage}, sorted descending.
        """
        color_totals = defaultdict(float)
        for row_colors in self.df["colors_json"]:
            if filtered:
                row_colors = self._filter_colors(row_colors)
            for color, pct in row_colors.items():
                color_totals[color] += pct

        total = sum(color_totals.values())
        if total > 0:
            color_totals = {k: v / total * 100 for k, v in color_totals.items()}
        return dict(sorted(color_totals.items(), key=lambda x: x[1], reverse=True))

    def _aggregate_shapes(self) -> dict:
        """
        Aggregate shape percentages across all characters.

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

    def _get_color_pairs(self, filtered: bool = True, min_pct: float = 5.0) -> dict:
        """
        Count how many characters share each two-color combination.

        Args:
            filtered (bool): Whether to apply artifact filtering.
            min_pct  (float): Minimum percentage for a color to be "significant".

        Returns:
            dict: {(color1, color2): count}, sorted by descending count.
        """
        pair_counts = defaultdict(int)
        for _, row in self.df.iterrows():
            row_colors = row["colors_json"]
            if filtered:
                row_colors = self._filter_colors(row_colors)
            significant = [c for c, p in row_colors.items() if p >= min_pct][:5]
            if len(significant) >= 2:
                for pair in combinations(sorted(significant), 2):
                    pair_counts[pair] += 1

        return dict(sorted(pair_counts.items(), key=lambda x: x[1], reverse=True))

    def _categorize_colors(self, filtered: bool = True) -> dict:
        """
        Break the aggregated color data into six thematic categories.

        Args:
            filtered (bool): Whether to use filtered color data.

        Returns:
            dict: {category_name: total_percentage}, sorted descending.
        """
        agg_colors     = self._aggregate_colors(filtered=filtered)
        category_totals = defaultdict(float)

        for color, pct in agg_colors.items():
            for category, cat_colors in COLOR_CATEGORIES.items():
                if color in cat_colors:
                    category_totals[category] += pct
                    break

        return dict(sorted(category_totals.items(), key=lambda x: x[1], reverse=True))

    # ------------------------------------------------------------------
    # Public report generation
    # ------------------------------------------------------------------

    def generate_report(self, output_filename: str = None, page_size=A4) -> Path:
        """
        Build and save the full PDF report.

        Args:
            output_filename (str | None): Filename for the PDF.  Defaults to
                ``<project_name_lowercase>_analysis_report.pdf``.
            page_size: ReportLab page-size constant.  Defaults to A4.

        Returns:
            Path: Absolute path to the written PDF file.
        """
        if output_filename is None:
            safe_name       = self.project_name.lower().replace(" ", "_")
            output_filename = f"{safe_name}_analysis_report.pdf"

        output_path = self.output_dir / output_filename
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=page_size,
            rightMargin=1 * cm, leftMargin=1 * cm,
            topMargin=1 * cm, bottomMargin=1 * cm,
        )

        story = []

        # ---- Title ----
        story.append(Paragraph(
            f"{self.project_name} — Visual Analysis Report",
            self.styles["Title_Custom"],
        ))
        story.append(Paragraph(
            f"Generated on {datetime.now().strftime('%B %d, %Y at %H:%M')}",
            self.styles["Subtitle_Custom"],
        ))
        story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#3498DB")))
        story.append(Spacer(1, 0.3 * cm))

        # ---- Overview statistics ----
        story.append(Paragraph("Overview", self.styles["SectionHeader_Custom"]))

        agg_colors  = self._aggregate_colors()
        agg_shapes  = self._aggregate_shapes()
        total_images  = len(self.df)
        total_colors  = len(agg_colors)
        total_shapes  = len(agg_shapes)
        dominant_color = list(agg_colors.keys())[0] if agg_colors else "N/A"
        dominant_shape = list(agg_shapes.keys())[0] if agg_shapes else "N/A"

        overview_data  = [
            ["Total Images Analyzed", str(total_images)],
            ["Unique Colors Detected", str(total_colors)],
            ["Unique Shapes Detected", str(total_shapes)],
            ["Most Common Color",      dominant_color],
            ["Most Common Shape",      dominant_shape],
        ]

        overview_table = Table(overview_data, colWidths=[4 * cm, 4 * cm])
        overview_table.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (0, -1), colors.HexColor("#ECF0F1")),
            ("TEXTCOLOR",    (0, 0), (-1, -1), colors.HexColor("#2C3E50")),
            ("ALIGN",        (0, 0), (-1, -1), "LEFT"),
            ("FONTNAME",     (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE",     (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 8),
            ("TOPPADDING",   (0, 0), (-1, -1), 8),
            ("GRID",         (0, 0), (-1, -1), 0.5, colors.HexColor("#BDC3C7")),
        ]))
        story.append(overview_table)
        story.append(Spacer(1, 0.5 * cm))

        # ---- Top 10 colors (filtered) ----
        story.append(Paragraph("Top 10 Colors (Filtered)", self.styles["SectionHeader_Custom"]))

        top_colors  = dict(list(self._aggregate_colors(filtered=True).items())[:10])
        color_data  = [["Color", "Percentage", "Sample"]]

        for color_name, pct in top_colors.items():
            color_data.append([color_name, f"{pct:.1f}%", "███"])

        color_table = Table(color_data, colWidths=[3.5 * cm, 2.5 * cm, 2 * cm])

        table_style = [
            ("BACKGROUND",   (0, 0), (-1, 0), colors.HexColor("#3498DB")),
            ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
            ("ALIGN",        (0, 0), (-1, -1), "LEFT"),
            ("ALIGN",        (1, 0), (1, -1), "RIGHT"),
            ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",     (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
            ("TOPPADDING",   (0, 0), (-1, -1), 6),
            ("GRID",         (0, 0), (-1, -1), 0.5, colors.HexColor("#BDC3C7")),
        ]

        # Apply the actual palette hex color to each swatch cell
        for i, (color_name, _) in enumerate(top_colors.items(), start=1):
            hex_color = self._get_color_hex(color_name)
            table_style.append(("TEXTCOLOR", (2, i), (2, i), colors.HexColor(hex_color)))
            table_style.append(("FONTNAME",  (2, i), (2, i), "Helvetica-Bold"))

        color_table.setStyle(TableStyle(table_style))
        story.append(color_table)
        story.append(Spacer(1, 0.5 * cm))

        # ---- Shape distribution ----
        story.append(Paragraph("Shape Distribution", self.styles["SectionHeader_Custom"]))

        top_shapes = dict(list(agg_shapes.items())[:8])
        shape_data = [["Shape", "Percentage"]]
        for shape_name, pct in top_shapes.items():
            shape_data.append([shape_name.capitalize(), f"{pct:.1f}%"])

        shape_table = Table(shape_data, colWidths=[3.5 * cm, 2.5 * cm])
        shape_table.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, 0), colors.HexColor("#27AE60")),
            ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
            ("ALIGN",        (0, 0), (-1, -1), "LEFT"),
            ("ALIGN",        (1, 0), (1, -1), "RIGHT"),
            ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",     (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
            ("TOPPADDING",   (0, 0), (-1, -1), 6),
            ("GRID",         (0, 0), (-1, -1), 0.5, colors.HexColor("#BDC3C7")),
        ]))
        story.append(shape_table)
        story.append(Spacer(1, 0.5 * cm))

        # ---- Color categories ----
        story.append(Paragraph("Color Categories", self.styles["SectionHeader_Custom"]))

        categories = self._categorize_colors(filtered=True)
        cat_data   = [["Category", "Percentage"]]
        for cat_name, pct in categories.items():
            cat_data.append([cat_name.capitalize(), f"{pct:.1f}%"])

        cat_table = Table(cat_data, colWidths=[3.5 * cm, 2.5 * cm])
        cat_table.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, 0), colors.HexColor("#8E44AD")),
            ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
            ("ALIGN",        (0, 0), (-1, -1), "LEFT"),
            ("ALIGN",        (1, 0), (1, -1), "RIGHT"),
            ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",     (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
            ("TOPPADDING",   (0, 0), (-1, -1), 6),
            ("GRID",         (0, 0), (-1, -1), 0.5, colors.HexColor("#BDC3C7")),
        ]))
        story.append(cat_table)
        story.append(Spacer(1, 0.5 * cm))

        # ---- Most common color pairs ----
        story.append(Paragraph("Most Common Color Combinations", self.styles["SectionHeader_Custom"]))

        pairs     = self._get_color_pairs(filtered=True)
        top_pairs = dict(list(pairs.items())[:8])

        if top_pairs:
            pair_data = [["Color Pair", "Count"]]
            for (c1, c2), count in top_pairs.items():
                pair_data.append([f"{c1} + {c2}", str(count)])

            pair_table = Table(pair_data, colWidths=[5 * cm, 2 * cm])
            pair_table.setStyle(TableStyle([
                ("BACKGROUND",   (0, 0), (-1, 0), colors.HexColor("#E67E22")),
                ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
                ("ALIGN",        (0, 0), (-1, -1), "LEFT"),
                ("ALIGN",        (1, 0), (1, -1), "CENTER"),
                ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE",     (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
                ("TOPPADDING",   (0, 0), (-1, -1), 6),
                ("GRID",         (0, 0), (-1, -1), 0.5, colors.HexColor("#BDC3C7")),
            ]))
            story.append(pair_table)
        else:
            story.append(Paragraph("No significant color pairs found.", self.styles["BodyText_Custom"]))

        story.append(Spacer(1, 0.5 * cm))

        # ---- Key insights (auto-generated) ----
        story.append(Paragraph("Key Insights", self.styles["SectionHeader_Custom"]))

        insights = []

        top_category = list(categories.keys())[0] if categories else None
        if top_category:
            insights.append(
                f"• The collection primarily uses <b>{top_category}</b> colors "
                f"({categories[top_category]:.1f}% of all colors)."
            )

        if total_colors > 30:
            insights.append(f"• High color diversity detected with {total_colors} unique colors across the dataset.")
        elif total_colors > 15:
            insights.append(f"• Moderate color diversity with {total_colors} unique colors.")
        else:
            insights.append(f"• Limited color palette with only {total_colors} unique colors.")

        top_shape = list(agg_shapes.keys())[0] if agg_shapes else None
        if top_shape:
            shape_pct    = agg_shapes[top_shape]
            design_label = (
                "organic/natural"
                if top_shape in ("curved", "blob", "ellipse", "circle")
                else "geometric/angular"
            )
            insights.append(
                f"• <b>{top_shape.capitalize()}</b> is the dominant shape ({shape_pct:.1f}%), "
                f"suggesting {design_label} design patterns."
            )

        if top_pairs:
            top_pair = list(top_pairs.keys())[0]
            insights.append(
                f"• The most common color pairing is "
                f"<b>{top_pair[0]} + {top_pair[1]}</b>, "
                f"appearing in {top_pairs[top_pair]} images."
            )

        for insight in insights:
            story.append(Paragraph(insight, self.styles["BodyText_Custom"]))

        story.append(Spacer(1, 0.5 * cm))

        # ---- Footer ----
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#BDC3C7")))
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph(
            f"Generated by Game Image Analyzer • {total_images} images analyzed • "
            f"{datetime.now().strftime('%Y-%m-%d')}",
            self.styles["SmallText_Custom"],
        ))

        doc.build(story)
        print(f"PDF report saved to: {output_path}")
        return output_path
