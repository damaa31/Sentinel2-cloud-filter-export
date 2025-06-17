# ===========================================
# Sentinel-2 Cloud Filtering and Export Script
# ===========================================
# This script automates the download and export of cloud-free composites
# from Sentinel-2 for areas affected by wildfires.
# It uses Earth Engine, applies cloud and shadow filters, and selects the
# least cloudy image from a defined period for each fire and year.

import ee
import csv

# ------------------------------------------------------------
# 1. Initialization and global configuration
# ------------------------------------------------------------

# Initialize Earth Engine (requires prior authentication)
ee.Initialize(project='your-project-id')  # Replace with your GEE project ID if different

# Key parameters (adjustable according to needs or atmospheric/local conditions)
CLOUD_FILTER = 50              # Maximum % of clouds allowed according to 'CLOUDY_PIXEL_PERCENTAGE' metadata
CLD_PRB_THRESH = 30            # Probability threshold to consider a pixel as cloud (0-100)
NIR_DRK_THRESH = 0.15          # Darkness threshold to identify shadows (NIR channel)
CLD_PRJ_DIST = 1               # Distance to project shadows (in km, approximately)
BUFFER = 50                    # Buffer (m) to expand the cloud and shadow mask
UMBRAL_NUBES = 15              # Maximum % of clouds tolerated in the final image

# Load the fire collection as base geometry
# 💡 This collection must have the attributes: "id", "initialdat" (start date), "finaldate" (end date of the fire)
incendios = ee.FeatureCollection("projects/ee-/assets/Incendios_europa")

# ------------------------------------------------------------
# 2. Loading and merging S2 + cloud collections
# ------------------------------------------------------------

def get_s2_sr_cld_col(aoi, start_date, end_date):
    """
    Returns a Sentinel-2 SR collection along with s2cloudless
    joined by image index.
    """
    s2_sr_col = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')\
        .filterBounds(aoi)\
        .filterDate(start_date, end_date)\
        .filter(ee.Filter.lte('CLOUDY_PIXEL_PERCENTAGE', CLOUD_FILTER))

    s2_cloudless_col = ee.ImageCollection('COPERNICUS/S2_CLOUD_PROBABILITY')\
        .filterBounds(aoi)\
        .filterDate(start_date, end_date)

    # Join the two collections by index (ID)
    joined = ee.Join.saveFirst('s2cloudless').apply(
        primary=s2_sr_col,
        secondary=s2_cloudless_col,
        condition=ee.Filter.equals(leftField='system:index', rightField='system:index')
    )
    return ee.ImageCollection(joined)

# ------------------------------------------------------------
# 3. Cloud and shadow masking
# ------------------------------------------------------------

def add_cloud_bands(img):
    """Adds cloud probability and binary mask bands"""
    cld_prb = ee.Image(img.get('s2cloudless')).select('probability')
    is_cloud = cld_prb.gt(CLD_PRB_THRESH).rename('clouds')
    return img.addBands([cld_prb.rename('cloud_prob'), is_cloud])

def add_shadow_bands(img):
    """Detects shadows using dark pixels and solar direction"""
    not_water = img.select('SCL').neq(6)  # Excludes water (SCL=6)
    dark_pixels = img.select('B8').lt(NIR_DRK_THRESH * 1e4).multiply(not_water).rename('dark_pixels')
    shadow_azimuth = ee.Number(90).subtract(ee.Number(img.get('MEAN_SOLAR_AZIMUTH_ANGLE')))
    cld_proj = img.select('clouds').directionalDistanceTransform(shadow_azimuth, CLD_PRJ_DIST * 10)\
        .select('distance').mask().rename('cloud_transform')
    shadows = cld_proj.multiply(dark_pixels).rename('shadows')
    return img.addBands([dark_pixels, cld_proj, shadows])

def add_cld_shdw_mask(img):
    """Combines cloud and shadow masks (focal_min + buffer)"""
    img_cloud = add_cloud_bands(img)
    img_shadow = add_shadow_bands(img_cloud)
    is_cld_shdw = img_shadow.select('clouds').add(img_shadow.select('shadows')).gt(0)\
        .focal_min(2).focal_max(BUFFER * 2 / 20)\
        .rename('cloudmask')
    return img_shadow.addBands(is_cld_shdw)

def apply_cld_shdw_mask(img):
    """Applies binary cloud/shadow mask on optical bands"""
    not_cld_shdw = img.select('cloudmask').Not()
    return img.select('B.*').updateMask(not_cld_shdw)

# ------------------------------------------------------------
# 4. Cloudiness evaluation in the AOI
# ------------------------------------------------------------

def get_cloud_percentage(image, aoi):
    """Calculates % of clouds in AOI based on s2cloudless"""
    cloud_prob = ee.Image(image.get('s2cloudless')).select('probability')
    cloud_mask = cloud_prob.gt(CLD_PRB_THRESH)
    valid_mask = image.select('B8').mask().gt(0)
    cloud_mask = cloud_mask.updateMask(valid_mask)

    cloud_area = cloud_mask.reduceRegion(
        reducer=ee.Reducer.sum(), geometry=aoi, scale=10, maxPixels=1e9
    ).get('probability')
    total_area = ee.Image(1).updateMask(valid_mask).reduceRegion(
        reducer=ee.Reducer.sum(), geometry=aoi, scale=10, maxPixels=1e9
    ).get('constant')

    return ee.Number(cloud_area).divide(total_area).multiply(100)

# ------------------------------------------------------------
# 5. Select best image by % of clouds
# ------------------------------------------------------------

def get_best_image_by_cloud_cover(col, aoi):
    """Returns the image in the collection with the lowest % of clouds in the AOI"""
    def set_cloudiness(img):
        cloud_prob = ee.Image(img.get('s2cloudless')).select('probability')
        cloud_mask = cloud_prob.gt(CLD_PRB_THRESH)
        valid_mask = img.select('B8').mask().gt(0)
        cloud_mask = cloud_mask.updateMask(valid_mask)

        cloud_area = cloud_mask.reduceRegion(
            reducer=ee.Reducer.sum(), geometry=aoi, scale=10, maxPixels=1e9
        ).get('probability')
        total_area = ee.Image(1).updateMask(valid_mask).reduceRegion(
            reducer=ee.Reducer.sum(), geometry=aoi, scale=10, maxPixels=1e9
        ).get('constant')

        cloud_pct = ee.Number(cloud_area).divide(total_area).multiply(100)
        return img.set('CLOUDY_PERCENT_AOI', cloud_pct)

    col_with_cloud = col.map(set_cloudiness)
    best_img = col_with_cloud.sort('CLOUDY_PERCENT_AOI').first()
    return ee.Image(best_img)

# ------------------------------------------------------------
# 6. Cloud-free composite and export
# ------------------------------------------------------------

def getCloudFreeComposite(aoi, start, end):
    """Median cloud-free composite after applying the mask"""
    col = get_s2_sr_cld_col(aoi, start, end)\
        .map(add_cld_shdw_mask)\
        .map(apply_cld_shdw_mask)
    return col.median().clip(aoi)

def try_export_image(nombre, aoi, start, end, epsg, writer):
    """Evaluates cloudiness and triggers export if acceptable"""
    col = get_s2_sr_cld_col(aoi, start, end)
    if col.size().getInfo() == 0:
        print(f"❌ No images for {nombre}")
        writer.writerow([nombre, "", "No images"])
        return False

    img = get_best_image_by_cloud_cover(col, aoi)

    try:
        cloud_percentage = get_cloud_percentage(img, aoi).getInfo()
    except Exception as e:
        print(f"⚠️ Cloud percentage error {nombre}: {e}")
        writer.writerow([nombre, "", "Cloud error"])
        return False

    print(f"☁️ Clouds in {nombre}: {cloud_percentage:.1f}%")

    # If the image has more clouds than the threshold and it's June (6), try July (7, 15)
    if cloud_percentage > UMBRAL_NUBES:
        if end.get('month').getInfo() == 6:
            print(f"🔁 Retrying {nombre} in July")
            end_july = ee.Date.fromYMD(end.get('year').getInfo(), 7, 15)
            return try_export_image(nombre, aoi, start, end_july, epsg, writer)
        else:
            print(f"❌ Image discarded: {nombre}")
            writer.writerow([nombre, cloud_percentage, "Discarded"])
            return False

    # Export cloud-free composite
    img_export = getCloudFreeComposite(aoi, start, end)
    task = ee.batch.Export.image.toDrive(
        image=img_export,
        description=f"S2_{nombre}",
        folder="Incendios_Europa_años",     # Folder name where files will be exported to DRIVE
        fileNamePrefix=nombre,
        region=aoi,
        crs=epsg,
        scale=20,
        maxPixels=1e13
    )
    task.start()
    print(f"📤 Exporting: {nombre}")
    writer.writerow([nombre, cloud_percentage, "Exported"])
    return True

# ------------------------------------------------------------
# 7. Fire loop and main execution
# ------------------------------------------------------------

def process_feature(feature, writer):
    incendio = ee.Feature(feature)
    incendioID = incendio.get("id").getInfo()
    fechaInicio = ee.Date(incendio.get("initialdat"))
    geom = incendio.geometry()
    aoi = geom.bounds().buffer(3000)   ## 3 km buffer

    # Calculation of UTM zone and corresponding EPSG based on fire location
    lon = aoi.centroid(1).coordinates().get(0)
    huso = ee.Number(lon).add(180).divide(6).floor().add(1)
    epsg = f"EPSG:258{int(huso.getInfo()):02d}"
    print(f"\n📌 EPSG for {incendioID}: {epsg}")

    # Year of the fire
    anioInicio = fechaInicio.get('year').getInfo()

    # 🔽️ Loop from the year after the fire up to 2024 (inclusive)
    for anio in range(anioInicio + 1, 2024):
        # ⏱️ Period of interest: May 15 to June 15
        start = ee.Date.fromYMD(anio, 5, 15)
        end = ee.Date.fromYMD(anio, 6, 15)

        # If the image from this period is too cloudy, the script automatically extends to July (see logic in try_export_image)
        nombre = f"{incendioID}_{anio}"
        try:
            try_export_image(nombre, aoi, start, end, epsg, writer)
        except Exception as e:
            print(f"⚠️ Error in {nombre}: {e}")

# ------------------------------------------------------------
# 8. General script execution + CSV with information
# ------------------------------------------------------------

with open("resultados_nubes.csv", mode='w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(["Name", "% Clouds", "Status"])
    incendios_features = incendios.getInfo()['features']
    for ftr in incendios_features:
        process_feature(ftr, writer)