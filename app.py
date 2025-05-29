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
    url = "https://drive.usercontent.google.com/download?id=1ojHKKSFia2Wdh9rrMJTI5yjL2oXidjeY&export=download&confirm=t&uuid=e8e5606e-d88e-460d-812d-8079c5b68ee5"
    r = requests.get(url)
    z = zipfile.ZipFile(BytesIO(r.content))
    extract_path = "kawasan_konservasi"
    z.extractall(extract_path)
    return extract_path

st.title("Konversi Koordinat Perizinan I")

format_pilihan = st.radio("Pilih format data koordinat:", ("OSS-UTM", "General-Decimal Degree"))

if format_pilihan == "OSS-UTM":
    st.write("Format OSS-UTM dipilih. Kolom: `id`, `bujur_derajat`, `bujur_menit`, `bujur_detik`, `BT_BB`, `lintang_derajat`, `lintang_menit`, `lintang_detik`, `LU_LS`")
else:
    st.write("Format General-DD dipilih. Kolom: `id`, `x`, `y`")

uploaded_file = st.file_uploader("Unggah file Excel", type=["xlsx"])
shp_type = st.radio("Pilih tipe shapefile yang ingin dibuat:", ("Titik (Point)", "Poligon (Polygon)"))

nama_file = st.text_input("Masukkan nama file shapefile (tanpa ekstensi)", value="koordinat_shapefile")

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
    else:
        coords = list(zip(df['longitude'], df['latitude']))
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        geometry = [Polygon(coords)]
        gdf = gpd.GeoDataFrame(pd.DataFrame({"id": ["polygon_1"]}), geometry=geometry, crs="EPSG:4326")

    if konservasi_gdf is not None:
        overlay_result = gpd.overlay(gdf, konservasi_gdf, how='intersection')
        if not overlay_result.empty:
            st.success("\U0001F3DE\ufe0f Berada di dalam Kawasan Konservasi")
        else:
            st.info("\U0001F4CD Tidak berada di kawasan konservasi")

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
