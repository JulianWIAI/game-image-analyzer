# Game Image Analyzer

A comprehensive toolkit for analyzing colors, shapes, and patterns in video game character/monster images. Perfect for research, character design inspiration, and understanding visual design patterns across games.

## Features

- **Image Scanner**: Extract color distributions and shape patterns from images
- **Chart Generator**: Create both static (PNG) and interactive (HTML) visualizations
- **Character Overview**: Generate individual analysis reports for each character
- **Type Analyzer**: Correlate visual properties with character types/attributes
- **Pokemon Support**: Built-in integration with PokeAPI for fetching Pokemon type data

## Installation

```bash
# Clone or download the project
cd game_image_analyzer

# Install dependencies
pip install -r requirements.txt
```

## Quick Start

### Full Pipeline (Recommended)
Run the complete analysis pipeline with one command:

```bash
cd scripts
python main.py full ./path/to/images -o ./output --fetch-pokemon
```

### Step-by-Step Usage

#### 1. Scan Images
```bash
# Scan a directory of images
python main.py scan ./pokemon_images -o ./output

# Scan a single image
python main.py scan ./pikachu.png -o ./output -n "Pikachu"
```

#### 2. Generate Charts
```bash
# Generate all charts (static + interactive)
python main.py charts ./output/scan_results.csv

# Static only (PNG)
python main.py charts ./output/scan_results.csv --static-only

# Interactive only (HTML)
python main.py charts ./output/scan_results.csv --interactive-only
```

#### 3. Generate Character Overviews
```bash
# All characters
python main.py overview ./output/scan_results.csv --all

# Specific character
python main.py overview ./output/scan_results.csv -n "Pikachu"

# Compare multiple characters
python main.py overview ./output/scan_results.csv --compare Pikachu Charizard Mewtwo
```

#### 4. Type Analysis
```bash
# With Pokemon API (auto-fetches type data)
python main.py types ./output/scan_results.csv --fetch-pokemon

# With your own type data file
python main.py types ./output/scan_results.csv -t ./my_types.csv
```

## Output Structure

```
output/
├── scan_results.csv          # Raw scan data
├── charts/
│   ├── color_frequency_static.png
│   ├── color_frequency_interactive.html
│   ├── shape_frequency_static.png
│   ├── shape_frequency_interactive.html
│   ├── color_shape_heatmap_static.png
│   ├── color_shape_heatmap_interactive.html
│   ├── color_categories_static.png
│   ├── shape_color_sunburst.html
│   └── color_treemap.html
├── overviews/
│   ├── Pikachu_overview.png
│   ├── Pikachu_overview.html
│   └── ...
└── analysis/
    ├── type_color_heatmap.png
    ├── type_shape_heatmap.png
    ├── attribute_correlations.png
    ├── type_analysis_dashboard.html
    └── type_analysis_report.txt
```

## CSV Format

### Scan Results (scan_results.csv)
| Column | Description |
|--------|-------------|
| name | Character name |
| image_path | Path to original image |
| dominant_color | Most common color |
| dominant_shape | Most common shape |
| color_[name]_pct | Percentage of each color |
| shape_[name]_pct | Percentage of each shape |
| colors_json | Full color data as JSON |
| shapes_json | Full shape data as JSON |
| color_shape_combos_json | Color-shape associations |

### Type Data (optional)
Create a CSV with at least these columns:
| Column | Description |
|--------|-------------|
| name | Character name (must match scan data) |
| type_primary | Primary type (e.g., "fire", "water") |
| type_secondary | Secondary type (optional) |

Additional columns for analysis:
- `is_legendary`, `is_mythical`, `is_baby`
- `base_happiness`, `capture_rate`
- `attack`, `defense`, `hp`, `speed`

## Color Palette

The analyzer uses a detailed 64-color palette including:
- **Reds**: crimson, scarlet, cherry, ruby, burgundy, maroon, coral, salmon
- **Oranges**: tangerine, pumpkin, amber, rust, peach, apricot
- **Yellows**: gold, canary, lemon, mustard, cream, buttercup
- **Greens**: emerald, jade, mint, sage, olive, forest, lime, teal, seafoam
- **Blues**: sky, azure, cobalt, navy, sapphire, cerulean, powder, steel, denim, cyan
- **Purples**: lavender, lilac, violet, plum, grape, orchid, mauve, amethyst, indigo
- **Pinks**: rose, blush, fuchsia, magenta, bubblegum, flamingo, hot_pink
- **Browns**: chocolate, coffee, caramel, tan, sienna, mahogany, bronze
- **Neutrals**: white, ivory, pearl, silver, ash, slate, charcoal, onyx, black

## Shape Detection

Detected shape categories:
- **Geometric**: circle, ellipse, triangle, square, rectangle, pentagon, hexagon
- **Complex**: star, curved, angular, spiky, blob, spiral

## Extending for Other Games

### Custom Type Data
Create a CSV file mapping your characters to types:

```csv
name,type_primary,type_secondary,attribute
Mario,hero,fire,friendly
Bowser,villain,fire,aggressive
Link,hero,sword,brave
```

Then run:
```bash
python main.py types ./scan_results.csv -t ./my_game_types.csv
```

### Custom Color Associations
Edit `config.py` to add your own attribute-color mappings:

```python
ATTRIBUTE_COLOR_ASSOCIATIONS = {
    "heroic": ["azure", "gold", "white"],
    "villainous": ["crimson", "black", "violet"],
    "magical": ["violet", "gold", "cyan"],
    # Add your own...
}
```

## Tips for Best Results

1. **Image Quality**: Use high-resolution images with clean backgrounds
2. **Consistent Naming**: Name image files to match your type data
3. **Background Removal**: The scanner attempts automatic background removal, but transparent PNGs work best
4. **Batch Processing**: For large datasets, the scanner processes efficiently in batches

## Troubleshooting

### "Module not found" errors
```bash
pip install -r requirements.txt
```

### Poor shape detection
- Increase image resolution
- Use images with clear outlines
- Adjust `min_contour_area` in `config.py`

### Colors not matching expected
- The analyzer uses nearest-neighbor color matching
- Edit `COLOR_PALETTE` in `config.py` to add specific colors

## License

MIT License - Feel free to use and modify for your research!
