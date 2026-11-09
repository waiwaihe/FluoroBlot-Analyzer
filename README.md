# FluoroBlot Analyzer
**Current release: [v1.0.0](https://github.com/waiwaihe/FluoroBlot-Analyzer/releases/tag/v1.0.0)**

FluoroBlot Analyzer is a standalone Windows application that integrates four commonly used biomedical image-analysis workflows:

- Western blot densitometry
- Confocal fluorescence quantification
- Oil Red O staining analysis
- BODIPY puncta measurement

The application provides visible analysis parameters, image overlays for result review, batch-compatible tables, and spreadsheet-ready outputs. The packaged Windows executable does not require Python or ImageJ.

## Main features

### Western blot densitometry

- Supports 6 to 15 lanes.
- Automatically estimates lane centers.
- Allows manual adjustment of lane regions by dragging.
- Provides adjustable ROI width, analysis-row range, and baseline percentile.
- Reports lane number, center position, ROI coordinates, and background-corrected optical-density peak area.
- Exports CSV data and an annotated image.

### Confocal fluorescence quantification

- Supports RGB TIFF, PNG, JPEG, and BMP images.
- Provides selectable red, green, and blue channels.
- Uses Green (2/3) and Threshold 45–255 by default.
- Reports positive pixels, Area, Mean, Min, Max, IntDen, RawIntDen, and Area Fraction.
- Supports batch analysis, threshold-overlay review, CSV export, and direct copying to Excel.

### Oil Red O staining analysis

- Reproduces the recorded RGB Stack workflow.
- Uses Green (2/3) and Threshold 0–150 by default.
- Reports Area, Mean, Min, Max, IntDen, and Area Fraction.
- Supports batch reanalysis and threshold-preview export.

### BODIPY puncta measurement

- Detects red-dominant fluorescent objects on dark backgrounds.
- Uses a red-dominance threshold of 30 and a minimum object area of 5 px² by default.
- Reports each punctum's area, centroid, bounding box, and mean red-dominance score.
- Reports puncta count, total puncta area, and image area fraction.
- Supports optional calibration in µm/px for area measurements in µm².
- Generates yellow object outlines and numeric labels for visual verification.

## Download

Download the latest Windows executable from the repository's **Releases** page.

The executable is larger than GitHub's normal 100 MB file limit and should therefore be uploaded as a release asset rather than committed directly to the repository.

## Running the Windows application

1. Download `FluoroBlot-Analyzer-v1.0.0-Windows-x64.exe` from Releases.
2. Double-click the file to start the application.
3. Select an analysis mode from the top of the window.
4. Import one or more supported images.
5. Review the ROI or segmentation overlay before exporting results.

Python and ImageJ are not required when using the packaged executable.

## Running from source

### Requirements

- Python 3.11 or later
- NumPy
- Pillow 12 or later

Install the dependencies:

```bash
python -m pip install --upgrade numpy "Pillow>=12"
```

Run the application:

```bash
python python FluoroBlot_Analyzer.py
```

## Building the executable

Install PyInstaller:

```bash
python -m pip install --upgrade pyinstaller
```

Build a single-file Windows executable:

```bash
python -m PyInstaller --noconfirm --clean --onefile --windowed --name FluoroBlot-Analyzer FluoroBlot_Analyzer.py
```

## Recommended analysis practice

- Use identical image-acquisition settings within each experimental comparison.
- Apply the same thresholds and analysis parameters to images being compared.
- Inspect every ROI or segmentation overlay before accepting the numerical results.
- Verify microscope calibration before interpreting measurements in µm².
- Report the software version and relevant analysis parameters in publications.

## Scope and limitations

FluoroBlot Analyzer automates restricted and inspectable workflows. It does not determine Western blot saturation, establish assay linearity, select loading controls, perform experimental normalization, segment individual cells, analyze native multidimensional stacks, or calculate colocalization.

Touching BODIPY puncta without a below-threshold gap are treated as a single connected object. Thresholds and minimum-area settings can change object counts and measured areas. ImageJ or another established image-analysis platform should be used for advanced workflows and independent method comparison.

The software output should be reviewed by the researcher and should not be treated as a substitute for experimental validation or statistical analysis.

## Citation

If you use FluoroBlot Analyzer in published work, please cite the associated article or archived software release. Add the final citation after publication:

> [Authors]. FluoroBlot Analyzer: a standalone four-module platform for reproducible biomedical image quantification. [Journal]. [Year]. [DOI].

## License

This project is distributed under the MIT License. See [LICENSE](LICENSE) for details.

## Contact

For questions, bug reports, or feature requests, open an issue in this repository.
