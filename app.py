import streamlit as st
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, Polygon
import tempfile
import os
import zipfile
import requests
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
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        response = requests.get(download_url, stream=True)
        if response.status_code == 200:
            with tempfile.TemporaryDirectory() as tmpdirname:
                zip_path = os.path.join(tmpdirname, "12mil.zip")
                with open(zip_path, "wb") as f:
                    f.write(response.content)

                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(tmpdirname)

                for file in os.listdir(tmpdirname):
                    if file.endswith(".shp"):
                        shp_path = os.path.join(tmpdirname, file)
                        gdf = gpd.read_file(shp_path)
                        return gdf
        else:
            st.warning("Gagal mengunduh file dari Google Drive.")
            return None
    except Exception as e:
        st.warning(f"Gagal mengunduh dan membaca shapefile dari Google Drive: {e}")
        return None

# ================================
# ===== MULAI STREAMLIT APP =====
# ================================
st.title("Konversi Koordinat dan Analisis Spasial - Verdok")

format_pilihan = st.radio("Pilih format data koordinat:", ("OSS-UTM", "General-Decimal Degree"))

if format_pilihan == "OSS-UTM":
    st.write("Format OSS-UTM dipilih. Kolom: `id`, `bujur_derajat`, `bujur_menit`, `bujur_detik`, `BT_BB`, `lintang_derajat`, `lintang_menit`, `lintang_detik`, `LU_LS`")
else:
    st.write("Format General-DD dipilih. Kolom: `id`, `x`, `y`")

uploaded_file = st.file_uploader("Unggah file Excel", type=["xlsx"])
shp_type = st.radio("Pilih tipe shapefile yang ingin dibuat:", ("Titik (Point)", "Poligon (Polygon)"))
nama_file = st.text_input("➡️Masukkan nama file shapefile (tanpa ekstensi)⬅️", value="nama_shapefile")

# Ambil data kawasan konservasi
try:
    konservasi_gdf = get_kawasan_konservasi_from_arcgis()
    if konservasi_gdf is None:
        st.warning("Gagal memuat kawasan konservasi dari ArcGIS Server.")
except Exception as e:
    konservasi_gdf = None
    st.warning(f"Gagal mengambil data dari ArcGIS Server: {e}")

# Ambil data 12 mil dari Google Drive
try:
    mil12_gdf = download_shapefile_from_gdrive("https://drive.google.com/file/d/16MnH27AofcSSr45jTvmopOZx4CMPxMKs/view?usp=sharing")
    if mil12_gdf is None:
        st.warning("Gagal memuat shapefile 12 Mil.")
except Exception as e:
    mil12_gdf = None
    st.warning(f"Gagal memproses shapefile 12 Mil: {e}")

# Proses file Excel
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

        # Cek dengan Kawasan Konservasi
        if konservasi_gdf is not None:
            joined = gpd.sjoin(gdf, konservasi_gdf[['namobj', 'geometry']], how='left', predicate='within')
            points_in_konservasi = joined[~joined['namobj'].isna()]
            if not points_in_konservasi.empty:
                st.success(f"{len(points_in_konservasi)} titik berada di dalam Kawasan Konservasi ⚠️⚠️")
                st.dataframe(points_in_konservasi[['id', 'namobj']])
            else:
                st.info("Tidak ada titik yang berada di kawasan konservasi ✅⚠️")

        # Cek dengan 12 Mil
        if mil12_gdf is not None:
            joined_mil = gpd.sjoin(gdf, mil12_gdf[['geometry']], how='left', predicate='within')
            points_in_mil = joined_mil[~joined_mil.index_right.isna()]
            if not points_in_mil.empty:
                st.success(f"{len(points_in_mil)} titik berada di dalam wilayah 12 Mil 🌊🌊")
                st.dataframe(points_in_mil[['id']])
            else:
                st.info("Tidak ada titik yang berada di dalam wilayah 12 Mil ✅")

    else:  # Polygon
        coords = list(zip(df['longitude'], df['latitude']))
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        geometry = [Polygon(coords)]
        gdf = gpd.GeoDataFrame(pd.DataFrame({"id": ["polygon_1"]}), geometry=geometry, crs="EPSG:4326")

        # Cek dengan Kawasan Konservasi
        if konservasi_gdf is not None:
            overlay_result = gpd.overlay(gdf, konservasi_gdf[['namobj', 'geometry']], how='intersection')
            if not overlay_result.empty:
                st.success("Poligon berada di dalam Kawasan Konservasi ⚠️⚠️")
                st.dataframe(overlay_result[['id', 'namobj']])
            else:
                st.info("Poligon tidak berada di kawasan konservasi ✅✅")

        # Cek dengan 12 Mil
        if mil12_gdf is not None:
            overlay_mil = gpd.overlay(gdf, mil12_gdf[['geometry']], how='intersection')
            if not overlay_mil.empty:
                st.success("Poligon berada di dalam wilayah 12 Mil 🌊🌊")
            else:
                st.info("Poligon tidak berada di dalam wilayah 12 Mil ✅")

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
