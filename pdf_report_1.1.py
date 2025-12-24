"""
PDF Summary Report Generator for Game Image Analysis
Creates a professional one-page PDF summary of analysis results.
Works with any game or image collection - not limited to Pokemon.
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, 
                                 TableStyle, Image, PageBreak, HRFlowable)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.graphics.shapes import Drawing, Rect
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.barcharts import HorizontalBarChart
from config import COLOR_PALETTE, COLOR_CATEGORIES

# Outline colors to filter
OUTLINE_COLORS = {"black", "onyx", "charcoal", "slate"}
OUTLINE_THRESHOLD = 8.0


class PDFReportGenerator:
    def __init__(self, csv_path, output_dir="output", project_name=None):
        self.csv_path = Path(csv_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.df = pd.read_csv(csv_path)
        self._parse_json_columns()
        
        # Auto-detect project name from folder or use provided
        if project_name:
            self.project_name = project_name
        else:
            # Try to infer from path
            self.project_name = self.csv_path.parent.name.replace("output_", "").replace("_", " ").title()
            if self.project_name.lower() in ["output", "charts", ""]:
                self.project_name = "Image Analysis"
        
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
    
    def _parse_json_columns(self):
        """Parse JSON columns in the dataframe."""
        json_cols = ["colors_json", "shapes_json", "color_shape_combos_json"]
        for col in json_cols:
            if col in self.df.columns:
                self.df[col] = self.df[col].apply(lambda x: json.loads(x) if pd.notna(x) and isinstance(x, str) else x)
    
    def _setup_custom_styles(self):
        """Setup custom paragraph styles."""
        self.styles.add(ParagraphStyle(
            name='Title_Custom',
            parent=self.styles['Heading1'],
            fontSize=24,
            spaceAfter=20,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#2C3E50')
        ))
        self.styles.add(ParagraphStyle(
            name='Subtitle',
            parent=self.styles['Normal'],
            fontSize=12,
            spaceAfter=20,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#7F8C8D')
        ))
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=14,
            spaceBefore=15,
            spaceAfter=10,
            textColor=colors.HexColor('#2980B9')
        ))
        self.styles.add(ParagraphStyle(
            name='BodyText',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceAfter=8
        ))
        self.styles.add(ParagraphStyle(
            name='SmallText',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#7F8C8D')
        ))
    
    def _get_color_hex(self, color_name):
        """Get hex color code for a color name."""
        if color_name in COLOR_PALETTE:
            return COLOR_PALETTE[color_name]["hex"]
        return "#888888"
    
    def _filter_colors(self, color_dict):
        """Filter out outline colors."""
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
    
    def _aggregate_colors(self, filtered=True):
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
    
    def _aggregate_shapes(self):
        """Aggregate shape data across all entries."""
        shape_totals = defaultdict(float)
        for shapes in self.df["shapes_json"]:
            for shape, pct in shapes.items():
                shape_totals[shape] += pct
        
        total = sum(shape_totals.values())
        if total > 0:
            shape_totals = {k: v/total * 100 for k, v in shape_totals.items()}
        return dict(sorted(shape_totals.items(), key=lambda x: x[1], reverse=True))
    
    def _get_color_pairs(self, filtered=True, min_pct=5.0):
        """Get most common color pairs."""
        from itertools import combinations
        pair_counts = defaultdict(int)
        
        for _, row in self.df.iterrows():
            colors = row["colors_json"]
            if filtered:
                colors = self._filter_colors(colors)
            
            significant = [c for c, p in colors.items() if p >= min_pct][:5]
            if len(significant) >= 2:
                for pair in combinations(sorted(significant), 2):
                    pair_counts[pair] += 1
        
        return dict(sorted(pair_counts.items(), key=lambda x: x[1], reverse=True))
    
    def _categorize_colors(self, filtered=True):
        """Get color category breakdown."""
        colors = self._aggregate_colors(filtered=filtered)
        category_totals = defaultdict(float)
        
        for color, pct in colors.items():
            for category, cat_colors in COLOR_CATEGORIES.items():
                if color in cat_colors:
                    category_totals[category] += pct
                    break
        
        return dict(sorted(category_totals.items(), key=lambda x: x[1], reverse=True))
    
    def generate_report(self, output_filename=None, page_size=A4):
        """Generate the PDF summary report."""
        if output_filename is None:
            safe_name = self.project_name.lower().replace(" ", "_")
            output_filename = f"{safe_name}_analysis_report.pdf"
        
        output_path = self.output_dir / output_filename
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=page_size,
            rightMargin=1*cm,
            leftMargin=1*cm,
            topMargin=1*cm,
            bottomMargin=1*cm
        )
        
        story = []
        
        # === TITLE ===
        story.append(Paragraph(f"{self.project_name} - Visual Analysis Report", self.styles['Title_Custom']))
        story.append(Paragraph(
            f"Generated on {datetime.now().strftime('%B %d, %Y at %H:%M')}",
            self.styles['Subtitle']
        ))
        story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#3498DB')))
        story.append(Spacer(1, 0.3*cm))
        
        # === OVERVIEW SECTION ===
        story.append(Paragraph("Overview", self.styles['SectionHeader']))
        
        total_images = len(self.df)
        total_colors = len(self._aggregate_colors())
        total_shapes = len(self._aggregate_shapes())
        dominant_color = list(self._aggregate_colors().keys())[0] if self._aggregate_colors() else "N/A"
        dominant_shape = list(self._aggregate_shapes().keys())[0] if self._aggregate_shapes() else "N/A"
        
        overview_data = [
            ["Total Images Analyzed", str(total_images)],
            ["Unique Colors Detected", str(total_colors)],
            ["Unique Shapes Detected", str(total_shapes)],
            ["Most Common Color", dominant_color],
            ["Most Common Shape", dominant_shape],
        ]
        
        overview_table = Table(overview_data, colWidths=[4*cm, 4*cm])
        overview_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#ECF0F1')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#2C3E50')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#BDC3C7')),
        ]))
        story.append(overview_table)
        story.append(Spacer(1, 0.5*cm))
        
        # === TOP COLORS SECTION ===
        story.append(Paragraph("Top 10 Colors (Filtered)", self.styles['SectionHeader']))
        
        top_colors = dict(list(self._aggregate_colors(filtered=True).items())[:10])
        color_data = [["Color", "Percentage", "Sample"]]
        
        for color_name, pct in top_colors.items():
            hex_color = self._get_color_hex(color_name)
            color_data.append([color_name, f"{pct:.1f}%", "███"])
        
        color_table = Table(color_data, colWidths=[3.5*cm, 2.5*cm, 2*cm])
        
        # Build style with color samples
        table_style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498DB')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#BDC3C7')),
        ]
        
        # Add color to sample column
        for i, (color_name, _) in enumerate(top_colors.items(), start=1):
            hex_color = self._get_color_hex(color_name)
            table_style.append(('TEXTCOLOR', (2, i), (2, i), colors.HexColor(hex_color)))
            table_style.append(('FONTNAME', (2, i), (2, i), 'Helvetica-Bold'))
        
        color_table.setStyle(TableStyle(table_style))
        story.append(color_table)
        story.append(Spacer(1, 0.5*cm))
        
        # === TOP SHAPES SECTION ===
        story.append(Paragraph("Shape Distribution", self.styles['SectionHeader']))
        
        top_shapes = dict(list(self._aggregate_shapes().items())[:8])
        shape_data = [["Shape", "Percentage"]]
        
        for shape_name, pct in top_shapes.items():
            shape_data.append([shape_name.capitalize(), f"{pct:.1f}%"])
        
        shape_table = Table(shape_data, colWidths=[3.5*cm, 2.5*cm])
        shape_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#27AE60')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#BDC3C7')),
        ]))
        story.append(shape_table)
        story.append(Spacer(1, 0.5*cm))
        
        # === COLOR CATEGORIES ===
        story.append(Paragraph("Color Categories", self.styles['SectionHeader']))
        
        categories = self._categorize_colors(filtered=True)
        cat_data = [["Category", "Percentage"]]
        
        category_colors_map = {
            "warm": "#E74C3C",
            "cool": "#3498DB", 
            "neutral": "#95A5A6",
            "vibrant": "#9B59B6",
            "pastel": "#F1C40F",
            "dark": "#2C3E50"
        }
        
        for cat_name, pct in categories.items():
            cat_data.append([cat_name.capitalize(), f"{pct:.1f}%"])
        
        cat_table = Table(cat_data, colWidths=[3.5*cm, 2.5*cm])
        cat_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#8E44AD')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#BDC3C7')),
        ]))
        story.append(cat_table)
        story.append(Spacer(1, 0.5*cm))
        
        # === TOP COLOR PAIRS ===
        story.append(Paragraph("Most Common Color Combinations", self.styles['SectionHeader']))
        
        pairs = self._get_color_pairs(filtered=True)
        top_pairs = dict(list(pairs.items())[:8])
        
        if top_pairs:
            pair_data = [["Color Pair", "Count"]]
            for (c1, c2), count in top_pairs.items():
                pair_data.append([f"{c1} + {c2}", str(count)])
            
            pair_table = Table(pair_data, colWidths=[5*cm, 2*cm])
            pair_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E67E22')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (1, 0), (1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#BDC3C7')),
            ]))
            story.append(pair_table)
        else:
            story.append(Paragraph("No significant color pairs found.", self.styles['BodyText']))
        
        story.append(Spacer(1, 0.5*cm))
        
        # === KEY INSIGHTS ===
        story.append(Paragraph("Key Insights", self.styles['SectionHeader']))
        
        insights = []
        
        # Insight 1: Dominant color category
        top_category = list(categories.keys())[0] if categories else None
        if top_category:
            insights.append(f"• The collection primarily uses <b>{top_category}</b> colors ({categories[top_category]:.1f}% of all colors).")
        
        # Insight 2: Color diversity
        if total_colors > 30:
            insights.append(f"• High color diversity detected with {total_colors} unique colors across the dataset.")
        elif total_colors > 15:
            insights.append(f"• Moderate color diversity with {total_colors} unique colors.")
        else:
            insights.append(f"• Limited color palette with only {total_colors} unique colors.")
        
        # Insight 3: Shape patterns
        top_shape = list(self._aggregate_shapes().keys())[0] if self._aggregate_shapes() else None
        if top_shape:
            shape_pct = self._aggregate_shapes()[top_shape]
            insights.append(f"• <b>{top_shape.capitalize()}</b> is the dominant shape ({shape_pct:.1f}%), suggesting {'organic/natural' if top_shape in ['curved', 'blob', 'ellipse', 'circle'] else 'geometric/angular'} design patterns.")
        
        # Insight 4: Color combinations
        if top_pairs:
            top_pair = list(top_pairs.keys())[0]
            insights.append(f"• The most common color pairing is <b>{top_pair[0]} + {top_pair[1]}</b>, appearing in {top_pairs[top_pair]} images.")
        
        for insight in insights:
            story.append(Paragraph(insight, self.styles['BodyText']))
        
        story.append(Spacer(1, 0.5*cm))
        
        # === FOOTER ===
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#BDC3C7')))
        story.append(Spacer(1, 0.2*cm))
        story.append(Paragraph(
            f"Generated by Game Image Analyzer • {total_images} images analyzed • {datetime.now().strftime('%Y-%m-%d')}",
            self.styles['SmallText']
        ))
        
        # Build PDF
        doc.build(story)
        print(f"PDF report saved to: {output_path}")
        return output_path


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate PDF summary report from scan results")
    parser.add_argument("csv", help="Path to scan results CSV")
    parser.add_argument("-o", "--output", default="output", help="Output directory")
    parser.add_argument("-n", "--name", help="Project name (e.g., 'Pokemon Gen 1', 'Mario Characters')")
    parser.add_argument("--filename", help="Output PDF filename")
    
    args = parser.parse_args()
    
    generator = PDFReportGenerator(
        args.csv,
        output_dir=args.output,
        project_name=args.name
    )
    
    generator.generate_report(output_filename=args.filename)


if __name__ == "__main__":
    main()
