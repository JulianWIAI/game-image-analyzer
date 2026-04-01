"""
SBS/ImageScanner.py — Image Color & Shape Scanner
===================================================
Provides the ImageScanner class, which is the first step in the analysis pipeline.

Responsibilities:
  1. Load individual image files or scan entire directories.
  2. Detect and remove background regions (alpha channel, solid-color borders,
     or edge-based fallback) so that only the subject is analyzed.
  3. Extract a color distribution via KMeans clustering, then map each cluster
     to the nearest named color in COLOR_PALETTE using Euclidean distance.
  4. Detect geometric and organic shapes via Canny edge detection + contour
     analysis, then classify each contour using circularity, solidity, vertex
     count, and aspect-ratio heuristics.
  5. Build a color-per-shape breakdown showing which colors appear inside each
     detected shape region.
  6. Export all results to a CSV file for downstream use by ChartGenerator,
     OverviewGenerator, PDFReportGenerator, and TypeAnalyzer.

Dependencies: OpenCV, NumPy, scikit-learn (KMeans), SciPy, SBS.config
"""

import cv2
import numpy as np
import os
import csv
import json
import warnings
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from sklearn.cluster import KMeans
from scipy import ndimage

from .config import COLOR_PALETTE, SHAPE_DEFINITIONS, ANALYSIS_SETTINGS

# Suppress KMeans convergence warnings that can clutter console output
# on small or low-variance images.
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")


class ImageScanner:
    """
    Scans image files to extract color distributions and shape statistics.

    The scanner operates in five stages for each image:
      1. Background removal (alpha, solid-color, or edge-based mask).
      2. Color analysis   (KMeans → nearest named-color mapping).
      3. Shape detection  (Canny edges → contour classification).
      4. Color-shape correlation (dominant color per shape bounding box).
      5. CSV export.

    Attributes:
        output_dir (Path): Directory where result CSV files are written.
        color_tree (list[dict]): Pre-built list of color descriptors used for
            fast nearest-color matching.  Each entry has keys 'name', 'rgb',
            and 'hex'.
        current_image_path (Path): Set at the start of scan_image(); used
            internally by _create_background_mask() to reload the raw file
            with its alpha channel when needed.
    """

    def __init__(self, output_dir: str = "output"):
        """
        Initialize the scanner and create the output directory.

        Args:
            output_dir (str): Path to the directory where CSV results will be
                saved.  Created automatically if it does not exist.
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.color_tree = self._build_color_tree()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_color_tree(self) -> list:
        """
        Build a list of color descriptors for fast nearest-color look-ups.

        Converts each entry in COLOR_PALETTE into a dict with a NumPy RGB
        array so that Euclidean distance can be computed directly without
        repeated conversion during analysis.

        Returns:
            list[dict]: Each dict contains 'name' (str), 'rgb' (np.ndarray),
                and 'hex' (str).
        """
        colors = []
        for name, data in COLOR_PALETTE.items():
            colors.append({
                "name": name,
                "rgb": np.array(data["rgb_center"]),
                "hex": data["hex"],
            })
        return colors

    def _match_color(self, rgb: tuple) -> str:
        """
        Find the closest named color in COLOR_PALETTE for a given RGB triplet.

        Uses brute-force Euclidean distance over all 64 palette entries.
        Acceptable because this is called once per KMeans cluster center
        (not once per pixel).

        Args:
            rgb (tuple): (R, G, B) integer values in the range 0–255.

        Returns:
            str: The palette name of the closest matching color (e.g. 'crimson').
        """
        rgb = np.array(rgb)
        min_dist = float("inf")
        closest = "unknown"
        for color in self.color_tree:
            dist = np.linalg.norm(rgb - color["rgb"])
            if dist < min_dist:
                min_dist = dist
                closest = color["name"]
        return closest

    def _detect_background_color(self, image: np.ndarray):
        """
        Estimate the background color by sampling the image border region.

        Samples a strip of pixels from all four edges (width ≈ 5 % of the
        smaller dimension, minimum 5 px) and returns the most frequent
        color value after rounding to the nearest 10 to reduce noise.

        Args:
            image (np.ndarray): BGR image array (H × W × 3).

        Returns:
            np.ndarray | None: Most-common border color as a (3,) array,
                or None if the border is empty.
        """
        h, w = image.shape[:2]
        border_size = max(5, min(h, w) // 20)

        top    = image[:border_size, :].reshape(-1, 3)
        bottom = image[-border_size:, :].reshape(-1, 3)
        left   = image[:, :border_size].reshape(-1, 3)
        right  = image[:, -border_size:].reshape(-1, 3)

        border_pixels = np.vstack([top, bottom, left, right])

        # Round to the nearest 10 to collapse near-identical colors
        rounded = (border_pixels // 10) * 10
        pixel_tuples = [tuple(p) for p in rounded]
        most_common = Counter(pixel_tuples).most_common(1)

        if most_common:
            return np.array(most_common[0][0])
        return None

    def _create_background_mask(self, image: np.ndarray) -> np.ndarray:
        """
        Create a binary foreground mask that excludes the background.

        Tries three strategies in order, falling back when a strategy
        produces an implausibly small foreground region:

          1. **Alpha channel** – If the file has an alpha channel and at
             least 1 % of pixels are transparent, the alpha is used directly.
          2. **Solid-color border** – Computes pixel-wise distance from the
             dominant border color; pixels below an adaptive threshold are
             treated as background.
          3. **Edge + morphology fallback** – Applies Otsu thresholding and
             morphological clean-up, then keeps only the largest contour.

        Args:
            image (np.ndarray): BGR image (H × W × 3), already loaded.

        Returns:
            np.ndarray: Uint8 mask (H × W) — 255 = foreground, 0 = background.
        """
        h, w = image.shape[:2]
        mask = np.ones((h, w), dtype=np.uint8) * 255

        # Strategy 1 — alpha channel
        original = cv2.imread(str(self.current_image_path), cv2.IMREAD_UNCHANGED)
        if (original is not None
                and len(original.shape) == 3
                and original.shape[2] == 4):
            alpha = original[:, :, 3]
            mask = np.where(alpha > 10, 255, 0).astype(np.uint8)
            if np.sum(mask == 0) > (h * w * 0.01):
                return mask

        # Strategy 2 — solid background color
        bg_color = self._detect_background_color(image)
        if bg_color is not None:
            diff = np.sqrt(
                np.sum((image.astype(np.float32) - bg_color.astype(np.float32)) ** 2, axis=2)
            )
            bg_brightness = np.mean(bg_color)
            # Use a more lenient threshold for very dark or very light backgrounds
            if bg_brightness < 30 or bg_brightness > 225:
                threshold = 50
            else:
                threshold = 30
            mask = np.where(diff > threshold, 255, 0).astype(np.uint8)

        # Strategy 3 — edge-based fallback when the mask covers < 5 % of the image
        mask_coverage = np.sum(mask > 0) / (h * w)
        if mask_coverage < 0.05:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

            # Invert if the subject is dark on a light background
            if np.mean(gray[:10, :]) > np.mean(gray[h // 3:2 * h // 3, w // 3:2 * w // 3]):
                thresh = cv2.bitwise_not(thresh)

            kernel = np.ones((5, 5), np.uint8)
            thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
            thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)

            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                mask = np.zeros((h, w), dtype=np.uint8)
                largest = max(contours, key=cv2.contourArea)
                cv2.drawContours(mask, [largest], -1, 255, -1)
                mask = cv2.dilate(mask, kernel, iterations=2)

        # Final morphological clean-up to close small holes
        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        return mask

    # ------------------------------------------------------------------
    # Public analysis methods
    # ------------------------------------------------------------------

    def analyze_colors(self, image: np.ndarray, mask: np.ndarray = None) -> tuple:
        """
        Extract a named-color distribution from the given image (or masked region).

        Steps:
          1. Isolate foreground pixels using the mask (if provided).
          2. Filter out near-black / near-white pixels that are likely
             background remnants, unless they have high color variance.
          3. Sample up to ``ANALYSIS_SETTINGS['dominant_colors_count']`` clusters
             using KMeans.
          4. Map each cluster center to the nearest palette name.

        Args:
            image (np.ndarray): BGR image array (H × W × 3).
            mask  (np.ndarray | None): Optional binary mask (H × W).  Only
                pixels where mask > 128 are included.

        Returns:
            tuple[dict, dict]: A pair of dicts mapping color names to
                percentages — (raw_distribution, rounded_distribution).
                Both are sorted by descending percentage.
        """
        if mask is not None:
            pixels = image[mask > 128]
        else:
            pixels = image.reshape(-1, 3)

        if len(pixels) == 0:
            return {}, {}

        # Filter near-black / near-white pixels that lack color saturation
        brightness = np.mean(pixels, axis=1)
        color_variance = np.var(pixels, axis=1)
        keep_mask = ((brightness > 15) & (brightness < 240)) | (color_variance > 100)
        filtered_pixels = pixels[keep_mask]

        if len(filtered_pixels) < 100:
            filtered_pixels = pixels   # Fall back to all pixels if too few survive

        # Determine a sensible cluster count based on actual color diversity
        sample_size = max(1000, int(len(filtered_pixels) * ANALYSIS_SETTINGS["color_sample_rate"]))
        if len(filtered_pixels) > sample_size:
            indices = np.random.choice(len(filtered_pixels), sample_size, replace=False)
            sample = filtered_pixels[indices]
        else:
            sample = filtered_pixels

        unique_colors = len(np.unique(sample.round(-1), axis=0))
        n_clusters = min(
            ANALYSIS_SETTINGS["dominant_colors_count"],
            max(2, unique_colors // 5, len(sample) // 50),
        )
        n_clusters = max(2, min(n_clusters, len(sample) // 10))

        try:
            kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10, max_iter=300)
            kmeans.fit(sample)

            cluster_centers = kmeans.cluster_centers_
            labels = kmeans.labels_
            label_counts = Counter(labels)
            total = sum(label_counts.values())

            color_distribution = {}
            for i, center in enumerate(cluster_centers):
                rgb = tuple(map(int, center))
                color_name = self._match_color(rgb[::-1])   # OpenCV BGR → RGB
                percentage = (label_counts[i] / total) * 100

                if color_name in color_distribution:
                    color_distribution[color_name] += percentage
                else:
                    color_distribution[color_name] = percentage

            color_distribution = dict(
                sorted(color_distribution.items(), key=lambda x: x[1], reverse=True)
            )
            color_percentages = {name: round(pct, 2) for name, pct in color_distribution.items()}
            return color_distribution, color_percentages

        except Exception as e:
            print(f"    Warning: Color analysis error — {e}")
            return {}, {}

    def detect_shapes(self, image: np.ndarray, mask: np.ndarray = None) -> tuple:
        """
        Detect and classify shapes in an image using contour analysis.

        Pipeline:
          1. Convert to grayscale → Gaussian blur → Canny edge detection.
          2. Apply the foreground mask to restrict edges to the subject.
          3. Find contours; skip those below the minimum area threshold.
          4. Classify each contour via ``_classify_shape()``.

        Args:
            image (np.ndarray): BGR image (H × W × 3).
            mask  (np.ndarray | None): Optional binary mask (H × W).

        Returns:
            tuple[dict, list]: A pair of:
                - shape_counts (dict): {shape_type: count}
                - shape_details (list[dict]): One dict per detected shape with
                  geometry metrics and classification confidence.
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, *ANALYSIS_SETTINGS["edge_detection_thresholds"])

        if mask is not None:
            edges = cv2.bitwise_and(edges, edges, mask=mask)

        contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

        shape_counts = defaultdict(int)
        shape_details = []

        for contour in contours:
            area = cv2.contourArea(contour)
            if area < ANALYSIS_SETTINGS["min_contour_area"]:
                continue
            shape_info = self._classify_shape(contour)
            if shape_info:
                shape_counts[shape_info["type"]] += 1
                shape_details.append(shape_info)

        return dict(shape_counts), shape_details

    def _classify_shape(self, contour) -> dict:
        """
        Classify a single OpenCV contour into a named shape type.

        Decision tree (in priority order):
          - circularity > 0.8 and aspect ratio ≈ 1.0  → circle
          - circularity > 0.6 and aspect ratio ≠ 1.0  → ellipse
          - 3 vertices                                 → triangle
          - 4 vertices, aspect ratio ≈ 1              → square
          - 4 vertices, aspect ratio ≠ 1              → rectangle
          - 5 vertices                                 → pentagon
          - 6 vertices                                 → hexagon
          - > 6 vertices and low solidity              → star
          - very low solidity                          → spiky
          - many vertices and low circularity          → angular
          - moderate circularity and high solidity     → curved
          - fallback                                   → blob

        Args:
            contour: An OpenCV contour array as returned by findContours().

        Returns:
            dict | None: Shape descriptor with keys 'type', 'vertices', 'area',
                'circularity', 'aspect_ratio', 'solidity', 'confidence',
                'center', 'bounds'.  Returns None if the perimeter is zero.
        """
        perimeter = cv2.arcLength(contour, True)
        if perimeter == 0:
            return None

        epsilon = ANALYSIS_SETTINGS["shape_simplification_epsilon"] * perimeter
        approx = cv2.approxPolyDP(contour, epsilon, True)
        vertices = len(approx)

        area = cv2.contourArea(contour)
        # Circularity = 1.0 for a perfect circle; decreases for irregular shapes
        circularity = 4 * np.pi * area / (perimeter * perimeter) if perimeter > 0 else 0

        x, y, w, h = cv2.boundingRect(contour)
        aspect_ratio = float(w) / h if h > 0 else 1

        rect_area = w * h
        extent = area / rect_area if rect_area > 0 else 0

        hull = cv2.convexHull(contour)
        hull_area = cv2.contourArea(hull)
        # Solidity = ratio of contour area to its convex hull area (< 1 for concave shapes)
        solidity = area / hull_area if hull_area > 0 else 0

        shape_type = "irregular"
        confidence = 0.0

        if circularity > 0.8 and 0.9 < aspect_ratio < 1.1:
            shape_type, confidence = "circle", circularity
        elif circularity > 0.6 and (aspect_ratio < 0.9 or aspect_ratio > 1.1):
            shape_type, confidence = "ellipse", circularity
        elif vertices == 3:
            shape_type, confidence = "triangle", 0.9
        elif vertices == 4:
            shape_type = "square" if 0.9 < aspect_ratio < 1.1 else "rectangle"
            confidence = extent
        elif vertices == 5:
            shape_type, confidence = "pentagon", 0.85
        elif vertices == 6:
            shape_type, confidence = "hexagon", 0.85
        elif vertices > 6 and solidity < 0.7:
            shape_type, confidence = "star", 1 - solidity
        elif solidity < 0.5:
            shape_type, confidence = "spiky", 1 - solidity
        elif vertices > 8 and circularity < 0.5:
            shape_type, confidence = "angular", 1 - circularity
        elif circularity > 0.4 and solidity > 0.8:
            shape_type, confidence = "curved", solidity
        else:
            shape_type, confidence = "blob", solidity

        return {
            "type": shape_type,
            "vertices": vertices,
            "area": area,
            "circularity": round(circularity, 3),
            "aspect_ratio": round(aspect_ratio, 3),
            "solidity": round(solidity, 3),
            "confidence": round(confidence, 3),
            "center": (x + w // 2, y + h // 2),
            "bounds": (x, y, w, h),
        }

    def analyze_color_shape_combinations(
        self,
        image: np.ndarray,
        shape_details: list,
        mask: np.ndarray = None,
    ) -> dict:
        """
        Determine which colors appear inside each detected shape's bounding box.

        For every shape in ``shape_details``, crops the corresponding region
        from the image and runs ``analyze_colors()`` on it.  Results are
        accumulated and normalized per shape type.

        Args:
            image         (np.ndarray): Full BGR image.
            shape_details (list[dict]): Shape descriptors as returned by detect_shapes().
            mask          (np.ndarray | None): Foreground mask; cropped sub-mask
                is passed to analyze_colors() for each region.

        Returns:
            dict: Nested dict {shape_type: {color_name: normalized_percentage}}.
        """
        combinations = defaultdict(lambda: defaultdict(float))

        for shape in shape_details:
            x, y, w, h = shape["bounds"]
            region = image[
                max(0, y): min(image.shape[0], y + h),
                max(0, x): min(image.shape[1], x + w),
            ]
            if region.size == 0:
                continue

            region_mask = None
            if mask is not None:
                region_mask = mask[
                    max(0, y): min(mask.shape[0], y + h),
                    max(0, x): min(mask.shape[1], x + w),
                ]

            color_dist, _ = self.analyze_colors(region, region_mask)
            for color, percentage in color_dist.items():
                combinations[shape["type"]][color] += percentage

        # Normalize each shape's color percentages to sum to 100 %
        normalized = {}
        for shape, colors in combinations.items():
            total = sum(colors.values())
            if total > 0:
                normalized[shape] = {c: round(p / total * 100, 2) for c, p in colors.items()}

        return normalized

    def scan_image(self, image_path, name: str = None) -> dict:
        """
        Scan a single image file and return a full analysis result dict.

        Orchestrates the complete pipeline: background removal → color analysis
        → shape detection → color-shape correlation.

        Args:
            image_path: Path-like object or string pointing to the image file.
            name (str | None): Display name for the result row.  Defaults to
                the file stem (filename without extension).

        Returns:
            dict | None: Analysis result keyed by field name, or None if the
                image could not be loaded.  Key fields include 'name',
                'colors', 'shapes', 'dominant_color', 'dominant_shape',
                'color_shape_combinations', and 'foreground_coverage'.
        """
        self.current_image_path = Path(image_path)

        image = cv2.imread(str(image_path))
        if image is None:
            print(f"Error: Could not load image {image_path}")
            return None

        if name is None:
            name = Path(image_path).stem

        mask = self._create_background_mask(image)

        mask_coverage = np.sum(mask > 0) / (image.shape[0] * image.shape[1])
        if mask_coverage < 0.01:
            print(f"    Warning: Very low foreground detection ({mask_coverage * 100:.1f}%), using full image")
            mask = None

        color_dist, color_pct = self.analyze_colors(image, mask)
        shape_counts, shape_details = self.detect_shapes(image, mask)
        color_shape_combos = self.analyze_color_shape_combinations(image, shape_details, mask)

        total_shapes = sum(shape_counts.values())
        shape_percentages = (
            {s: round(c / total_shapes * 100, 2) for s, c in shape_counts.items()}
            if total_shapes > 0
            else {}
        )

        return {
            "name":                  name,
            "image_path":            str(image_path),
            "image_width":           image.shape[1],
            "image_height":          image.shape[0],
            "scan_timestamp":        datetime.now().isoformat(),
            "colors":                color_pct,
            "dominant_color":        list(color_pct.keys())[0] if color_pct else "unknown",
            "color_count":           len(color_pct),
            "shapes":                shape_percentages,
            "dominant_shape":        max(shape_counts, key=shape_counts.get) if shape_counts else "unknown",
            "shape_count":           total_shapes,
            "shape_details":         shape_details,
            "color_shape_combinations": color_shape_combos,
            "foreground_coverage":   round(mask_coverage * 100, 1) if mask is not None else 100.0,
        }

    def scan_directory(self, directory_path, extensions: list = None) -> list:
        """
        Scan every supported image file found in a directory.

        Uses a case-insensitive deduplication strategy so that files are not
        processed twice on case-insensitive file systems.  Results are returned
        in alphabetical order by filename.

        Args:
            directory_path: Path-like or string pointing to a directory.
            extensions (list | None): Allowed file extensions (include the
                leading dot, e.g. '.png').  Defaults to
                ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'].

        Returns:
            list[dict]: List of analysis result dicts, one per successfully
                scanned image.
        """
        if extensions is None:
            extensions = [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"]

        directory = Path(directory_path)
        results = []
        seen_files = set()
        image_files = []

        for ext in extensions:
            for f in directory.glob(f"*{ext}"):
                normalized = str(f).lower()
                if normalized not in seen_files:
                    seen_files.add(normalized)
                    image_files.append(f)
            for f in directory.glob(f"*{ext.upper()}"):
                normalized = str(f).lower()
                if normalized not in seen_files:
                    seen_files.add(normalized)
                    image_files.append(f)

        image_files = sorted(image_files, key=lambda x: x.name.lower())
        print(f"Found {len(image_files)} images to scan...")

        for i, image_path in enumerate(image_files):
            print(f"Scanning {i + 1}/{len(image_files)}: {image_path.name}")
            result = self.scan_image(image_path)
            if result:
                results.append(result)

        return results

    def export_to_csv(self, results: list, output_filename: str = "scan_results.csv") -> Path:
        """
        Export a list of scan results to a CSV file.

        Columns are generated dynamically based on all unique color and shape
        names found across all results, so the output adapts to whatever was
        detected in the dataset.  JSON blobs for the full distributions are
        appended as the last three columns.

        Args:
            results (list[dict]): Scan results as returned by scan_image().
            output_filename (str): Name of the CSV file to write inside
                ``self.output_dir``.

        Returns:
            Path: Absolute path to the written CSV file.
        """
        output_path = self.output_dir / output_filename

        # Collect all unique color and shape keys across the dataset
        all_colors = set()
        all_shapes = set()
        for r in results:
            all_colors.update(r["colors"].keys())
            all_shapes.update(r["shapes"].keys())

        all_colors = sorted(all_colors)
        all_shapes = sorted(all_shapes)

        fieldnames = [
            "name", "image_path", "image_width", "image_height", "scan_timestamp",
            "dominant_color", "color_count", "dominant_shape", "shape_count",
            "foreground_coverage",
        ]
        for color in all_colors:
            fieldnames.append(f"color_{color}_pct")
        for shape in all_shapes:
            fieldnames.append(f"shape_{shape}_pct")
        fieldnames += ["colors_json", "shapes_json", "color_shape_combos_json"]

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for result in results:
                row = {
                    "name":               result["name"],
                    "image_path":         result["image_path"],
                    "image_width":        result["image_width"],
                    "image_height":       result["image_height"],
                    "scan_timestamp":     result["scan_timestamp"],
                    "dominant_color":     result["dominant_color"],
                    "color_count":        result["color_count"],
                    "dominant_shape":     result["dominant_shape"],
                    "shape_count":        result["shape_count"],
                    "foreground_coverage": result.get("foreground_coverage", 100.0),
                }
                for color in all_colors:
                    row[f"color_{color}_pct"] = result["colors"].get(color, 0)
                for shape in all_shapes:
                    row[f"shape_{shape}_pct"] = result["shapes"].get(shape, 0)
                row["colors_json"]           = json.dumps(result["colors"])
                row["shapes_json"]           = json.dumps(result["shapes"])
                row["color_shape_combos_json"] = json.dumps(result["color_shape_combinations"])

                writer.writerow(row)

        print(f"Results exported to {output_path}")
        return output_path
