import streamlit as st
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, Polygon
import tempfile
import os
import zipfile
import requests
import gdown
from io import BytesIO
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def dms_to_dd(degree, minute, second, direction):
    dd = degree + minute / 60 + second / 3600
    if direction in ["LS", "BB"]:
        dd *= -1
    return dd

@st.cache_data
def get_kawasan_konservasi_from_arcgis():
    url = "https://kspservices.big.go.id/satupeta/rest/services/PUBLIK/SUMBER_DAYA_ALAM_DAN_LINGKUNGAN/MapServer/35/query"
    params = {
        "where": "1=1",
        "outFields": "*",
        "f": "geojson"
    }
    try:
        response = requests.get(url, params=params, verify=False)
        if response.status_code == 200:
            gdf = gpd.read_file(BytesIO(response.content))
            return gdf
        else:
            st.warning(f"Gagal mengunduh data: status code {response.status_code}")
            return None
    except Exception as e:
        st.warning(f"Gagal mengambil data dari ArcGIS Server: {e}")
        return None

def download_shapefile_from_gdrive(gdrive_url):
    try:
        file_id = gdrive_url.split("/d/")[1].split("/")[0]
        download_url = f"https://drive.google.com/uc?id={file_id}"
        
        with tempfile.TemporaryDirectory() as tmpdirname:
            zip_path = os.path.join(tmpdirname, "file.zip")
            gdown.download(download_url, zip_path, quiet=False)
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(tmpdirname)

            for file in os.listdir(tmpdirname):
                if file.endswith(".shp"):
                    shp_path = os.path.join(tmpdirname, file)
                    gdf = gpd.read_file(shp_path)
                    return gdf
        return None
    except Exception as e:
        st.warning(f"Gagal mengunduh dan membaca shapefile: {e}")
        return None

# ================================
# ==== MULAI STREAMLIT APP ======
# ================================
st.title("Konversi Koordinat dan Analisis Spasial - Verdok")

format_pilihan = st.radio("Pilih format data koordinat:", ("OSS-UTM", "General-Decimal Degree"))

if format_pilihan == "OSS-UTM":
    st.write("Format OSS-UTM dipilih. Kolom: `id`, `bujur_derajat`, `bujur_menit`, `bujur_detik`, `BT_BB`, `lintang_derajat`, `lintang_menit`, `lintang_detik`, `LU_LS`")
else:
    st.write("Format General-DD dipilih. Kolom: `id`, `x`, `y`")

uploaded_file = st.file_uploader("Unggah file Excel", type=["xlsx"])
shp_type = st.radio("Pilih tipe shapefile yang ingin dibuat:", ("Poligon (Polygon)", "Titik (Point)"))
nama_file = st.text_input("➡️Masukkan nama file shapefile (tanpa ekstensi)⬅️", value="nama_shapefile")

cek_sedimentasi = st.checkbox("Sedimentasi 🏖️")
cek_pertambangan = st.checkbox("Pertambangan ⛏️")

konservasi_gdf = get_kawasan_konservasi_from_arcgis()
mil12_gdf = download_shapefile_from_gdrive("https://drive.google.com/file/d/16MnH27AofcSSr45jTvmopOZx4CMPxMKs/view?usp=sharing")
sedimen_gdf = download_shapefile_from_gdrive("https://drive.google.com/file/d/1ZcruoWPzneMCn11Y7vmgCvIWFyO4Sgg6/view?usp=sharing") if cek_sedimentasi else None
tambang_gdf = download_shapefile_from_gdrive("https://drive.google.com/file/d/1vysvEsJIiuTPGq1JgdqHMsBucLOGcFn8/view?usp=sharing") if cek_pertambangan else None

if uploaded_file and nama_file:
    df = pd.read_excel(uploaded_file)
    if df.shape[0] > 50:
        st.warning("Hanya 20 baris pertama yang akan diproses.")
        df = df.head(50)

    if format_pilihan == "OSS-UTM":
        df['longitude'] = df.apply(lambda row: dms_to_dd(row['bujur_derajat'], row['bujur_menit'], row['bujur_detik'], row['BT_BB']), axis=1)
        df['latitude'] = df.apply(lambda row: dms_to_dd(row['lintang_derajat'], row['lintang_menit'], row['lintang_detik'], row['LU_LS']), axis=1)
    else:
        df.rename(columns={'x': 'longitude', 'y': 'latitude'}, inplace=True)

    if shp_type == "Titik (Point)":
        geometry = [Point(xy) for xy in zip(df['longitude'], df['latitude'])]
        gdf = gpd.GeoDataFrame(df[['id']], geometry=geometry, crs="EPSG:4326")

        if konservasi_gdf is not None:
            joined = gpd.sjoin(gdf, konservasi_gdf[['namobj', 'geometry']], how='left', predicate='within')
            points_in_konservasi = joined[~joined['namobj'].isna()]
            if not points_in_konservasi.empty:
                st.success(f"{len(points_in_konservasi)} titik berada di Kawasan Konservasi: {', '.join(points_in_konservasi['namobj'].unique())}")
            else:
                st.info("Tidak ada titik di kawasan konservasi.")

        if mil12_gdf is not None:
            joined_mil = gpd.sjoin(gdf, mil12_gdf[['WP', 'geometry']], how='left', predicate='within')
            points_in_mil = joined_mil[~joined_mil['WP'].isna()]
            if not points_in_mil.empty:
                st.success(f"{len(points_in_mil)} titik berada di wilayah 12 Mil Laut: {', '.join(points_in_mil['WP'].unique())}")
            else:
                st.info("Titik di luar wilayah 12 Mil Laut.")

        if sedimen_gdf is not None:
            joined_sedimen = gpd.sjoin(gdf, sedimen_gdf[['geometry']], how='left', predicate='within')
            if not joined_sedimen[joined_sedimen.index_right.notna()].empty:
                st.success("Titik berada di Lokasi Prioritas Sedimentasi")
            else:
                st.info("Titik di luar Lokasi Prioritas Sedimentasi")

        if tambang_gdf is not None:
            joined_tambang = gpd.sjoin(gdf, tambang_gdf[['geometry']], how='left', predicate='within')
            if not joined_tambang[joined_tambang.index_right.notna()].empty:
                st.success("Titik berada di area Pertambangan")
            else:
                st.info("Titik di luar area Pertambangan")

    else:  # Poligon
        coords = list(zip(df['longitude'], df['latitude']))
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        geometry = [Polygon(coords)]
        gdf = gpd.GeoDataFrame(pd.DataFrame({"id": ["polygon_1"]}), geometry=geometry, crs="EPSG:4326")

        if konservasi_gdf is not None:
            overlay = gpd.overlay(gdf, konservasi_gdf[['namobj', 'geometry']], how='intersection')
            if not overlay.empty:
                st.success(f"Poligon berada di Kawasan Konservasi: {', '.join(overlay['namobj'].unique())}")
            else:
                st.info("Poligon tidak di kawasan konservasi.")

        if mil12_gdf is not None:
            overlay = gpd.overlay(gdf, mil12_gdf[['WP', 'geometry']], how='intersection')
            if not overlay.empty:
                st.success(f"Poligon berada di wilayah 12 Mil Laut: {', '.join(overlay['WP'].unique())}")
            else:
                st.info("Poligon di luar wilayah 12 Mil Laut.")

        if sedimen_gdf is not None:
            overlay = gpd.overlay(gdf, sedimen_gdf[['geometry']], how='intersection')
            if not overlay.empty:
                st.success("Poligon berada di Lokasi Prioritas Sedimentasi")
            else:
                st.info("Poligon di luar Lokasi Prioritas Sedimentasi")

        if tambang_gdf is not None:
            overlay = gpd.overlay(gdf, tambang_gdf[['geometry']], how='intersection')
            if not overlay.empty:
                st.success("Poligon berada di area Pertambangan")
            else:
                st.info("Poligon di luar area Pertambangan")

    st.subheader("Hasil Konversi")
    st.dataframe(df[['id', 'longitude', 'latitude']])

    with tempfile.TemporaryDirectory() as tmpdirname:
        shp_path = os.path.join(tmpdirname, f"{nama_file}.shp")
        gdf.to_file(shp_path)
        zip_path = os.path.join(tmpdirname, f"{nama_file}.zip")
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for ext in ['shp', 'shx', 'dbf', 'cpg', 'prj']:
                fpath = shp_path.replace('.shp', f'.{ext}')
                if os.path.exists(fpath):
                    zipf.write(fpath, arcname=os.path.basename(fpath))
        with open(zip_path, "rb") as f:
            st.download_button("Unduh Shapefile (ZIP)", f, file_name=f"{nama_file}.zip")
