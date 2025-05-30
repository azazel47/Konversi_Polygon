import streamlit as st
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, Polygon
import tempfile
import os
import zipfile
import requests
import io
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def dms_to_dd(degree, minute, second, direction):
    dd = degree + minute / 60 + second / 3600
    if direction in ["LS", "BB"]:
        dd *= -1
    return dd

# MASUKAN USERNAME & PASSWORD ArcGIS kamu di sini
username = st.secrets.get("pemetaan.kkprl", "")  # alternatif bisa langsung isi string: username = "user"
password = st.secrets.get("prlkapital1234", "")  # alternatif: password = "pass"

@st.cache_data(show_spinner=False)
def get_arcgis_token(username, password):
    url = "https://arcgis.ruanglaut.id/arcgis/tokens/generateToken"
    params = {
        'username': username,
        'password': password,
        'f': 'json',
        'client': 'requestip',
        'expiration': 60  # token berlaku 60 menit
    }
    try:
        response = requests.post(url, data=params, verify=False)
        token_json = response.json()
        if 'token' in token_json:
            return token_json['token']
        else:
            st.error(f"Gagal mendapatkan token ArcGIS: {token_json}")
            return None
    except Exception as e:
        st.error(f"Error saat generate token: {e}")
        return None

@st.cache_data(show_spinner=False)
def get_kawasan_konservasi_from_arcgis(token):
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
            geojson_str = response.text
            gdf = gpd.read_file(io.StringIO(geojson_str))
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

if not username or not password:
    st.warning("⚠️ Masukkan username dan password ArcGIS di variabel `username` dan `password` pada kode!")
else:
    token = get_arcgis_token(username, password)
    konservasi_gdf = None
    if token:
        konservasi_gdf = get_kawasan_konservasi_from_arcgis(token)
        if konservasi_gdf is None:
            st.warning("Gagal memuat kawasan konservasi dari ArcGIS Server.")
    else:
        st.warning("Token ArcGIS tidak tersedia. Tidak dapat memuat kawasan konservasi.")

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
