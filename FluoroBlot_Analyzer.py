"""Integrated WB, confocal, Oil Red O and BODIPY image-analysis desktop app."""

import csv
from pathlib import Path
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import numpy as np
from PIL import Image, ImageDraw, ImageTk


def read_gray(path):
    with Image.open(path) as image:
        raw = np.asarray(image)
    if raw.ndim == 3:
        raw = np.dot(raw[..., :3].astype(float), [0.299, 0.587, 0.114])
    else:
        raw = raw.astype(float)
    minimum, maximum = float(np.min(raw)), float(np.max(raw))
    if maximum <= minimum:
        raise ValueError("The image contains only one grayscale value; band analysis is not possible.")
    return np.clip(np.rint((raw - minimum) * 255 / (maximum - minimum)), 0, 255).astype(np.uint8)


def lane_centers(gray, count, y0, y1):
    h, w = gray.shape
    y0, y1 = max(0, y0), min(h, y1)
    score = (255.0 - gray[y0:y1].astype(float)).sum(axis=0)
    smooth = np.convolve(score, np.ones(9) / 9, mode="same")
    pitch = w / count
    centers = []
    for index in range(count):
        expected = (index + 0.5) * pitch
        lower = max(0, round(expected - pitch * 0.30))
        upper = min(w, round(expected + pitch * 0.30) + 1)
        centers.append(int(lower + np.argmax(smooth[lower:upper])))
    return centers


def lane_area(gray, center, half_width, y0, y1, baseline_percentile):
    height, width = gray.shape
    x0, x1 = max(0, center - half_width), min(width, center + half_width + 1)
    y0, y1 = max(0, y0), min(height, y1)
    if x1 <= x0 or y1 - y0 < 3:
        raise ValueError("The analysis region is too small.")
    lane = gray[y0:y1, x0:x1].astype(float)
    optical_density = np.log10(255.0 / (lane + 1.0))
    profile = optical_density.sum(axis=1)
    baseline = float(np.percentile(profile, baseline_percentile))
    area = float(np.maximum(profile - baseline, 0).sum())
    return area, (x0, y0, x1, y1)


def excel_text(rows, areas_only=False):
    """Tab/newline-separated cells paste into separate Excel columns/rows."""
    if areas_only:
        return "\n".join(f"{row[-1]:.3f}" for row in rows)
    header = "Lane\tCenter X\tROI_X0\tROI_Y0\tROI_X1\tROI_Y1\tOptical-density peak area"
    return header + "\n" + "\n".join("\t".join(
        [str(value) for value in row[:-1]] + [f"{row[-1]:.3f}"]
    ) for row in rows)


CONFOCAL_CHANNELS = {
    "Red (1/3)": (0, "1/3 Red"),
    "Green (2/3)": (1, "2/3 Green"),
    "Blue (3/3)": (2, "3/3 Blue"),
}

CONFOCAL_HEADERS = [
    "File name", "Width (px)", "Height (px)", "Channel", "Threshold low", "Threshold high",
    "Positive pixels", "Area", "Area unit", "Mean", "Min", "Max", "IntDen",
    "RawIntDen", "Area Fraction(%)",
]


def analyze_confocal(path, channel_name, threshold_low, threshold_high):
    """Replicate ImageJ RGB Stack + channel + threshold-limited Measure."""
    with Image.open(path) as image:
        tags = getattr(image, "tag_v2", {})
        x_resolution = float(tags.get(282, 1.0))
        y_resolution = float(tags.get(283, 1.0))
        resolution_unit = int(tags.get(296, 1))
        raw = np.asarray(image)

    if raw.ndim != 3 or raw.shape[2] < 3:
        raise ValueError("Confocal analysis requires an RGB image.")
    if not 0 <= threshold_low <= threshold_high <= 255:
        raise ValueError("The threshold must satisfy 0 <= low <= high <= 255.")

    channel_index, imagej_channel = CONFOCAL_CHANNELS[channel_name]
    channel = raw[..., channel_index].astype(np.uint8)
    mask = (channel >= threshold_low) & (channel <= threshold_high)
    values = channel[mask].astype(np.float64)
    if values.size == 0:
        raise ValueError("No pixels fall within the selected channel and threshold range.")

    if resolution_unit == 2 and x_resolution > 0 and y_resolution > 0:
        area_scale, area_unit = x_resolution * y_resolution, "in²"
    elif resolution_unit == 3 and x_resolution > 0 and y_resolution > 0:
        area_scale, area_unit = x_resolution * y_resolution, "cm²"
    else:
        area_scale, area_unit = 1.0, "px²"

    selected_pixels = int(mask.sum())
    raw_intden = int(values.sum())
    overlay = np.repeat(channel[..., None], 3, axis=2)
    overlay[mask] = (255, 0, 0)
    height, width = channel.shape
    result = {
        "path": str(path),
        "file": Path(path).name,
        "width": width,
        "height": height,
        "channel": imagej_channel,
        "threshold_low": threshold_low,
        "threshold_high": threshold_high,
        "selected_pixels": selected_pixels,
        "area": selected_pixels / area_scale,
        "area_unit": area_unit,
        "mean": float(values.mean()),
        "min": int(values.min()),
        "max": int(values.max()),
        "intden": raw_intden / area_scale,
        "raw_intden": raw_intden,
        "area_fraction": selected_pixels / channel.size * 100.0,
        "overlay": Image.fromarray(overlay, mode="RGB"),
    }
    return result


def confocal_excel_text(results):
    lines = ["\t".join(CONFOCAL_HEADERS)]
    for result in results:
        lines.append("\t".join([
            result["file"], str(result["width"]), str(result["height"]), result["channel"],
            str(result["threshold_low"]), str(result["threshold_high"]),
            str(result["selected_pixels"]), f'{result["area"]:.3f}', result["area_unit"],
            f'{result["mean"]:.3f}', str(result["min"]), str(result["max"]),
            f'{result["intden"]:.3f}', str(result["raw_intden"]),
            f'{result["area_fraction"]:.3f}',
        ]))
    return "\n".join(lines)


OIL_RED_HEADERS = [
    "File name", "Width (px)", "Height (px)", "Channel", "Threshold low", "Threshold high",
    "Area", "Mean", "Min", "Max", "IntDen", "Area Fraction(%)",
]


def oil_red_excel_text(results):
    lines = ["\t".join(OIL_RED_HEADERS)]
    for result in results:
        lines.append("\t".join([
            result["file"], str(result["width"]), str(result["height"]), result["channel"],
            str(result["threshold_low"]), str(result["threshold_high"]),
            str(result["selected_pixels"]), f'{result["mean"]:.3f}',
            str(result["min"]), str(result["max"]), str(result["raw_intden"]),
            f'{result["area_fraction"]:.3f}',
        ]))
    return "\n".join(lines)


BODIPY_HEADERS = [
    "File name", "Punctum ID", "Punctum area (px²)", "Punctum area (µm²)", "Centroid X (px)", "Centroid Y (px)",
    "Bounding box (X0,Y0,X1,Y1)", "Mean red-dominance score", "Puncta count", "Total puncta area (px²)",
    "Total puncta area (µm²)", "Image area fraction (%)", "Red threshold", "Minimum punctum area (px²)", "Pixel size (µm/px)",
]


def _connected_components(mask, minimum_area):
    """Return 8-connected components with at least minimum_area pixels."""
    working = mask.copy()
    components = []
    height, width = working.shape
    for start_y, start_x in np.argwhere(working):
        if not working[start_y, start_x]:
            continue
        working[start_y, start_x] = False
        stack = [(int(start_y), int(start_x))]
        pixels = []
        while stack:
            y, x = stack.pop()
            pixels.append((y, x))
            for neighbor_y in range(max(0, y - 1), min(height, y + 2)):
                for neighbor_x in range(max(0, x - 1), min(width, x + 2)):
                    if working[neighbor_y, neighbor_x]:
                        working[neighbor_y, neighbor_x] = False
                        stack.append((neighbor_y, neighbor_x))
        if len(pixels) >= minimum_area:
            components.append(pixels)
    components.sort(key=len, reverse=True)
    return components


def analyze_bodipy(path, red_threshold=30, minimum_area=5, micron_per_pixel=0.0):
    """Measure individual red-dominant fluorescent objects and their combined area."""
    if not 0 <= red_threshold <= 255:
        raise ValueError("The red threshold must be between 0 and 255.")
    if minimum_area < 1:
        raise ValueError("The minimum punctum area must be at least 1 px².")
    if micron_per_pixel < 0:
        raise ValueError("Pixel size cannot be negative; enter 0 if unknown.")

    with Image.open(path) as image:
        rgb_image = image.convert("RGB")
        raw = np.asarray(rgb_image).astype(np.int16)
    height, width = raw.shape[:2]
    red_score = raw[..., 0] - np.maximum(raw[..., 1], raw[..., 2])
    initial_mask = red_score >= red_threshold
    components = _connected_components(initial_mask, minimum_area)

    kept_mask = np.zeros((height, width), dtype=bool)
    spots = []
    calibrated = micron_per_pixel > 0
    area_factor = micron_per_pixel ** 2 if calibrated else 0.0
    for spot_id, pixels in enumerate(components, start=1):
        ys = np.fromiter((pixel[0] for pixel in pixels), dtype=np.int32)
        xs = np.fromiter((pixel[1] for pixel in pixels), dtype=np.int32)
        kept_mask[ys, xs] = True
        area_pixels = int(len(pixels))
        spots.append({
            "spot_id": spot_id,
            "area_pixels": area_pixels,
            "area_um2": area_pixels * area_factor if calibrated else None,
            "centroid_x": float(xs.mean()),
            "centroid_y": float(ys.mean()),
            "bbox": (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1),
            "mean_red_score": float(red_score[ys, xs].mean()),
        })

    total_pixels = int(kept_mask.sum())
    total_um2 = total_pixels * area_factor if calibrated else None
    preview = np.asarray(rgb_image).copy()
    padded = np.pad(kept_mask, 1, constant_values=False)
    interior = kept_mask.copy()
    for dy in range(3):
        for dx in range(3):
            interior &= padded[dy:dy + height, dx:dx + width]
    boundary = kept_mask & ~interior
    preview[boundary] = (255, 255, 0)
    overlay = Image.fromarray(preview, mode="RGB")
    pen = ImageDraw.Draw(overlay)
    for spot in spots:
        x0, y0, x1, y1 = spot["bbox"]
        pen.rectangle((x0, y0, x1 - 1, y1 - 1), outline=(255, 215, 0), width=1)
        pen.text((x0 + 1, max(0, y0 - 10)), str(spot["spot_id"]), fill=(255, 255, 0),
                 stroke_width=1, stroke_fill=(0, 0, 0))

    return {
        "path": str(path), "file": Path(path).name, "width": width, "height": height,
        "red_threshold": red_threshold, "minimum_area": minimum_area,
        "micron_per_pixel": micron_per_pixel, "spots": spots, "spot_count": len(spots),
        "total_pixels": total_pixels, "total_um2": total_um2,
        "area_fraction": total_pixels / (width * height) * 100.0,
        "overlay": overlay,
    }


def bodipy_excel_text(results, selected_rows=None):
    rows = selected_rows if selected_rows is not None else [
        (result, spot) for result in results for spot in result["spots"]
    ]
    lines = ["\t".join(BODIPY_HEADERS)]
    for result, spot in rows:
        lines.append("\t".join([
            result["file"], str(spot["spot_id"]), str(spot["area_pixels"]),
            "" if spot["area_um2"] is None else f'{spot["area_um2"]:.3f}',
            f'{spot["centroid_x"]:.2f}', f'{spot["centroid_y"]:.2f}',
            ",".join(str(value) for value in spot["bbox"]), f'{spot["mean_red_score"]:.3f}',
            str(result["spot_count"]), str(result["total_pixels"]),
            "" if result["total_um2"] is None else f'{result["total_um2"]:.3f}',
            f'{result["area_fraction"]:.3f}', str(result["red_threshold"]),
            str(result["minimum_area"]), f'{result["micron_per_pixel"]:.6g}',
        ]))
    return "\n".join(lines)


class WBApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Image Quantification · WB / Confocal / Oil Red O / BODIPY")
        self.root.geometry("1380x820")
        self.file = None
        self.gray = None
        self.centers = []
        self.photo = None
        self.scale = 1
        self.dragging = None
        self.mode = tk.StringVar(value="wb")
        mode_bar = ttk.Frame(root, padding=(12, 10, 12, 4))
        mode_bar.pack(fill="x")
        ttk.Label(mode_bar, text="Analysis mode:").pack(side="left")
        ttk.Radiobutton(mode_bar, text="Western blot", value="wb", variable=self.mode,
                        command=self.switch_mode).pack(side="left", padx=5)
        ttk.Radiobutton(mode_bar, text="Confocal fluorescence", value="confocal", variable=self.mode,
                        command=self.switch_mode).pack(side="left", padx=5)
        ttk.Radiobutton(mode_bar, text="Oil Red O staining", value="oil_red", variable=self.mode,
                        command=self.switch_mode).pack(side="left", padx=5)
        ttk.Radiobutton(mode_bar, text="BODIPY puncta", value="bodipy", variable=self.mode,
                        command=self.switch_mode).pack(side="left", padx=5)
        controls = ttk.Frame(root, padding=10)
        controls.pack(fill="x")
        ttk.Button(controls, text="Open WB image", command=self.open_file).pack(side="left", padx=4)
        ttk.Label(controls, text="Lanes").pack(side="left", padx=(15, 2))
        self.count = tk.IntVar(value=8)
        ttk.Spinbox(controls, from_=6, to=15, width=4, textvariable=self.count).pack(side="left")
        ttk.Button(controls, text="Redetect", command=self.reset_lanes).pack(side="left", padx=6)
        ttk.Label(controls, text="ROI half-width").pack(side="left", padx=(12, 2))
        self.half_width = tk.IntVar(value=25)
        ttk.Spinbox(controls, from_=4, to=200, width=5, textvariable=self.half_width, command=self.refresh).pack(side="left")
        ttk.Label(controls, text="Start row").pack(side="left", padx=(12, 2))
        self.y_start = tk.IntVar(value=0)
        ttk.Spinbox(controls, from_=0, to=10000, width=5, textvariable=self.y_start, command=self.refresh).pack(side="left")
        ttk.Label(controls, text="End row").pack(side="left", padx=(12, 2))
        self.y_end = tk.IntVar(value=65)
        ttk.Spinbox(controls, from_=1, to=10000, width=5, textvariable=self.y_end, command=self.refresh).pack(side="left")
        ttk.Label(controls, text="Baseline percentile").pack(side="left", padx=(12, 2))
        self.baseline = tk.IntVar(value=15)
        ttk.Spinbox(controls, from_=0, to=50, width=4, textvariable=self.baseline, command=self.refresh).pack(side="left")

        actions = ttk.Frame(root, padding=(10, 0, 10, 8))
        actions.pack(fill="x")
        ttk.Button(actions, text="Update analysis", command=self.refresh).pack(side="left", padx=4)
        ttk.Button(actions, text="Export CSV + annotated image", command=self.export).pack(side="left", padx=4)
        ttk.Button(actions, text="Copy area column", command=self.copy_areas).pack(side="left", padx=4)
        ttk.Button(actions, text="Copy full table", command=self.copy_all).pack(side="left", padx=4)
        self.status = tk.StringVar(value="Open a WB image. Click or drag a colored box to adjust the lane center.")
        ttk.Label(actions, textvariable=self.status).pack(side="left", padx=16)

        self.canvas = tk.Canvas(root, bg="#eeeeee", height=350, highlightthickness=1)
        self.canvas.pack(fill="both", expand=True, padx=12, pady=5)
        self.canvas.bind("<Button-1>", self.begin_drag)
        self.canvas.bind("<B1-Motion>", self.move_drag)
        self.canvas.bind("<ButtonRelease-1>", self.stop_drag)

        columns = ("lane", "x_center", "roi", "area")
        self.table = ttk.Treeview(root, columns=columns, show="headings", height=10, selectmode="extended")
        for name, label, width in (("lane", "Lane", 75), ("x_center", "Center X", 90),
                                   ("roi", "Image ROI (X0,Y0,X1,Y1)", 290),
                                   ("area", "Optical-density peak area (preview algorithm)", 200)):
            self.table.heading(name, text=label)
            self.table.column(name, width=width, anchor="center")
        self.table.pack(fill="x", padx=12, pady=(4, 12))
        self.table.bind("<Control-c>", self.copy_selected)
        self.table.bind("<Control-C>", self.copy_selected)
        self.table.bind("<Control-a>", self.select_all)
        self.table.bind("<Control-A>", self.select_all)
        for var in (self.half_width, self.y_start, self.y_end, self.baseline):
            var.trace_add("write", lambda *_: self.refresh())

        self.wb_widgets = [controls, actions, self.canvas, self.table]
        self.confocal_results = []
        self.confocal_paths = []
        self.confocal_photo = None
        self.build_confocal_ui()
        self.oil_red_results = []
        self.oil_red_paths = []
        self.oil_red_photo = None
        self.build_oil_red_ui()
        self.bodipy_results = []
        self.bodipy_paths = []
        self.bodipy_photo = None
        self.bodipy_rows = []
        self.build_bodipy_ui()
        self.switch_mode()

    def build_confocal_ui(self):
        controls = ttk.Frame(self.root, padding=10)
        ttk.Button(controls, text="Open confocal images", command=self.open_confocal_files).pack(side="left", padx=4)
        ttk.Label(controls, text="Channel").pack(side="left", padx=(14, 3))
        self.confocal_channel = tk.StringVar(value="Green (2/3)")
        channel_box = ttk.Combobox(controls, state="readonly", width=14,
                                   values=list(CONFOCAL_CHANNELS), textvariable=self.confocal_channel)
        channel_box.pack(side="left")
        ttk.Label(controls, text="Threshold").pack(side="left", padx=(14, 3))
        self.confocal_low = tk.IntVar(value=45)
        self.confocal_high = tk.IntVar(value=255)
        ttk.Spinbox(controls, from_=0, to=255, width=5, textvariable=self.confocal_low).pack(side="left")
        ttk.Label(controls, text="–").pack(side="left", padx=3)
        ttk.Spinbox(controls, from_=0, to=255, width=5, textvariable=self.confocal_high).pack(side="left")
        ttk.Button(controls, text="Reanalyze with current settings", command=self.reanalyze_confocal).pack(side="left", padx=8)
        ttk.Button(controls, text="Clear", command=self.clear_confocal).pack(side="left", padx=4)

        actions = ttk.Frame(self.root, padding=(10, 0, 10, 8))
        ttk.Button(actions, text="Copy selected rows", command=self.copy_confocal_selected).pack(side="left", padx=4)
        ttk.Button(actions, text="Copy full table", command=self.copy_confocal_all).pack(side="left", padx=4)
        ttk.Button(actions, text="Export CSV", command=self.export_confocal).pack(side="left", padx=4)
        ttk.Button(actions, text="Save threshold preview", command=self.save_confocal_preview).pack(side="left", padx=4)
        self.confocal_status = tk.StringVar(value="Import RGB TIFF images to analyze Green with Threshold 45–255.")
        ttk.Label(actions, textvariable=self.confocal_status).pack(side="left", padx=16)

        self.confocal_canvas = tk.Canvas(self.root, bg="#111111", height=380, highlightthickness=1)

        table_frame = ttk.Frame(self.root, padding=(12, 4, 12, 12))
        columns = ("file", "size", "channel", "threshold", "pixels", "area", "mean",
                   "min", "max", "intden", "rawintden", "fraction")
        self.confocal_table = ttk.Treeview(table_frame, columns=columns, show="headings",
                                           height=9, selectmode="extended")
        definitions = (
            ("file", "File name", 260), ("size", "Dimensions", 90), ("channel", "Channel", 90),
            ("threshold", "Threshold", 85), ("pixels", "Positive pixels", 100),
            ("area", "Area", 100), ("mean", "Mean", 85), ("min", "Min", 65),
            ("max", "Max", 65), ("intden", "IntDen", 105),
            ("rawintden", "RawIntDen", 110), ("fraction", "Area Fraction", 105),
        )
        for name, label, width in definitions:
            self.confocal_table.heading(name, text=label)
            self.confocal_table.column(name, width=width, minwidth=55, anchor="center")
        x_scroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.confocal_table.xview)
        y_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.confocal_table.yview)
        self.confocal_table.configure(xscrollcommand=x_scroll.set, yscrollcommand=y_scroll.set)
        self.confocal_table.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        self.confocal_table.bind("<<TreeviewSelect>>", self.show_selected_confocal_preview)
        self.confocal_table.bind("<Control-c>", self.copy_confocal_selected)
        self.confocal_table.bind("<Control-C>", self.copy_confocal_selected)
        self.confocal_table.bind("<Control-a>", self.select_all_confocal)
        self.confocal_table.bind("<Control-A>", self.select_all_confocal)

        self.confocal_widgets = [controls, actions, self.confocal_canvas, table_frame]

    def build_oil_red_ui(self):
        controls = ttk.Frame(self.root, padding=10)
        ttk.Button(controls, text="Open Oil Red O images", command=self.open_oil_red_files).pack(side="left", padx=4)
        ttk.Label(controls, text="Channel").pack(side="left", padx=(14, 3))
        self.oil_red_channel = tk.StringVar(value="Green (2/3)")
        channel_box = ttk.Combobox(controls, state="readonly", width=14,
                                   values=list(CONFOCAL_CHANNELS), textvariable=self.oil_red_channel)
        channel_box.pack(side="left")
        ttk.Label(controls, text="Threshold").pack(side="left", padx=(14, 3))
        self.oil_red_low = tk.IntVar(value=0)
        self.oil_red_high = tk.IntVar(value=150)
        ttk.Spinbox(controls, from_=0, to=255, width=5, textvariable=self.oil_red_low).pack(side="left")
        ttk.Label(controls, text="–").pack(side="left", padx=3)
        ttk.Spinbox(controls, from_=0, to=255, width=5, textvariable=self.oil_red_high).pack(side="left")
        ttk.Button(controls, text="Reanalyze with current settings", command=self.reanalyze_oil_red).pack(side="left", padx=8)
        ttk.Button(controls, text="Clear", command=self.clear_oil_red).pack(side="left", padx=4)

        actions = ttk.Frame(self.root, padding=(10, 0, 10, 8))
        ttk.Button(actions, text="Copy selected rows", command=self.copy_oil_red_selected).pack(side="left", padx=4)
        ttk.Button(actions, text="Copy full table", command=self.copy_oil_red_all).pack(side="left", padx=4)
        ttk.Button(actions, text="Export CSV", command=self.export_oil_red).pack(side="left", padx=4)
        ttk.Button(actions, text="Save threshold preview", command=self.save_oil_red_preview).pack(side="left", padx=4)
        self.oil_red_status = tk.StringVar(
            value="Import RGB Oil Red O images to analyze Green with Threshold 0–150, matching the recorded workflow."
        )
        ttk.Label(actions, textvariable=self.oil_red_status).pack(side="left", padx=16)

        self.oil_red_canvas = tk.Canvas(self.root, bg="#eeeeee", height=380, highlightthickness=1)

        table_frame = ttk.Frame(self.root, padding=(12, 4, 12, 12))
        columns = ("file", "size", "channel", "threshold", "area", "mean", "min", "max", "intden", "fraction")
        self.oil_red_table = ttk.Treeview(table_frame, columns=columns, show="headings",
                                          height=9, selectmode="extended")
        definitions = (
            ("file", "File name", 280), ("size", "Dimensions", 95), ("channel", "Channel", 90),
            ("threshold", "Threshold", 90), ("area", "Area", 100), ("mean", "Mean", 90),
            ("min", "Min", 65), ("max", "Max", 65), ("intden", "IntDen", 120),
            ("fraction", "Area Fraction", 110),
        )
        for name, label, width in definitions:
            self.oil_red_table.heading(name, text=label)
            self.oil_red_table.column(name, width=width, minwidth=55, anchor="center")
        x_scroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.oil_red_table.xview)
        y_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.oil_red_table.yview)
        self.oil_red_table.configure(xscrollcommand=x_scroll.set, yscrollcommand=y_scroll.set)
        self.oil_red_table.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        self.oil_red_table.bind("<<TreeviewSelect>>", self.show_selected_oil_red_preview)
        self.oil_red_table.bind("<Control-c>", self.copy_oil_red_selected)
        self.oil_red_table.bind("<Control-C>", self.copy_oil_red_selected)
        self.oil_red_table.bind("<Control-a>", self.select_all_oil_red)
        self.oil_red_table.bind("<Control-A>", self.select_all_oil_red)
        self.oil_red_widgets = [controls, actions, self.oil_red_canvas, table_frame]

    def build_bodipy_ui(self):
        controls = ttk.Frame(self.root, padding=10)
        ttk.Button(controls, text="Open BODIPY images", command=self.open_bodipy_files).pack(side="left", padx=4)
        ttk.Label(controls, text="Red threshold").pack(side="left", padx=(12, 3))
        self.bodipy_threshold = tk.IntVar(value=30)
        ttk.Spinbox(controls, from_=0, to=255, width=5,
                    textvariable=self.bodipy_threshold).pack(side="left")
        ttk.Label(controls, text="Minimum area (px²)").pack(side="left", padx=(12, 3))
        self.bodipy_min_area = tk.IntVar(value=5)
        ttk.Spinbox(controls, from_=1, to=100000, width=7,
                    textvariable=self.bodipy_min_area).pack(side="left")
        ttk.Label(controls, text="Pixel size (µm/px; 0 if unknown)").pack(side="left", padx=(12, 3))
        self.bodipy_micron_per_pixel = tk.DoubleVar(value=0.0)
        ttk.Entry(controls, width=8, textvariable=self.bodipy_micron_per_pixel).pack(side="left")
        ttk.Button(controls, text="Reanalyze with current settings", command=self.reanalyze_bodipy).pack(side="left", padx=8)
        ttk.Button(controls, text="Clear", command=self.clear_bodipy).pack(side="left", padx=4)

        actions = ttk.Frame(self.root, padding=(10, 0, 10, 8))
        ttk.Button(actions, text="Copy selected puncta", command=self.copy_bodipy_selected).pack(side="left", padx=4)
        ttk.Button(actions, text="Copy all puncta", command=self.copy_bodipy_all).pack(side="left", padx=4)
        ttk.Button(actions, text="Export CSV", command=self.export_bodipy).pack(side="left", padx=4)
        ttk.Button(actions, text="Save annotated preview", command=self.save_bodipy_preview).pack(side="left", padx=4)
        self.bodipy_status = tk.StringVar(
            value="Import RGB images. Default: red-dominance score >= 30 and minimum area 5 px²."
        )
        ttk.Label(actions, textvariable=self.bodipy_status).pack(side="left", padx=16)

        self.bodipy_canvas = tk.Canvas(self.root, bg="#111111", height=380, highlightthickness=1)
        table_frame = ttk.Frame(self.root, padding=(12, 4, 12, 12))
        columns = ("file", "spot", "area_px", "area_um", "centroid", "bbox", "mean_score",
                   "count", "total_px", "total_um", "fraction")
        self.bodipy_table = ttk.Treeview(table_frame, columns=columns, show="headings",
                                         height=9, selectmode="extended")
        definitions = (
            ("file", "File name", 230), ("spot", "Punctum ID", 75),
            ("area_px", "Punctum area (px²)", 105), ("area_um", "Punctum area (µm²)", 110),
            ("centroid", "Centroid X,Y", 105), ("bbox", "Bounding box", 130),
            ("mean_score", "Mean red-dominance score", 115), ("count", "Total count", 70),
            ("total_px", "Total area (px²)", 105), ("total_um", "Total area (µm²)", 110),
            ("fraction", "Area fraction", 85),
        )
        for name, label, width in definitions:
            self.bodipy_table.heading(name, text=label)
            self.bodipy_table.column(name, width=width, minwidth=55, anchor="center")
        x_scroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.bodipy_table.xview)
        y_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.bodipy_table.yview)
        self.bodipy_table.configure(xscrollcommand=x_scroll.set, yscrollcommand=y_scroll.set)
        self.bodipy_table.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        self.bodipy_table.bind("<<TreeviewSelect>>", self.show_selected_bodipy_preview)
        self.bodipy_table.bind("<Control-c>", self.copy_bodipy_selected)
        self.bodipy_table.bind("<Control-C>", self.copy_bodipy_selected)
        self.bodipy_table.bind("<Control-a>", self.select_all_bodipy)
        self.bodipy_table.bind("<Control-A>", self.select_all_bodipy)
        self.bodipy_widgets = [controls, actions, self.bodipy_canvas, table_frame]

    def switch_mode(self):
        for widget in getattr(self, "wb_widgets", []):
            widget.pack_forget()
        for widget in getattr(self, "confocal_widgets", []):
            widget.pack_forget()
        for widget in getattr(self, "oil_red_widgets", []):
            widget.pack_forget()
        for widget in getattr(self, "bodipy_widgets", []):
            widget.pack_forget()
        if self.mode.get() == "confocal":
            controls, actions, canvas, table_frame = self.confocal_widgets
            controls.pack(fill="x")
            actions.pack(fill="x")
            canvas.pack(fill="both", expand=True, padx=12, pady=5)
            table_frame.pack(fill="x")
        elif self.mode.get() == "oil_red":
            controls, actions, canvas, table_frame = self.oil_red_widgets
            controls.pack(fill="x")
            actions.pack(fill="x")
            canvas.pack(fill="both", expand=True, padx=12, pady=5)
            table_frame.pack(fill="x")
        elif self.mode.get() == "bodipy":
            controls, actions, canvas, table_frame = self.bodipy_widgets
            controls.pack(fill="x")
            actions.pack(fill="x")
            canvas.pack(fill="both", expand=True, padx=12, pady=5)
            table_frame.pack(fill="x")
        else:
            controls, actions, canvas, table = self.wb_widgets
            controls.pack(fill="x")
            actions.pack(fill="x")
            canvas.pack(fill="both", expand=True, padx=12, pady=5)
            table.pack(fill="x", padx=12, pady=(4, 12))

    def open_file(self):
        name = filedialog.askopenfilename(filetypes=[("WB images", "*.tif *.tiff *.png *.jpg *.jpeg *.bmp")])
        if not name:
            return
        try:
            self.gray = read_gray(name)
        except Exception as error:
            messagebox.showerror("Open failed", str(error))
            return
        self.file = Path(name)
        height, width = self.gray.shape
        self.y_start.set(max(0, round(height * 0.12)))
        self.y_end.set(min(height, round(height * 0.94)))
        self.half_width.set(max(4, round(width / (8 * int(self.count.get())))))
        self.reset_lanes()

    def reset_lanes(self):
        if self.gray is None:
            return
        try:
            count = self.count.get()
            if not 6 <= count <= 15:
                raise ValueError("The lane count must be between 6 and 15.")
            self.centers = lane_centers(self.gray, count, self.y_start.get(), self.y_end.get())
            self.refresh()
        except Exception as error:
            messagebox.showerror("Detection failed", str(error))

    def refresh(self):
        if self.gray is None or not self.centers:
            return
        try:
            h, w = self.gray.shape
            half = self.half_width.get()
            y0, y1, baseline = self.y_start.get(), self.y_end.get(), self.baseline.get()
            if not (0 <= y0 < y1 <= h and 0 <= baseline <= 50 and 1 <= half <= w):
                return
            result = [lane_area(self.gray, center, half, y0, y1, baseline) for center in self.centers]
            preview = Image.fromarray(self.gray).convert("RGB")
            pen = ImageDraw.Draw(preview)
            for i, (_, (x0, top, x1, bottom)) in enumerate(result, start=1):
                pen.rectangle((x0, top, x1 - 1, bottom - 1), outline=(235, 31, 40), width=2)
                pen.text((x0 + 3, max(0, top - 10)), str(i), fill=(235, 31, 40))
            self.marked = preview
            max_width, max_height = max(1, self.canvas.winfo_width() - 24), max(1, self.canvas.winfo_height() - 24)
            self.scale = min(max_width / w, max_height / h, 4)
            size = (max(1, round(w * self.scale)), max(1, round(h * self.scale)))
            self.photo = ImageTk.PhotoImage(preview.resize(size, Image.Resampling.NEAREST))
            self.canvas.delete("all")
            self.canvas.create_image(12, 12, image=self.photo, anchor="nw")
            self.rows = []
            for i, (area, roi) in enumerate(result, start=1):
                self.rows.append((i, self.centers[i - 1], *roi, round(area, 3)))
            self.table.delete(*self.table.get_children())
            for i, x, x0, top, x1, bottom, area in self.rows:
                self.table.insert("", "end", values=(i, x, f"{x0},{top},{x1},{bottom}", f"{area:.3f}"))
            self.status.set(f"{self.file.name} · {w}×{h} · {len(self.rows)} lanes · drag red boxes to adjust centers")
        except (ValueError, tk.TclError):
            pass

    def begin_drag(self, event):
        if not self.centers:
            return
        x = round((event.x - 12) / self.scale)
        self.dragging = min(range(len(self.centers)), key=lambda i: abs(self.centers[i] - x))
        self.move_drag(event)

    def move_drag(self, event):
        if self.dragging is None or self.gray is None:
            return
        x = round((event.x - 12) / self.scale)
        self.centers[self.dragging] = max(0, min(self.gray.shape[1] - 1, x))
        self.refresh()

    def stop_drag(self, _event):
        self.dragging = None

    def select_all(self, _event=None):
        self.table.selection_set(self.table.get_children())
        return "break"

    def copy_to_clipboard(self, rows, areas_only=False):
        if not rows:
            messagebox.showinfo("Information", "Open an image and run the analysis first.")
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(excel_text(rows, areas_only))
            self.root.update()
            self.status.set(f"Copied {len(rows)} rows. Select a starting cell in Excel and press Ctrl+V.")
        except tk.TclError as error:
            messagebox.showerror("Copy failed", str(error))

    def copy_areas(self):
        self.copy_to_clipboard(getattr(self, "rows", []), areas_only=True)

    def copy_all(self):
        self.copy_to_clipboard(getattr(self, "rows", []))

    def copy_selected(self, _event=None):
        selected = set(self.table.selection())
        items = self.table.get_children()
        chosen = [row for row, item in zip(getattr(self, "rows", []), items) if item in selected]
        self.copy_to_clipboard(chosen if selected else getattr(self, "rows", []))
        return "break"

    def export(self):
        if not hasattr(self, "rows") or not self.rows:
            messagebox.showinfo("Information", "Open an image and run the analysis first.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile=f"{self.file.stem}_WB_results.csv",
                                            filetypes=[("CSV files", "*.csv")])
        if not path:
            return
        dest = Path(path)
        try:
            with dest.open("w", encoding="utf-8-sig", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(["Source image", self.file.name])
                writer.writerow(["Note", "This preview optical-density peak area has not been calibrated pixel-by-pixel against manual ImageJ baseline selection and must not be considered identical to ImageJ Area."])
                writer.writerow(["Lanes", len(self.rows), "Baseline percentile", self.baseline.get()])
                writer.writerow(["Lane", "Center X", "ROI_X0", "ROI_Y0", "ROI_X1", "ROI_Y1", "Optical-density peak area"])
                writer.writerows(self.rows)
            picture = dest.with_name(dest.stem + "_ROI_preview.png")
            self.marked.save(picture)
            messagebox.showinfo("Export complete", f"Results: {dest}\nROI preview: {picture}")
        except Exception as error:
            messagebox.showerror("Export failed", str(error))

    def open_confocal_files(self):
        names = filedialog.askopenfilenames(
            filetypes=[("Confocal images", "*.tif *.tiff *.png *.jpg *.jpeg *.bmp")]
        )
        if not names:
            return
        for name in names:
            if name not in self.confocal_paths:
                self.confocal_paths.append(name)
        self.reanalyze_confocal()

    def clear_confocal(self):
        self.confocal_paths = []
        self.confocal_results = []
        self.confocal_table.delete(*self.confocal_table.get_children())
        self.confocal_canvas.delete("all")
        self.confocal_status.set("Cleared. You can import RGB TIFF images again.")

    def reanalyze_confocal(self):
        if not self.confocal_paths:
            messagebox.showinfo("Information", "Import confocal images first.")
            return
        try:
            low, high = self.confocal_low.get(), self.confocal_high.get()
            if not 0 <= low <= high <= 255:
                raise ValueError("The threshold must satisfy 0 <= low <= high <= 255.")
        except (tk.TclError, ValueError) as error:
            messagebox.showerror("Invalid settings", str(error))
            return

        results, failures = [], []
        for path in self.confocal_paths:
            try:
                results.append(analyze_confocal(path, self.confocal_channel.get(), low, high))
            except Exception as error:
                failures.append(f"{Path(path).name}: {error}")
        self.confocal_results = results
        self.populate_confocal_table()
        if results:
            self.show_confocal_preview(0)
            self.confocal_status.set(
                f"Analyzed {len(results)} images · {self.confocal_channel.get()} · Threshold {low}–{high}"
            )
        if failures:
            messagebox.showwarning("Some images were not analyzed", "\n".join(failures[:12]))

    def populate_confocal_table(self):
        self.confocal_table.delete(*self.confocal_table.get_children())
        for result in self.confocal_results:
            self.confocal_table.insert("", "end", values=(
                result["file"], f'{result["width"]}×{result["height"]}', result["channel"],
                f'{result["threshold_low"]}–{result["threshold_high"]}',
                f'{result["selected_pixels"]:,}', f'{result["area"]:.3f} {result["area_unit"]}',
                f'{result["mean"]:.3f}', result["min"], result["max"],
                f'{result["intden"]:.3f}', f'{result["raw_intden"]:,}',
                f'{result["area_fraction"]:.3f}%',
            ))

    def show_selected_confocal_preview(self, _event=None):
        selection = self.confocal_table.selection()
        if not selection:
            return
        items = self.confocal_table.get_children()
        self.show_confocal_preview(items.index(selection[0]))

    def show_confocal_preview(self, index):
        if not 0 <= index < len(self.confocal_results):
            return
        result = self.confocal_results[index]
        preview = result["overlay"]
        self.confocal_current_index = index
        self.confocal_canvas.update_idletasks()
        max_width = max(1, self.confocal_canvas.winfo_width() - 24)
        max_height = max(1, self.confocal_canvas.winfo_height() - 24)
        scale = min(max_width / preview.width, max_height / preview.height, 1.0)
        size = (max(1, round(preview.width * scale)), max(1, round(preview.height * scale)))
        resized = preview.resize(size, Image.Resampling.LANCZOS)
        self.confocal_photo = ImageTk.PhotoImage(resized)
        self.confocal_canvas.delete("all")
        x = max(12, (self.confocal_canvas.winfo_width() - size[0]) // 2)
        y = max(12, (self.confocal_canvas.winfo_height() - size[1]) // 2)
        self.confocal_canvas.create_image(x, y, image=self.confocal_photo, anchor="nw")
        self.confocal_status.set(
            f'{result["file"]} · Red overlay: pixels within Threshold {result["threshold_low"]}–{result["threshold_high"]}'
        )

    def selected_confocal_results(self):
        selected = set(self.confocal_table.selection())
        items = self.confocal_table.get_children()
        if not selected:
            return list(self.confocal_results)
        return [result for result, item in zip(self.confocal_results, items) if item in selected]

    def copy_confocal_results(self, results):
        if not results:
            messagebox.showinfo("Information", "There are no confocal results to copy.")
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(confocal_excel_text(results))
            self.root.update()
            self.confocal_status.set(f"Copied {len(results)} rows. Select a starting cell in Excel and press Ctrl+V.")
        except tk.TclError as error:
            messagebox.showerror("Copy failed", str(error))

    def copy_confocal_selected(self, _event=None):
        self.copy_confocal_results(self.selected_confocal_results())
        return "break"

    def copy_confocal_all(self):
        self.copy_confocal_results(self.confocal_results)

    def select_all_confocal(self, _event=None):
        self.confocal_table.selection_set(self.confocal_table.get_children())
        return "break"

    def export_confocal(self):
        if not self.confocal_results:
            messagebox.showinfo("Information", "Import and analyze confocal images first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=f"Confocal_{self.confocal_channel.get().split()[0]}_Threshold{self.confocal_low.get()}_results.csv",
            filetypes=[("CSV files", "*.csv")],
        )
        if not path:
            return
        try:
            with Path(path).open("w", encoding="utf-8-sig", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(CONFOCAL_HEADERS)
                for result in self.confocal_results:
                    writer.writerow([
                        result["file"], result["width"], result["height"], result["channel"],
                        result["threshold_low"], result["threshold_high"], result["selected_pixels"],
                        round(result["area"], 3), result["area_unit"], round(result["mean"], 3),
                        result["min"], result["max"], round(result["intden"], 3),
                        result["raw_intden"], round(result["area_fraction"], 3),
                    ])
            messagebox.showinfo("Export complete", f"Results: {path}")
        except Exception as error:
            messagebox.showerror("Export failed", str(error))

    def save_confocal_preview(self):
        if not self.confocal_results:
            messagebox.showinfo("Information", "Import and analyze confocal images first.")
            return
        index = getattr(self, "confocal_current_index", 0)
        result = self.confocal_results[index]
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            initialfile=f'{Path(result["file"]).stem}_Threshold{result["threshold_low"]}_preview.png',
            filetypes=[("PNG images", "*.png")],
        )
        if not path:
            return
        try:
            result["overlay"].save(path)
            messagebox.showinfo("Saved", f"Threshold preview: {path}")
        except Exception as error:
            messagebox.showerror("Save failed", str(error))

    def open_oil_red_files(self):
        names = filedialog.askopenfilenames(
            filetypes=[("Oil Red O images", "*.tif *.tiff *.png *.jpg *.jpeg *.bmp")]
        )
        if not names:
            return
        for name in names:
            if name not in self.oil_red_paths:
                self.oil_red_paths.append(name)
        self.reanalyze_oil_red()

    def clear_oil_red(self):
        self.oil_red_paths = []
        self.oil_red_results = []
        self.oil_red_table.delete(*self.oil_red_table.get_children())
        self.oil_red_canvas.delete("all")
        self.oil_red_status.set("Cleared. You can import RGB Oil Red O images again.")

    def reanalyze_oil_red(self):
        if not self.oil_red_paths:
            messagebox.showinfo("Information", "Import Oil Red O images first.")
            return
        try:
            low, high = self.oil_red_low.get(), self.oil_red_high.get()
            if not 0 <= low <= high <= 255:
                raise ValueError("The threshold must satisfy 0 <= low <= high <= 255.")
        except (tk.TclError, ValueError) as error:
            messagebox.showerror("Invalid settings", str(error))
            return

        results, failures = [], []
        for path in self.oil_red_paths:
            try:
                results.append(analyze_confocal(path, self.oil_red_channel.get(), low, high))
            except Exception as error:
                failures.append(f"{Path(path).name}: {error}")
        self.oil_red_results = results
        self.populate_oil_red_table()
        if results:
            self.show_oil_red_preview(0)
            self.oil_red_status.set(
                f"Analyzed {len(results)} images · {self.oil_red_channel.get()} · Threshold {low}–{high}"
            )
        if failures:
            messagebox.showwarning("Some images were not analyzed", "\n".join(failures[:12]))

    def populate_oil_red_table(self):
        self.oil_red_table.delete(*self.oil_red_table.get_children())
        for result in self.oil_red_results:
            self.oil_red_table.insert("", "end", values=(
                result["file"], f'{result["width"]}×{result["height"]}', result["channel"],
                f'{result["threshold_low"]}–{result["threshold_high"]}',
                f'{result["selected_pixels"]:,}', f'{result["mean"]:.3f}',
                result["min"], result["max"], f'{result["raw_intden"]:,}',
                f'{result["area_fraction"]:.3f}%',
            ))

    def show_selected_oil_red_preview(self, _event=None):
        selection = self.oil_red_table.selection()
        if not selection:
            return
        items = self.oil_red_table.get_children()
        self.show_oil_red_preview(items.index(selection[0]))

    def show_oil_red_preview(self, index):
        if not 0 <= index < len(self.oil_red_results):
            return
        result = self.oil_red_results[index]
        preview = result["overlay"]
        self.oil_red_current_index = index
        self.oil_red_canvas.update_idletasks()
        max_width = max(1, self.oil_red_canvas.winfo_width() - 24)
        max_height = max(1, self.oil_red_canvas.winfo_height() - 24)
        scale = min(max_width / preview.width, max_height / preview.height, 1.0)
        size = (max(1, round(preview.width * scale)), max(1, round(preview.height * scale)))
        resized = preview.resize(size, Image.Resampling.LANCZOS)
        self.oil_red_photo = ImageTk.PhotoImage(resized)
        self.oil_red_canvas.delete("all")
        x = max(12, (self.oil_red_canvas.winfo_width() - size[0]) // 2)
        y = max(12, (self.oil_red_canvas.winfo_height() - size[1]) // 2)
        self.oil_red_canvas.create_image(x, y, image=self.oil_red_photo, anchor="nw")
        self.oil_red_status.set(
            f'{result["file"]} · Red overlay: Green channel Threshold '
            f'{result["threshold_low"]}–{result["threshold_high"]}'
        )

    def selected_oil_red_results(self):
        selected = set(self.oil_red_table.selection())
        items = self.oil_red_table.get_children()
        if not selected:
            return list(self.oil_red_results)
        return [result for result, item in zip(self.oil_red_results, items) if item in selected]

    def copy_oil_red_results(self, results):
        if not results:
            messagebox.showinfo("Information", "There are no Oil Red O results to copy.")
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(oil_red_excel_text(results))
            self.root.update()
            self.oil_red_status.set(f"Copied {len(results)} rows. Select a starting cell in Excel and press Ctrl+V.")
        except tk.TclError as error:
            messagebox.showerror("Copy failed", str(error))

    def copy_oil_red_selected(self, _event=None):
        self.copy_oil_red_results(self.selected_oil_red_results())
        return "break"

    def copy_oil_red_all(self):
        self.copy_oil_red_results(self.oil_red_results)

    def select_all_oil_red(self, _event=None):
        self.oil_red_table.selection_set(self.oil_red_table.get_children())
        return "break"

    def export_oil_red(self):
        if not self.oil_red_results:
            messagebox.showinfo("Information", "Import and analyze Oil Red O images first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=f"OilRedO_Green_Threshold{self.oil_red_low.get()}-{self.oil_red_high.get()}_results.csv",
            filetypes=[("CSV files", "*.csv")],
        )
        if not path:
            return
        try:
            with Path(path).open("w", encoding="utf-8-sig", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(OIL_RED_HEADERS)
                for result in self.oil_red_results:
                    writer.writerow([
                        result["file"], result["width"], result["height"], result["channel"],
                        result["threshold_low"], result["threshold_high"], result["selected_pixels"],
                        round(result["mean"], 3), result["min"], result["max"],
                        result["raw_intden"], round(result["area_fraction"], 3),
                    ])
            messagebox.showinfo("Export complete", f"Results: {path}")
        except Exception as error:
            messagebox.showerror("Export failed", str(error))

    def save_oil_red_preview(self):
        if not self.oil_red_results:
            messagebox.showinfo("Information", "Import and analyze Oil Red O images first.")
            return
        index = getattr(self, "oil_red_current_index", 0)
        result = self.oil_red_results[index]
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            initialfile=f'{Path(result["file"]).stem}_OilRedO_Green_Threshold'
                        f'{result["threshold_low"]}-{result["threshold_high"]}_preview.png',
            filetypes=[("PNG images", "*.png")],
        )
        if not path:
            return
        try:
            result["overlay"].save(path)
            messagebox.showinfo("Saved", f"Threshold preview: {path}")
        except Exception as error:
            messagebox.showerror("Save failed", str(error))

    def open_bodipy_files(self):
        names = filedialog.askopenfilenames(
            filetypes=[("BODIPY images", "*.tif *.tiff *.png *.jpg *.jpeg *.bmp")]
        )
        if not names:
            return
        for name in names:
            if name not in self.bodipy_paths:
                self.bodipy_paths.append(name)
        self.reanalyze_bodipy()

    def clear_bodipy(self):
        self.bodipy_paths = []
        self.bodipy_results = []
        self.bodipy_rows = []
        self.bodipy_table.delete(*self.bodipy_table.get_children())
        self.bodipy_canvas.delete("all")
        self.bodipy_status.set("Cleared. You can import RGB BODIPY images again.")

    def reanalyze_bodipy(self):
        if not self.bodipy_paths:
            messagebox.showinfo("Information", "Import BODIPY images first.")
            return
        try:
            threshold = self.bodipy_threshold.get()
            minimum_area = self.bodipy_min_area.get()
            micron_per_pixel = self.bodipy_micron_per_pixel.get()
            if not 0 <= threshold <= 255:
                raise ValueError("The red threshold must be between 0 and 255.")
            if minimum_area < 1:
                raise ValueError("The minimum punctum area must be at least 1 px².")
            if micron_per_pixel < 0:
                raise ValueError("Pixel size cannot be negative; enter 0 if unknown.")
        except (tk.TclError, ValueError) as error:
            messagebox.showerror("Invalid settings", str(error))
            return

        results, failures = [], []
        for path in self.bodipy_paths:
            try:
                results.append(analyze_bodipy(path, threshold, minimum_area, micron_per_pixel))
            except Exception as error:
                failures.append(f"{Path(path).name}: {error}")
        self.bodipy_results = results
        self.populate_bodipy_table()
        if results:
            self.show_bodipy_preview(0)
        if failures:
            messagebox.showwarning("Some images were not analyzed", "\n".join(failures[:12]))

    def populate_bodipy_table(self):
        self.bodipy_table.delete(*self.bodipy_table.get_children())
        self.bodipy_rows = []
        for result in self.bodipy_results:
            for spot in result["spots"]:
                self.bodipy_rows.append((result, spot))
                self.bodipy_table.insert("", "end", values=(
                    result["file"], spot["spot_id"], f'{spot["area_pixels"]:,}',
                    "—" if spot["area_um2"] is None else f'{spot["area_um2"]:.3f}',
                    f'{spot["centroid_x"]:.2f}, {spot["centroid_y"]:.2f}',
                    ",".join(str(value) for value in spot["bbox"]),
                    f'{spot["mean_red_score"]:.3f}', result["spot_count"],
                    f'{result["total_pixels"]:,}',
                    "—" if result["total_um2"] is None else f'{result["total_um2"]:.3f}',
                    f'{result["area_fraction"]:.3f}%',
                ))

    def show_selected_bodipy_preview(self, _event=None):
        selection = self.bodipy_table.selection()
        if not selection:
            return
        items = self.bodipy_table.get_children()
        row_index = items.index(selection[0])
        selected_result = self.bodipy_rows[row_index][0]
        self.show_bodipy_preview(self.bodipy_results.index(selected_result))

    def show_bodipy_preview(self, index):
        if not 0 <= index < len(self.bodipy_results):
            return
        result = self.bodipy_results[index]
        preview = result["overlay"]
        self.bodipy_current_index = index
        self.bodipy_canvas.update_idletasks()
        max_width = max(1, self.bodipy_canvas.winfo_width() - 24)
        max_height = max(1, self.bodipy_canvas.winfo_height() - 24)
        scale = min(max_width / preview.width, max_height / preview.height, 2.0)
        size = (max(1, round(preview.width * scale)), max(1, round(preview.height * scale)))
        resized = preview.resize(size, Image.Resampling.NEAREST if scale > 1 else Image.Resampling.LANCZOS)
        self.bodipy_photo = ImageTk.PhotoImage(resized)
        self.bodipy_canvas.delete("all")
        x = max(12, (self.bodipy_canvas.winfo_width() - size[0]) // 2)
        y = max(12, (self.bodipy_canvas.winfo_height() - size[1]) // 2)
        self.bodipy_canvas.create_image(x, y, image=self.bodipy_photo, anchor="nw")
        area_text = f'{result["total_pixels"]:,} px²'
        if result["total_um2"] is not None:
            area_text += f' / {result["total_um2"]:.3f} µm²'
        self.bodipy_status.set(
            f'{result["file"]} · Puncta: {result["spot_count"]} · Total area: {area_text} · '
            f'Area fraction {result["area_fraction"]:.3f}%'
        )

    def selected_bodipy_rows(self):
        selected = set(self.bodipy_table.selection())
        items = self.bodipy_table.get_children()
        if not selected:
            return list(self.bodipy_rows)
        return [row for row, item in zip(self.bodipy_rows, items) if item in selected]

    def copy_bodipy_rows(self, rows):
        if not rows:
            messagebox.showinfo("Information", "There are no BODIPY puncta results to copy.")
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(bodipy_excel_text(self.bodipy_results, rows))
            self.root.update()
            self.bodipy_status.set(f"Copied {len(rows)} puncta. Select a starting cell in Excel and press Ctrl+V.")
        except tk.TclError as error:
            messagebox.showerror("Copy failed", str(error))

    def copy_bodipy_selected(self, _event=None):
        self.copy_bodipy_rows(self.selected_bodipy_rows())
        return "break"

    def copy_bodipy_all(self):
        self.copy_bodipy_rows(self.bodipy_rows)

    def select_all_bodipy(self, _event=None):
        self.bodipy_table.selection_set(self.bodipy_table.get_children())
        return "break"

    def export_bodipy(self):
        if not self.bodipy_rows:
            messagebox.showinfo("Information", "Import and analyze BODIPY images first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=f"BODIPY_puncta_area_threshold{self.bodipy_threshold.get()}_results.csv",
            filetypes=[("CSV files", "*.csv")],
        )
        if not path:
            return
        try:
            with Path(path).open("w", encoding="utf-8-sig", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(BODIPY_HEADERS)
                for result, spot in self.bodipy_rows:
                    writer.writerow([
                        result["file"], spot["spot_id"], spot["area_pixels"],
                        "" if spot["area_um2"] is None else round(spot["area_um2"], 3),
                        round(spot["centroid_x"], 2), round(spot["centroid_y"], 2),
                        ",".join(str(value) for value in spot["bbox"]),
                        round(spot["mean_red_score"], 3), result["spot_count"],
                        result["total_pixels"],
                        "" if result["total_um2"] is None else round(result["total_um2"], 3),
                        round(result["area_fraction"], 3), result["red_threshold"],
                        result["minimum_area"], result["micron_per_pixel"],
                    ])
            messagebox.showinfo("Export complete", f"Per-punctum and total-area results: {path}")
        except Exception as error:
            messagebox.showerror("Export failed", str(error))

    def save_bodipy_preview(self):
        if not self.bodipy_results:
            messagebox.showinfo("Information", "Import and analyze BODIPY images first.")
            return
        index = getattr(self, "bodipy_current_index", 0)
        result = self.bodipy_results[index]
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            initialfile=f'{Path(result["file"]).stem}_BODIPY_puncta_annotated.png',
            filetypes=[("PNG images", "*.png")],
        )
        if not path:
            return
        try:
            result["overlay"].save(path)
            messagebox.showinfo("Saved", f"Annotated preview: {path}")
        except Exception as error:
            messagebox.showerror("Save failed", str(error))


if __name__ == "__main__":
    if "--self-test-bodipy" in sys.argv:
        test_paths = [value for value in sys.argv[1:] if value != "--self-test-bodipy"]
        if not test_paths:
            raise SystemExit(2)
        for test_path in test_paths:
            tested = analyze_bodipy(test_path, 30, 5, 0.0)
            if tested["spot_count"] <= 0 or tested["total_pixels"] <= 0:
                raise SystemExit(3)
        raise SystemExit(0)
    if "--self-test-oil-red" in sys.argv:
        test_paths = [value for value in sys.argv[1:] if value != "--self-test-oil-red"]
        if not test_paths:
            raise SystemExit(2)
        for test_path in test_paths:
            tested = analyze_confocal(test_path, "Green (2/3)", 0, 150)
            if tested["selected_pixels"] <= 0 or tested["raw_intden"] <= 0:
                raise SystemExit(3)
        raise SystemExit(0)
    if "--self-test-confocal" in sys.argv:
        test_paths = [value for value in sys.argv[1:] if value != "--self-test-confocal"]
        if not test_paths:
            raise SystemExit(2)
        for test_path in test_paths:
            tested = analyze_confocal(test_path, "Green (2/3)", 45, 255)
            if tested["selected_pixels"] <= 0 or tested["raw_intden"] <= 0:
                raise SystemExit(3)
        raise SystemExit(0)
    app_root = tk.Tk()
    WBApp(app_root)
    app_root.mainloop()
