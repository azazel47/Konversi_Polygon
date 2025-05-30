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
def get_geojson_from_arcgis(url):
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

st.title("Konversi Koordinat dan Analisis Spasial - Verdok")

format_pilihan = st.radio("Pilih format data koordinat:", ("OSS-UTM", "General-DD"))

if format_pilihan == "OSS-UTM":
    st.write("Format OSS-UTM dipilih. Kolom: `id`, `bujur_derajat`, `bujur_menit`, `bujur_detik`, `BT_BB`, `lintang_derajat`, `lintang_menit`, `lintang_detik`, `LU_LS`")
else:
    st.write("Format General-DD dipilih. Kolom: `id`, `x`, `y`")

uploaded_file = st.file_uploader("Unggah file Excel", type=["xlsx"])
shp_type = st.radio("Pilih tipe shapefile yang ingin dibuat:", ("Titik (Point)", "Poligon (Polygon)"))
nama_file = st.text_input("➡️Masukkan nama file shapefile (tanpa ekstensi)⬅️", value="koordinat_shapefile")

# Load kawasan konservasi
konservasi_gdf = get_geojson_from_arcgis("https://kspservices.big.go.id/satupeta/rest/services/PUBLIK/SUMBER_DAYA_ALAM_DAN_LINGKUNGAN/MapServer/35/query")

# Load kawasan hutan (KKPRL)
kkprl_gdf = get_geojson_from_arcgis("https://utility.arcgis.com/usrsvcs/servers/ff6238a54c304ad8a0a627dd238d2171/rest/services/KKPRL/KKPRL/FeatureServer/0/query")

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

    if shp_type == "Titik (Point)":
        geometry = [Point(xy) for xy in zip(df['longitude'], df['latitude'])]
        gdf = gpd.GeoDataFrame(df[['id']], geometry=geometry, crs="EPSG:4326")

        if konservasi_gdf is not None:
            joined_konservasi = gpd.sjoin(gdf, konservasi_gdf[['namobj', 'geometry']], how='left', predicate='within')
            points_in_konservasi = joined_konservasi[~joined_konservasi['namobj'].isna()]
            if not points_in_konservasi.empty:
                st.success(f"{len(points_in_konservasi)} titik berada di dalam Kawasan Konservasi ⚠️")
                st.subheader("Kawasan Konservasi:")
                st.dataframe(points_in_konservasi[['id', 'namobj']])
            else:
                st.info("Tidak ada titik yang berada di kawasan konservasi ✅")

        if kkprl_gdf is not None:
            joined_kkprl = gpd.sjoin(gdf, kkprl_gdf[['NAMOBJ', 'geometry']], how='left', predicate='within')
            points_in_kkprl = joined_kkprl[~joined_kkprl['NAMOBJ'].isna()]
            if not points_in_kkprl.empty:
                st.warning(f"{len(points_in_kkprl)} titik berada di Kawasan Hutan (KKPRL) 🌲")
                st.subheader("Kawasan Hutan (KKPRL):")
                st.dataframe(points_in_kkprl[['id', 'NAMOBJ']])
            else:
                st.info("Tidak ada titik yang berada di kawasan hutan ✅")

    else:  # Poligon
        coords = list(zip(df['longitude'], df['latitude']))
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        geometry = [Polygon(coords)]
        gdf = gpd.GeoDataFrame(pd.DataFrame({"id": ["polygon_1"]}), geometry=geometry, crs="EPSG:4326")

        if konservasi_gdf is not None:
            overlay_konservasi = gpd.overlay(gdf, konservasi_gdf[['namobj', 'geometry']], how='intersection')
            if not overlay_konservasi.empty:
                st.success("Poligon bersinggungan dengan Kawasan Konservasi ⚠️")
                st.subheader("Kawasan Konservasi:")
                st.dataframe(overlay_konservasi[['id', 'namobj']])
            else:
                st.info("Poligon tidak bersinggungan dengan kawasan konservasi ✅")

        if kkprl_gdf is not None:
            overlay_kkprl = gpd.overlay(gdf, kkprl_gdf[['NAMOBJ', 'geometry']], how='intersection')
            if not overlay_kkprl.empty:
                st.warning("Poligon bersinggungan dengan Kawasan Hutan (KKPRL) 🌲")
                st.subheader("Kawasan Hutan (KKPRL):")
                st.dataframe(overlay_kkprl[['id', 'NAMOBJ']])
            else:
                st.info("Poligon tidak bersinggungan dengan kawasan hutan ✅")

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
