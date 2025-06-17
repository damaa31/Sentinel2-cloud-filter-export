
# 🌍 Sentinel-2 Cloud-Free Image Export Script

This script automates the process of generating **cloud-free composite images** from Sentinel-2 data using **Google Earth Engine (GEE)**. It is particularly tailored to support **wildfire analysis** across Europe but can be adapted to other purposes involving time-series image analysis.

---

## 📌 Objective

The primary goal is to extract and export annual **cloud-free median composites** for areas affected by wildfires. The script filters and processes Sentinel-2 images, masks out clouds and shadows using the S2_CLOUD_PROBABILITY product, and exports the best cloud-free image for each post-fire year.

---

## ⚙️ Key Parameters and Their Meaning

| Parameter           | Value        | Description |
|---------------------|--------------|-------------|
| `CLOUD_FILTER`      | `50`         | Max % of clouds in metadata (`CLOUDY_PIXEL_PERCENTAGE`) to consider an image. |
| `CLD_PRB_THRESH`    | `30`         | Threshold for cloud probability from s2cloudless. |
| `NIR_DRK_THRESH`    | `0.15`       | Near-infrared threshold for detecting cloud shadows. |
| `CLD_PRJ_DIST`      | `1` (pixel)  | Distance to project cloud shadows. |
| `BUFFER`            | `50`         | Buffer (in meters) around clouds and shadows to mask residuals. |
| `UMBRAL_NUBES`      | `15`         | Max cloud percentage tolerated inside AOI before attempting to reprocess. |

---

## 📅 Temporal Settings

- For each fire polygon, the script extracts the **initial fire year** from the `initialdat` property.
- Processing starts the **year after the fire**, continuing until **2024** (inclusive).
- Default time window each year is **May 15 – June 15**, targeting early growing season.
- If selected images exceed 15% cloud cover, a fallback window extends to **July 15**.

---

## 🛰️ Data Sources

- **Sentinel-2 Surface Reflectance (SR)**: `COPERNICUS/S2_SR_HARMONIZED`
- **Sentinel-2 Cloud Probability**: `COPERNICUS/S2_CLOUD_PROBABILITY`
- **Fire polygons input**: A custom `FeatureCollection` in your GEE assets, with at least the properties `initialdat`, `finaldat`, and `Id`.

---

## 🧠 Key Functionalities

- Joins cloud probability collection with SR images using `system:index`.
- Masks clouds and shadows using custom logic.
- Calculates actual cloud cover over the AOI.
- Selects best image per year or computes median composite.
- Automatically detects UTM zone and assigns EPSG:258XX for export.
- Exports images to Google Drive in organized folders.
- Logs export details and cloud percentages in a CSV file.

---

## 📤 Output

Each export includes:

- Image named: `FireID_Year` (e.g., `ES12345_2022.tif`)
- Stored in: `Incendios_Europa_años` (Google Drive)
- Projection: UTM ETRS89 (EPSG:258XX), 20 m resolution
- Log: `resultados_nubes.csv` with image cloud percentage and export status

---

## ▶️ How to Run

1. Clone this repo or download the script.
2. Ensure your GEE account is authenticated:
   ```bash
   earthengine authenticate
   ```
3. Modify the script with:
   - Your `project` name in `ee.Initialize(project='your-project')`
   - Your fire polygons asset path
4. Run the script in a Python environment:
   ```bash
   python export_cloudfree_images.py
   ```

---

## 🧩 Customization Options

- Adjust **dates** for different seasonal periods.
- Apply to **non-fire areas** for other land cover studies.
- Replace **median** with **mean**, **mosaic**, or **first** image.
- Add **spectral indices** (e.g., NDVI, NBR) before exporting.

---

## 📁 Project Structure

```
.
├── export_cloudfree_images.py      # Main script
├── resultados_nubes.csv           # Output log file (generated)
└── README.md                      # Documentation
```

---

## 🔧 Dependencies

- Python 3.8+
- `earthengine-api`
- `csv`
- `os`, `datetime`, `math`

Install Earth Engine API:
```bash
pip install earthengine-api
```

---

## 🛠️ To-Do or Improvements

- [ ] Add image visualization before export
- [ ] Include NDVI/NBR in exports
- [ ] Batch management with `ee.batch.Task.list()`
- [ ] Export metadata as JSON or GeoTIFF tags

---

## 🧾 Author & Acknowledgments

Developed by a geospatial analyst using Google Earth Engine to support post-fire monitoring and ecological recovery in Europe.

Inspired by GEE community resources and optimized for real-world landscape analysis.

---

## 📄 License

MIT License. See `LICENSE` file for more details.

---

## 📚 Citation

If you use this script in your research or projects, please cite it as:

> *David San Martín Aguado (2025). Sentinel-2 Cloud-Free Export Script for Fire Monitoring. GitHub Repository.*  
> [https://github.com/damaa31/Sentinel2-cloud-filter-export.git]
