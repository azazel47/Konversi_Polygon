import streamlit as st
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, Polygon
import tempfile
import os
import zipfile
import requests
import io

st.set_page_config(page_title="Konversi Koordinat dan Analisis Spasial - Verdok", layout="wide")

def dms_to_dd(degree, minute, second, direction):
    dd = degree + minute / 60 + second / 3600
    if direction in ["LS", "BB"]:
        dd *= -1
    return dd

@st.cache_data
def get_kawasan_konservasi_from_arcgis(token):
    if not token:
        st.warning("Token belum dimasukkan.")
        return None
    url = "https://arcgis.ruanglaut.id/arcgis/rest/services/KKPRL/KKPRL/MapServer/1/query"
    params = {
        "where": "1=1",
        "outFields": "*",
        "f": "geojson",
        "token": token
    }
    try:
        response = requests.get(url, params=params, verify=False)
        if response.status_code == 200:
            gdf = gpd.read_file(io.StringIO(response.text))
            return gdf
        else:
            st.warning(f"Gagal mengunduh data: status code {response.status_code}")
            st.write("Response content:", response.text)
            return None
    except Exception as e:
        st.warning(f"Gagal mengambil data dari ArcGIS Server: {e}")
        return None

st.title("Konversi Koordinat dan Analisis Spasial - Verdok")

st.markdown("""
Masukkan **token ArcGIS** yang sudah kamu dapatkan dari [https://arcgis.ruanglaut.id/arcgis/tokens/](https://arcgis.ruanglaut.id/arcgis/tokens/) untuk mengakses data Kawasan Konservasi.
""")

token = st.text_input("Masukkan token ArcGIS", type="password")

format_pilihan = st.radio("Pilih format data koordinat:", ("OSS-UTM", "General-DD"))

if format_pilihan == "OSS-UTM":
    st.write("Format OSS-UTM dipilih. Kolom: `id`, `bujur_derajat`, `bujur_menit`, `bujur_detik`, `BT_BB`, `lintang_derajat`, `lintang_menit`, `lintang_detik`, `LU_LS`")
else:
    st.write("Format General-DD dipilih. Kolom: `id`, `x`, `y`")

uploaded_file = st.file_uploader("Unggah file Excel", type=["xlsx"])
shp_type = st.radio("Pilih tipe shapefile yang ingin dibuat:", ("Titik (Point)", "Poligon (Polygon)"))

nama_file = st.text_input("➡️Masukkan nama file shapefile (tanpa ekstensi)⬅️", value="koordinat_shapefile")

konservasi_gdf = get_kawasan_konservasi_from_arcgis(token)

if konservasi_gdf is not None:
    st.success(f"Berhasil memuat {len(konservasi_gdf)} fitur kawasan konservasi")

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

        if konservasi_gdf is not None:
            # Spatial join untuk menambahkan atribut 'namobj' kawasan konservasi ke tiap titik jika ada
            joined = gpd.sjoin(gdf, konservasi_gdf[['namobj', 'geometry']], how='left', predicate='within')
            points_in_konservasi = joined[~joined['namobj'].isna()]

            if not points_in_konservasi.empty:
                st.success(f"{len(points_in_konservasi)} titik berada di dalam Kawasan Konservasi ⚠️⚠️")
                st.subheader("Detail Kawasan Konservasi untuk Titik")
                st.dataframe(points_in_konservasi[['id', 'namobj']])
            else:
                st.info("Tidak ada titik yang berada di kawasan konservasi ✅✅")

    else:
        coords = list(zip(df['longitude'], df['latitude']))
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        geometry = [Polygon(coords)]
        gdf = gpd.GeoDataFrame(pd.DataFrame({"id": ["polygon_1"]}), geometry=geometry, crs="EPSG:4326")

        if konservasi_gdf is not None:
            overlay_result = gpd.overlay(gdf, konservasi_gdf[['namobj', 'geometry']], how='intersection')
            if not overlay_result.empty:
                st.success("Poligon berada di dalam Kawasan Konservasi ⚠️⚠️")
                st.subheader("Detail Kawasan Konservasi yang bersinggungan dengan Poligon")
                st.dataframe(overlay_result[['id', 'namobj']])
            else:
                st.info("Poligon tidak berada di kawasan konservasi ✅✅")

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
