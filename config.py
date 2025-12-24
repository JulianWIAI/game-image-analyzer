"""
Configuration file for Game Image Analyzer
Contains detailed color palettes, shape definitions, and analysis settings
"""

# Detailed color palette with 64 distinct colors
# Each color has: name, RGB range (min, max), hex code for visualization
COLOR_PALETTE = {
    # Reds
    "crimson": {"rgb_center": (220, 20, 60), "hex": "#DC143C"},
    "scarlet": {"rgb_center": (255, 36, 0), "hex": "#FF2400"},
    "cherry": {"rgb_center": (222, 49, 99), "hex": "#DE3163"},
    "ruby": {"rgb_center": (224, 17, 95), "hex": "#E0115F"},
    "burgundy": {"rgb_center": (128, 0, 32), "hex": "#800020"},
    "maroon": {"rgb_center": (128, 0, 0), "hex": "#800000"},
    "coral": {"rgb_center": (255, 127, 80), "hex": "#FF7F50"},
    "salmon": {"rgb_center": (250, 128, 114), "hex": "#FA8072"},
    
    # Oranges
    "tangerine": {"rgb_center": (255, 159, 0), "hex": "#FF9F00"},
    "pumpkin": {"rgb_center": (255, 117, 24), "hex": "#FF7518"},
    "amber": {"rgb_center": (255, 191, 0), "hex": "#FFBF00"},
    "rust": {"rgb_center": (183, 65, 14), "hex": "#B7410E"},
    "peach": {"rgb_center": (255, 218, 185), "hex": "#FFDAB9"},
    "apricot": {"rgb_center": (251, 206, 177), "hex": "#FBCEB1"},
    
    # Yellows
    "gold": {"rgb_center": (255, 215, 0), "hex": "#FFD700"},
    "canary": {"rgb_center": (255, 239, 0), "hex": "#FFEF00"},
    "lemon": {"rgb_center": (255, 247, 0), "hex": "#FFF700"},
    "mustard": {"rgb_center": (255, 219, 88), "hex": "#FFDB58"},
    "cream": {"rgb_center": (255, 253, 208), "hex": "#FFFDD0"},
    "buttercup": {"rgb_center": (249, 241, 165), "hex": "#F9F1A5"},
    
    # Greens
    "emerald": {"rgb_center": (80, 200, 120), "hex": "#50C878"},
    "jade": {"rgb_center": (0, 168, 107), "hex": "#00A86B"},
    "mint": {"rgb_center": (152, 255, 152), "hex": "#98FF98"},
    "sage": {"rgb_center": (188, 184, 138), "hex": "#BCB88A"},
    "olive": {"rgb_center": (128, 128, 0), "hex": "#808000"},
    "forest": {"rgb_center": (34, 139, 34), "hex": "#228B22"},
    "lime": {"rgb_center": (50, 205, 50), "hex": "#32CD32"},
    "teal": {"rgb_center": (0, 128, 128), "hex": "#008080"},
    "seafoam": {"rgb_center": (159, 226, 191), "hex": "#9FE2BF"},
    
    # Blues
    "sky": {"rgb_center": (135, 206, 235), "hex": "#87CEEB"},
    "azure": {"rgb_center": (0, 127, 255), "hex": "#007FFF"},
    "cobalt": {"rgb_center": (0, 71, 171), "hex": "#0047AB"},
    "navy": {"rgb_center": (0, 0, 128), "hex": "#000080"},
    "sapphire": {"rgb_center": (15, 82, 186), "hex": "#0F52BA"},
    "cerulean": {"rgb_center": (0, 123, 167), "hex": "#007BA7"},
    "powder": {"rgb_center": (176, 224, 230), "hex": "#B0E0E6"},
    "steel": {"rgb_center": (70, 130, 180), "hex": "#4682B4"},
    "denim": {"rgb_center": (21, 96, 189), "hex": "#1560BD"},
    "cyan": {"rgb_center": (0, 255, 255), "hex": "#00FFFF"},
    
    # Purples
    "lavender": {"rgb_center": (230, 230, 250), "hex": "#E6E6FA"},
    "lilac": {"rgb_center": (200, 162, 200), "hex": "#C8A2C8"},
    "violet": {"rgb_center": (238, 130, 238), "hex": "#EE82EE"},
    "plum": {"rgb_center": (142, 69, 133), "hex": "#8E4585"},
    "grape": {"rgb_center": (111, 45, 168), "hex": "#6F2DA8"},
    "orchid": {"rgb_center": (218, 112, 214), "hex": "#DA70D6"},
    "mauve": {"rgb_center": (224, 176, 255), "hex": "#E0B0FF"},
    "amethyst": {"rgb_center": (153, 102, 204), "hex": "#9966CC"},
    "indigo": {"rgb_center": (75, 0, 130), "hex": "#4B0082"},
    
    # Pinks
    "rose": {"rgb_center": (255, 0, 127), "hex": "#FF007F"},
    "blush": {"rgb_center": (222, 93, 131), "hex": "#DE5D83"},
    "fuchsia": {"rgb_center": (255, 0, 255), "hex": "#FF00FF"},
    "magenta": {"rgb_center": (255, 0, 144), "hex": "#FF0090"},
    "bubblegum": {"rgb_center": (255, 193, 204), "hex": "#FFC1CC"},
    "flamingo": {"rgb_center": (252, 142, 172), "hex": "#FC8EAC"},
    "hot_pink": {"rgb_center": (255, 105, 180), "hex": "#FF69B4"},
    
    # Browns
    "chocolate": {"rgb_center": (123, 63, 0), "hex": "#7B3F00"},
    "coffee": {"rgb_center": (111, 78, 55), "hex": "#6F4E37"},
    "caramel": {"rgb_center": (255, 213, 154), "hex": "#FFD59A"},
    "tan": {"rgb_center": (210, 180, 140), "hex": "#D2B48C"},
    "sienna": {"rgb_center": (160, 82, 45), "hex": "#A0522D"},
    "mahogany": {"rgb_center": (192, 64, 0), "hex": "#C04000"},
    "bronze": {"rgb_center": (205, 127, 50), "hex": "#CD7F32"},
    
    # Neutrals
    "white": {"rgb_center": (255, 255, 255), "hex": "#FFFFFF"},
    "ivory": {"rgb_center": (255, 255, 240), "hex": "#FFFFF0"},
    "pearl": {"rgb_center": (234, 224, 200), "hex": "#EAE0C8"},
    "silver": {"rgb_center": (192, 192, 192), "hex": "#C0C0C0"},
    "ash": {"rgb_center": (178, 190, 181), "hex": "#B2BEB5"},
    "slate": {"rgb_center": (112, 128, 144), "hex": "#708090"},
    "charcoal": {"rgb_center": (54, 69, 79), "hex": "#36454F"},
    "onyx": {"rgb_center": (53, 56, 57), "hex": "#353839"},
    "black": {"rgb_center": (0, 0, 0), "hex": "#000000"},
}

# Color categories for grouping
COLOR_CATEGORIES = {
    "warm": ["crimson", "scarlet", "cherry", "ruby", "burgundy", "maroon", "coral", "salmon",
             "tangerine", "pumpkin", "amber", "rust", "peach", "apricot",
             "gold", "canary", "lemon", "mustard", "cream", "buttercup"],
    "cool": ["emerald", "jade", "mint", "sage", "olive", "forest", "lime", "teal", "seafoam",
             "sky", "azure", "cobalt", "navy", "sapphire", "cerulean", "powder", "steel", "denim", "cyan"],
    "neutral": ["white", "ivory", "pearl", "silver", "ash", "slate", "charcoal", "onyx", "black",
                "chocolate", "coffee", "caramel", "tan", "sienna", "mahogany", "bronze"],
    "vibrant": ["crimson", "scarlet", "tangerine", "canary", "emerald", "azure", "violet", "fuchsia", "hot_pink"],
    "pastel": ["salmon", "peach", "cream", "mint", "seafoam", "powder", "lavender", "bubblegum", "ivory"],
    "dark": ["burgundy", "maroon", "rust", "forest", "navy", "indigo", "plum", "chocolate", "charcoal", "onyx", "black"],
}

# Shape detection parameters
SHAPE_DEFINITIONS = {
    # Geometric primitives (enhanced detection)
    "circle": {
        "description": "Round, circular forms",
        "contour_approx": 8,  # Minimum vertices for circle approximation
        "circularity_threshold": 0.8,
        "attributes": ["friendly", "soft", "cute", "approachable"]
    },
    "ellipse": {
        "description": "Oval, elongated circular forms",
        "aspect_ratio_range": (1.2, 3.0),
        "circularity_threshold": 0.6,
        "attributes": ["organic", "natural", "flowing"]
    },
    "triangle": {
        "description": "Three-sided angular forms",
        "vertices": 3,
        "attributes": ["sharp", "aggressive", "dynamic", "energetic"]
    },
    "square": {
        "description": "Four equal sides, right angles",
        "vertices": 4,
        "aspect_ratio_range": (0.9, 1.1),
        "attributes": ["stable", "solid", "mechanical", "sturdy"]
    },
    "rectangle": {
        "description": "Four sides, right angles, unequal sides",
        "vertices": 4,
        "aspect_ratio_range": (1.2, 5.0),
        "attributes": ["structured", "orderly", "artificial"]
    },
    "pentagon": {
        "description": "Five-sided polygon",
        "vertices": 5,
        "attributes": ["unique", "mystical", "unusual"]
    },
    "hexagon": {
        "description": "Six-sided polygon",
        "vertices": 6,
        "attributes": ["natural", "honeycomb", "crystalline"]
    },
    "star": {
        "description": "Star-shaped with pointed tips",
        "convexity_defects": True,
        "attributes": ["magical", "special", "celestial"]
    },
    
    # Abstract/organic shapes
    "curved": {
        "description": "Smooth curved edges, non-circular",
        "curvature_analysis": True,
        "attributes": ["organic", "natural", "flowing", "friendly"]
    },
    "angular": {
        "description": "Sharp angles and edges",
        "angle_threshold": 60,  # degrees
        "attributes": ["aggressive", "sharp", "dangerous", "edgy"]
    },
    "spiky": {
        "description": "Multiple pointed protrusions",
        "spike_detection": True,
        "attributes": ["dangerous", "hostile", "defensive", "fierce"]
    },
    "blob": {
        "description": "Irregular, amorphous shape",
        "irregularity_threshold": 0.3,
        "attributes": ["cute", "squishy", "soft", "friendly"]
    },
    "spiral": {
        "description": "Spiral or swirl patterns",
        "pattern_detection": True,
        "attributes": ["mystical", "hypnotic", "magical"]
    },
}

# Character attribute mappings (for type analysis)
ATTRIBUTE_SHAPE_ASSOCIATIONS = {
    "friendly": ["circle", "ellipse", "curved", "blob"],
    "aggressive": ["triangle", "angular", "spiky", "star"],
    "mystical": ["star", "spiral", "hexagon", "pentagon"],
    "sturdy": ["square", "rectangle"],
    "natural": ["ellipse", "curved", "hexagon", "blob"],
    "mechanical": ["square", "rectangle", "angular"],
}

ATTRIBUTE_COLOR_ASSOCIATIONS = {
    "friendly": ["bubblegum", "mint", "sky", "cream", "peach", "lavender"],
    "aggressive": ["crimson", "scarlet", "black", "burgundy", "rust"],
    "mystical": ["violet", "indigo", "amethyst", "gold", "silver"],
    "electric": ["canary", "cyan", "lime", "hot_pink"],
    "natural": ["emerald", "forest", "sage", "tan", "coffee", "seafoam"],
    "fire": ["crimson", "tangerine", "amber", "gold", "rust"],
    "water": ["azure", "cerulean", "navy", "cyan", "powder"],
    "earth": ["sienna", "chocolate", "tan", "olive", "bronze"],
    "poison": ["grape", "plum", "lime", "violet"],
    "ice": ["powder", "white", "cyan", "silver", "sky"],
    "dark": ["onyx", "charcoal", "indigo", "plum", "burgundy"],
    "fairy": ["bubblegum", "lavender", "rose", "cream", "orchid"],
}

# Analysis settings
ANALYSIS_SETTINGS = {
    "min_contour_area": 100,  # Minimum pixel area for shape detection
    "color_sample_rate": 0.1,  # Sample 10% of pixels for color analysis
    "dominant_colors_count": 10,  # Number of dominant colors to extract
    "shape_simplification_epsilon": 0.02,  # Contour approximation factor
    "background_removal": True,  # Attempt to remove background
    "edge_detection_thresholds": (50, 150),  # Canny edge detection
}

# Output settings
OUTPUT_SETTINGS = {
    "chart_dpi": 150,
    "chart_style": "seaborn-v0_8-whitegrid",
    "color_scheme": "viridis",
    "figure_size": (12, 8),
    "overview_size": (16, 12),
}
