import streamlit as st
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, Polygon
import tempfile
import os
import zipfile
import requests
from io import BytesIO


def dms_to_dd(degree, minute, second, direction):
    dd = degree + minute / 60 + second / 3600
    if direction in ["LS", "BB"]:
        dd *= -1
    return dd

@st.cache_data
def download_and_extract_shapefile():
    url = "https://drive.google.com/uc?export=download&id=1VbpLlczAT0GmsCM4UKtBsD0hFvJmB8t4"
    r = requests.get(url)
    z = zipfile.ZipFile(BytesIO(r.content))
    extract_path = "kawasan_konservasi"
    z.extractall(extract_path)
    return extract_path

st.title("Konversi Koordinat DMS ke Decimal Degrees & Cek Kawasan Konservasi")

st.write("Masukkan hingga 20 koordinat dalam format berikut:")
st.markdown("**Kolom yang dibutuhkan:** `id`, `bujur_derajat`, `bujur_menit`, `bujur_detik`, `BT_BB`, `lintang_derajat`, `lintang_menit`, `lintang_detik`, `LU_LS`")

uploaded_file = st.file_uploader("Unggah file Excel", type=["xlsx"])

shp_type = st.radio("Pilih tipe shapefile yang ingin dibuat:", ("Titik (Point)", "Poligon (Polygon)"))

# Unduh dan ekstrak file SHP kawasan konservasi dari Google Drive
try:
    konservasi_path = download_and_extract_shapefile()
    konservasi_gdf = None
    for file in os.listdir(konservasi_path):
        if file.endswith(".shp"):
            konservasi_gdf = gpd.read_file(os.path.join(konservasi_path, file))
            break
    if konservasi_gdf is None:
        st.warning("File .shp tidak ditemukan dalam ZIP kawasan konservasi.")
except Exception as e:
    konservasi_gdf = None
    st.warning(f"Gagal memuat file kawasan konservasi: {e}")

if uploaded_file:
    df = pd.read_excel(uploaded_file)

    if df.shape[0] > 20:
        st.warning("Hanya 20 baris pertama yang akan diproses.")
        df = df.head(20)

    # Konversi koordinat
    df['longitude'] = df.apply(lambda row: dms_to_dd(row['bujur_derajat'], row['bujur_menit'], row['bujur_detik'], row['BT_BB']), axis=1)
    df['latitude'] = df.apply(lambda row: dms_to_dd(row['lintang_derajat'], row['lintang_menit'], row['lintang_detik'], row['LU_LS']), axis=1)

    # Buat GeoDataFrame
    if shp_type == "Titik (Point)":
        geometry = [Point(xy) for xy in zip(df['longitude'], df['latitude'])]
        gdf = gpd.GeoDataFrame(df[['id']], geometry=geometry, crs="EPSG:4326")
    else:
        coords = list(zip(df['longitude'], df['latitude']))
        if coords[0] != coords[-1]:
            coords.append(coords[0])  # pastikan poligon tertutup
        geometry = [Polygon(coords)]
        gdf = gpd.GeoDataFrame(pd.DataFrame({"id": ["polygon_1"]}), geometry=geometry, crs="EPSG:4326")

    # Overlay dengan kawasan konservasi jika tersedia
    if konservasi_gdf is not None:
        overlay_result = gpd.overlay(gdf, konservasi_gdf, how='intersection')
        if not overlay_result.empty:
            st.success("\U0001F3DE\ufe0f Berada di dalam Kawasan Konservasi")
        else:
            st.info("\U0001F4CD Tidak berada di kawasan konservasi")

    # Tampilkan hasil konversi
    st.subheader("Hasil Konversi")
    st.dataframe(df[['id', 'longitude', 'latitude']])

    # Simpan shapefile ke file sementara
    with tempfile.TemporaryDirectory() as tmpdirname:
        shp_path = os.path.join(tmpdirname, "koordinat.shp")
        gdf.to_file(shp_path)

        # Kompres ke ZIP
        zip_path = os.path.join(tmpdirname, "koordinat_shapefile.zip")
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for ext in ['shp', 'shx', 'dbf', 'cpg', 'prj']:
                fpath = shp_path.replace('.shp', f'.{ext}')
                if os.path.exists(fpath):
                    zipf.write(fpath, arcname=os.path.basename(fpath))

        # Unduhan
        with open(zip_path, "rb") as f:
            st.download_button("Unduh Shapefile (ZIP)", f, file_name="koordinat_shapefile.zip")
