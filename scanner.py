"""
Image Scanner for Game Character/Monster Analysis
Extracts color distributions, shape patterns, and their combinations from images.
Outputs results to CSV for further analysis.
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
from config import COLOR_PALETTE, SHAPE_DEFINITIONS, ANALYSIS_SETTINGS

# Suppress KMeans convergence warnings
warnings.filterwarnings('ignore', category=UserWarning, module='sklearn')


class ImageScanner:
    def __init__(self, output_dir="output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.color_tree = self._build_color_tree()
        
    def _build_color_tree(self):
        """Build a lookup structure for fast color matching."""
        colors = []
        for name, data in COLOR_PALETTE.items():
            colors.append({
                "name": name,
                "rgb": np.array(data["rgb_center"]),
                "hex": data["hex"]
            })
        return colors
    
    def _match_color(self, rgb):
        """Find the closest named color for an RGB value."""
        rgb = np.array(rgb)
        min_dist = float('inf')
        closest = "unknown"
        for color in self.color_tree:
            dist = np.linalg.norm(rgb - color["rgb"])
            if dist < min_dist:
                min_dist = dist
                closest = color["name"]
        return closest
    
    def _detect_background_color(self, image):
        """
        Detect the background color by analyzing the edges of the image.
        Returns the dominant color found in the border regions.
        """
        h, w = image.shape[:2]
        border_size = max(5, min(h, w) // 20)  # 5% of smallest dimension, min 5px
        
        # Sample pixels from all four borders
        top = image[:border_size, :].reshape(-1, 3)
        bottom = image[-border_size:, :].reshape(-1, 3)
        left = image[:, :border_size].reshape(-1, 3)
        right = image[:, -border_size:].reshape(-1, 3)
        
        border_pixels = np.vstack([top, bottom, left, right])
        
        # Find the most common color in border (round to reduce noise)
        rounded = (border_pixels // 10) * 10
        pixel_tuples = [tuple(p) for p in rounded]
        most_common = Counter(pixel_tuples).most_common(1)
        
        if most_common:
            return np.array(most_common[0][0])
        return None
    
    def _create_background_mask(self, image):
        """
        Create a mask that excludes the background.
        Handles: transparent backgrounds, solid color backgrounds (black, white, etc.)
        """
        h, w = image.shape[:2]
        
        # Start with a full white mask (everything included)
        mask = np.ones((h, w), dtype=np.uint8) * 255
        
        # Method 1: Check for alpha channel (transparency)
        # Note: OpenCV loads as BGR or BGRA
        original_image = cv2.imread(str(self.current_image_path), cv2.IMREAD_UNCHANGED)
        if original_image is not None and len(original_image.shape) == 3 and original_image.shape[2] == 4:
            # Has alpha channel - use it directly
            alpha = original_image[:, :, 3]
            mask = np.where(alpha > 10, 255, 0).astype(np.uint8)
            
            # Check if alpha mask is meaningful (not all opaque)
            if np.sum(mask == 0) > (h * w * 0.01):  # At least 1% transparent
                return mask
        
        # Method 2: Detect and remove solid background color
        bg_color = self._detect_background_color(image)
        
        if bg_color is not None:
            # Calculate color distance from background for each pixel
            diff = np.sqrt(np.sum((image.astype(np.float32) - bg_color.astype(np.float32)) ** 2, axis=2))
            
            # Threshold: pixels too similar to background are masked out
            # Use adaptive threshold based on background color brightness
            bg_brightness = np.mean(bg_color)
            
            if bg_brightness < 30:  # Dark/black background
                threshold = 50  # More lenient for dark backgrounds
            elif bg_brightness > 225:  # Light/white background
                threshold = 50  # More lenient for light backgrounds
            else:
                threshold = 30  # Stricter for mid-tone backgrounds
            
            mask = np.where(diff > threshold, 255, 0).astype(np.uint8)
        
        # Method 3: If mask removes too much, use edge-based detection
        mask_coverage = np.sum(mask > 0) / (h * w)
        
        if mask_coverage < 0.05:  # Less than 5% of image is foreground
            # Fall back to edge detection + morphology
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # Use Otsu's thresholding
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            # Determine if we should invert (dark object on light bg or vice versa)
            if np.mean(gray[:10, :]) > np.mean(gray[h//3:2*h//3, w//3:2*w//3]):
                thresh = cv2.bitwise_not(thresh)
            
            # Clean up with morphology
            kernel = np.ones((5, 5), np.uint8)
            thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
            thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
            
            # Find largest contour (main subject)
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                mask = np.zeros((h, w), dtype=np.uint8)
                largest = max(contours, key=cv2.contourArea)
                cv2.drawContours(mask, [largest], -1, 255, -1)
                
                # Dilate slightly to include edges
                mask = cv2.dilate(mask, kernel, iterations=2)
        
        # Final cleanup
        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        
        return mask
    
    def analyze_colors(self, image, mask=None):
        """Extract color distribution from an image."""
        if mask is not None:
            # Only analyze pixels where mask is white (foreground)
            foreground_pixels = image[mask > 128]
            pixels = foreground_pixels
        else:
            pixels = image.reshape(-1, 3)
        
        if len(pixels) == 0:
            return {}, {}
        
        # Filter out near-black and near-white pixels that might be background remnants
        # Calculate brightness for each pixel
        brightness = np.mean(pixels, axis=1)
        
        # Keep pixels that aren't too dark or too light (unless they're colored)
        color_variance = np.var(pixels, axis=1)
        
        # Keep if: not too dark, not too light, OR has color variation
        keep_mask = ((brightness > 15) & (brightness < 240)) | (color_variance > 100)
        filtered_pixels = pixels[keep_mask]
        
        if len(filtered_pixels) < 100:
            filtered_pixels = pixels  # Fall back if too many filtered
        
        sample_size = max(1000, int(len(filtered_pixels) * ANALYSIS_SETTINGS["color_sample_rate"]))
        if len(filtered_pixels) > sample_size:
            indices = np.random.choice(len(filtered_pixels), sample_size, replace=False)
            sample = filtered_pixels[indices]
        else:
            sample = filtered_pixels
        
        # Determine optimal number of clusters based on actual color diversity
        unique_colors = len(np.unique(sample.round(-1), axis=0))
        n_clusters = min(
            ANALYSIS_SETTINGS["dominant_colors_count"],
            max(2, unique_colors // 5, len(sample) // 50)
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
                color_name = self._match_color(rgb[::-1])  # BGR to RGB
                percentage = (label_counts[i] / total) * 100
                
                if color_name in color_distribution:
                    color_distribution[color_name] += percentage
                else:
                    color_distribution[color_name] = percentage
            
            color_distribution = dict(sorted(color_distribution.items(), key=lambda x: x[1], reverse=True))
            color_percentages = {name: round(pct, 2) for name, pct in color_distribution.items()}
            
            return color_distribution, color_percentages
            
        except Exception as e:
            print(f"    Warning: Color analysis error - {e}")
            return {}, {}
    
    def detect_shapes(self, image, mask=None):
        """Detect shapes in an image using contour analysis."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, *ANALYSIS_SETTINGS["edge_detection_thresholds"])
        
        if mask is not None:
            edges = cv2.bitwise_and(edges, edges, mask=mask)
        
        contours, hierarchy = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        
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
    
    def _classify_shape(self, contour):
        """Classify a contour into a shape type."""
        perimeter = cv2.arcLength(contour, True)
        if perimeter == 0:
            return None
            
        epsilon = ANALYSIS_SETTINGS["shape_simplification_epsilon"] * perimeter
        approx = cv2.approxPolyDP(contour, epsilon, True)
        vertices = len(approx)
        
        area = cv2.contourArea(contour)
        circularity = 4 * np.pi * area / (perimeter * perimeter) if perimeter > 0 else 0
        
        x, y, w, h = cv2.boundingRect(contour)
        aspect_ratio = float(w) / h if h > 0 else 1
        
        rect_area = w * h
        extent = area / rect_area if rect_area > 0 else 0
        
        hull = cv2.convexHull(contour)
        hull_area = cv2.contourArea(hull)
        solidity = area / hull_area if hull_area > 0 else 0
        
        shape_type = "irregular"
        confidence = 0.0
        
        if circularity > 0.8 and 0.9 < aspect_ratio < 1.1:
            shape_type = "circle"
            confidence = circularity
        elif circularity > 0.6 and (aspect_ratio < 0.9 or aspect_ratio > 1.1):
            shape_type = "ellipse"
            confidence = circularity
        elif vertices == 3:
            shape_type = "triangle"
            confidence = 0.9
        elif vertices == 4:
            if 0.9 < aspect_ratio < 1.1:
                shape_type = "square"
            else:
                shape_type = "rectangle"
            confidence = extent
        elif vertices == 5:
            shape_type = "pentagon"
            confidence = 0.85
        elif vertices == 6:
            shape_type = "hexagon"
            confidence = 0.85
        elif vertices > 6 and solidity < 0.7:
            shape_type = "star"
            confidence = 1 - solidity
        elif solidity < 0.5:
            shape_type = "spiky"
            confidence = 1 - solidity
        elif vertices > 8 and circularity < 0.5:
            shape_type = "angular"
            confidence = 1 - circularity
        elif circularity > 0.4 and solidity > 0.8:
            shape_type = "curved"
            confidence = solidity
        else:
            shape_type = "blob"
            confidence = solidity
        
        return {
            "type": shape_type,
            "vertices": vertices,
            "area": area,
            "circularity": round(circularity, 3),
            "aspect_ratio": round(aspect_ratio, 3),
            "solidity": round(solidity, 3),
            "confidence": round(confidence, 3),
            "center": (x + w // 2, y + h // 2),
            "bounds": (x, y, w, h)
        }
    
    def analyze_color_shape_combinations(self, image, shape_details, mask=None):
        """Analyze which colors appear with which shapes."""
        combinations = defaultdict(lambda: defaultdict(float))
        
        for shape in shape_details:
            x, y, w, h = shape["bounds"]
            region = image[max(0, y):min(image.shape[0], y+h), max(0, x):min(image.shape[1], x+w)]
            
            if region.size == 0:
                continue
            
            region_mask = None
            if mask is not None:
                region_mask = mask[max(0, y):min(mask.shape[0], y+h), max(0, x):min(mask.shape[1], x+w)]
            
            color_dist, _ = self.analyze_colors(region, region_mask)
            
            for color, percentage in color_dist.items():
                combinations[shape["type"]][color] += percentage
        
        normalized = {}
        for shape, colors in combinations.items():
            total = sum(colors.values())
            if total > 0:
                normalized[shape] = {c: round(p/total * 100, 2) for c, p in colors.items()}
        
        return normalized
    
    def scan_image(self, image_path, name=None):
        """Scan a single image and return analysis results."""
        self.current_image_path = Path(image_path)  # Store for alpha detection
        
        image = cv2.imread(str(image_path))
        if image is None:
            print(f"Error: Could not load image {image_path}")
            return None
        
        if name is None:
            name = Path(image_path).stem
        
        # Create background mask
        mask = self._create_background_mask(image)
        
        # Check mask quality
        mask_coverage = np.sum(mask > 0) / (image.shape[0] * image.shape[1])
        if mask_coverage < 0.01:
            print(f"    Warning: Very low foreground detection ({mask_coverage*100:.1f}%), using full image")
            mask = None
        
        color_dist, color_pct = self.analyze_colors(image, mask)
        shape_counts, shape_details = self.detect_shapes(image, mask)
        color_shape_combos = self.analyze_color_shape_combinations(image, shape_details, mask)
        
        total_shapes = sum(shape_counts.values())
        shape_percentages = {s: round(c/total_shapes * 100, 2) for s, c in shape_counts.items()} if total_shapes > 0 else {}
        
        result = {
            "name": name,
            "image_path": str(image_path),
            "image_width": image.shape[1],
            "image_height": image.shape[0],
            "scan_timestamp": datetime.now().isoformat(),
            "colors": color_pct,
            "dominant_color": list(color_pct.keys())[0] if color_pct else "unknown",
            "color_count": len(color_pct),
            "shapes": shape_percentages,
            "dominant_shape": max(shape_counts, key=shape_counts.get) if shape_counts else "unknown",
            "shape_count": total_shapes,
            "shape_details": shape_details,
            "color_shape_combinations": color_shape_combos,
            "foreground_coverage": round(mask_coverage * 100, 1) if mask is not None else 100.0,
        }
        
        return result
    
    def scan_directory(self, directory_path, extensions=None):
        """Scan all images in a directory."""
        if extensions is None:
            extensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp']
        
        directory = Path(directory_path)
        results = []
        
        # Use a set to avoid duplicates from case-insensitive file systems
        seen_files = set()
        image_files = []
        
        for ext in extensions:
            # Only search lowercase to avoid duplicates
            for f in directory.glob(f"*{ext}"):
                # Normalize path to handle case-insensitivity
                normalized = str(f).lower()
                if normalized not in seen_files:
                    seen_files.add(normalized)
                    image_files.append(f)
            
            # Also check uppercase extension (but still track by lowercase path)
            for f in directory.glob(f"*{ext.upper()}"):
                normalized = str(f).lower()
                if normalized not in seen_files:
                    seen_files.add(normalized)
                    image_files.append(f)
        
        # Sort for consistent ordering
        image_files = sorted(image_files, key=lambda x: x.name.lower())
        
        print(f"Found {len(image_files)} images to scan...")
        
        for i, image_path in enumerate(image_files):
            print(f"Scanning {i+1}/{len(image_files)}: {image_path.name}")
            result = self.scan_image(image_path)
            if result:
                results.append(result)
        
        return results
    
    def export_to_csv(self, results, output_filename="scan_results.csv"):
        """Export scan results to CSV."""
        output_path = self.output_dir / output_filename
        
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
        
        fieldnames.append("colors_json")
        fieldnames.append("shapes_json")
        fieldnames.append("color_shape_combos_json")
        
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for result in results:
                row = {
                    "name": result["name"],
                    "image_path": result["image_path"],
                    "image_width": result["image_width"],
                    "image_height": result["image_height"],
                    "scan_timestamp": result["scan_timestamp"],
                    "dominant_color": result["dominant_color"],
                    "color_count": result["color_count"],
                    "dominant_shape": result["dominant_shape"],
                    "shape_count": result["shape_count"],
                    "foreground_coverage": result.get("foreground_coverage", 100.0),
                }
                
                for color in all_colors:
                    row[f"color_{color}_pct"] = result["colors"].get(color, 0)
                
                for shape in all_shapes:
                    row[f"shape_{shape}_pct"] = result["shapes"].get(shape, 0)
                
                row["colors_json"] = json.dumps(result["colors"])
                row["shapes_json"] = json.dumps(result["shapes"])
                row["color_shape_combos_json"] = json.dumps(result["color_shape_combinations"])
                
                writer.writerow(row)
        
        print(f"Results exported to {output_path}")
        return output_path


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Scan images for color and shape analysis")
    parser.add_argument("input", help="Image file or directory to scan")
    parser.add_argument("-o", "--output", default="output", help="Output directory")
    parser.add_argument("-n", "--name", help="Name for single image scan")
    parser.add_argument("--csv", default="scan_results.csv", help="Output CSV filename")
    
    args = parser.parse_args()
    
    scanner = ImageScanner(output_dir=args.output)
    
    input_path = Path(args.input)
    
    if input_path.is_file():
        result = scanner.scan_image(input_path, name=args.name)
        if result:
            scanner.export_to_csv([result], args.csv)
    elif input_path.is_dir():
        results = scanner.scan_directory(input_path)
        if results:
            scanner.export_to_csv(results, args.csv)
    else:
        print(f"Error: {args.input} is not a valid file or directory")


if __name__ == "__main__":
    main()
