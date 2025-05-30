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

# Fungsi konversi DMS ke Decimal Degrees
def dms_to_dd(degree, minute, second, direction):
    dd = degree + minute / 60 + second / 3600
    if direction in ["LS", "BB"]:
        dd *= -1
    return dd

# Ambil data Kawasan Konservasi dari ArcGIS Server
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
            st.warning(f"Gagal mengunduh data konservasi: status code {response.status_code}")
            return None
    except Exception as e:
        st.warning(f"Gagal mengambil data konservasi: {e}")
        return None

# Ambil data Kawasan Hutan dari ArcGIS Server
@st.cache_data
def get_kawasan_hutan_from_arcgis():
    url = "https://arcgis.ruanglaut.id/arcgis/rest/services/KKPRL/KKPRL/FeatureServer/1/query"
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
            st.warning(f"Gagal mengunduh data hutan: status code {response.status_code}")
            return None
    except Exception as e:
        st.warning(f"Gagal mengambil data hutan: {e}")
        return None

# ===== Streamlit UI =====
st.title("Konversi Koordinat dan Analisis Spasial - Verdok")

format_pilihan = st.radio("Pilih format data koordinat:", ("OSS-UTM", "General-DD"))

if format_pilihan == "OSS-UTM":
    st.write("Kolom: `id`, `bujur_derajat`, `bujur_menit`, `bujur_detik`, `BT_BB`, `lintang_derajat`, `lintang_menit`, `lintang_detik`, `LU_LS`")
else:
    st.write("Kolom: `id`, `x`, `y`")

uploaded_file = st.file_uploader("Unggah file Excel", type=["xlsx"])
shp_type = st.radio("Pilih tipe shapefile yang ingin dibuat:", ("Titik (Point)", "Poligon (Polygon)"))
nama_file = st.text_input("➡️Masukkan nama file shapefile (tanpa ekstensi)⬅️", value="koordinat_shapefile")

# Load data konservasi & hutan dari ArcGIS Server
try:
    konservasi_gdf = get_kawasan_konservasi_from_arcgis()
    kawasan_hutan_gdf = get_kawasan_hutan_from_arcgis()
    if konservasi_gdf is None or kawasan_hutan_gdf is None:
        st.warning("Gagal memuat data konservasi atau kawasan hutan.")
except Exception as e:
    konservasi_gdf = None
    kawasan_hutan_gdf = None
    st.warning(f"Gagal mengambil data dari ArcGIS Server: {e}")

if uploaded_file and nama_file:
    df = pd.read_excel(uploaded_file)
    if df.shape[0] > 20:
        st.warning("Hanya 20 baris pertama yang akan diproses.")
        df = df.head(20)

    if format_pilihan == "OSS-UTM":
        df['longitude'] = df.apply(lambda row: dms_to_dd(row['bujur_derajat'], row['bujur_menit'], row['bujur_detik'], row['BT_BB']), axis=1)
        df['latitude'] = df.apply(lambda row: dms_to_dd(row['lintang_derajat'], row['lintang_menit'], row['lintang_detik'], row['LU_LS']), axis=1)
    else:
        df.rename(columns={'x': 'longitude', 'y': 'latitude'}, inplace=True)

    # Buat GeoDataFrame
    if shp_type == "Titik (Point)":
        geometry = [Point(xy) for xy in zip(df['longitude'], df['latitude'])]
        gdf = gpd.GeoDataFrame(df[['id']], geometry=geometry, crs="EPSG:4326")

        # Overlay Kawasan Konservasi
        if konservasi_gdf is not None:
            joined = gpd.sjoin(gdf, konservasi_gdf[['namobj', 'geometry']], how='left', predicate='within')
            points_in_konservasi = joined[~joined['namobj'].isna()]
            if not points_in_konservasi.empty:
                st.success(f"{len(points_in_konservasi)} titik berada di dalam Kawasan Konservasi ⚠️")
                st.subheader("Detail Kawasan Konservasi untuk Titik")
                st.dataframe(points_in_konservasi[['id', 'namobj']])
            else:
                st.info("Tidak ada titik yang berada di Kawasan Konservasi ✅")

        # Overlay Kawasan Hutan
        if kawasan_hutan_gdf is not None:
            joined_hutan = gpd.sjoin(gdf, kawasan_hutan_gdf[['NAMOBJ', 'geometry']], how='left', predicate='within')
            titik_di_hutan = joined_hutan[~joined_hutan['NAMOBJ'].isna()]
            if not titik_di_hutan.empty:
                st.success(f"{len(titik_di_hutan)} titik berada di dalam Kawasan Hutan 🌲")
                st.subheader("Detail Kawasan Hutan untuk Titik")
                st.dataframe(titik_di_hutan[['id', 'NAMOBJ']])
            else:
                st.info("Tidak ada titik di Kawasan Hutan ✅")

    else:  # Poligon
        coords = list(zip(df['longitude'], df['latitude']))
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        geometry = [Polygon(coords)]
        gdf = gpd.GeoDataFrame(pd.DataFrame({"id": ["polygon_1"]}), geometry=geometry, crs="EPSG:4326")

        # Overlay Kawasan Konservasi
        if konservasi_gdf is not None:
            overlay_result = gpd.overlay(gdf, konservasi_gdf[['namobj', 'geometry']], how='intersection')
            if not overlay_result.empty:
                st.success("Poligon bersinggungan dengan Kawasan Konservasi ⚠️")
                st.subheader("Detail Kawasan Konservasi yang bersinggungan dengan Poligon")
                st.dataframe(overlay_result[['id', 'namobj']])
            else:
                st.info("Poligon tidak bersinggungan dengan Kawasan Konservasi ✅")

        # Overlay Kawasan Hutan
        if kawasan_hutan_gdf is not None:
            overlay_hutan = gpd.overlay(gdf, kawasan_hutan_gdf[['NAMOBJ', 'geometry']], how='intersection')
            if not overlay_hutan.empty:
                st.success("Poligon bersinggungan dengan Kawasan Hutan 🌲")
                st.subheader("Detail Kawasan Hutan yang bersinggungan dengan Poligon")
                st.dataframe(overlay_hutan[['id', 'NAMOBJ']])
            else:
                st.info("Poligon tidak bersinggungan dengan Kawasan Hutan ✅")

    st.subheader("Hasil Konversi Koordinat")
    st.dataframe(df[['id', 'longitude', 'latitude']])

    # Simpan dan zip shapefile untuk didownload
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
