@st.cache_data
def get_kkprl_from_arcgis():
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
            st.warning(f"Gagal mengunduh data KKPRL: status code {response.status_code}")
            return None
    except Exception as e:
        st.warning(f"Gagal mengambil data KKPRL dari ArcGIS Server: {e}")
        return None


# Setelah load konservasi_gdf, load juga kkprl_gdf
try:
    konservasi_gdf = get_kawasan_konservasi_from_arcgis()
    if konservasi_gdf is None:
        st.warning("Gagal memuat kawasan konservasi dari ArcGIS Server.")
except Exception as e:
    konservasi_gdf = None
    st.warning(f"Gagal mengambil data dari ArcGIS Server: {e}")

try:
    kkprl_gdf = get_kkprl_from_arcgis()
    if kkprl_gdf is None:
        st.warning("Gagal memuat data KKPRL dari ArcGIS Server.")
except Exception as e:
    kkprl_gdf = None
    st.warning(f"Gagal mengambil data KKPRL dari ArcGIS Server: {e}")

# Di bagian setelah buat gdf dari titik atau poligon:

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

    if kkprl_gdf is not None:
        joined_kkprl = gpd.sjoin(gdf, kkprl_gdf[['geometry']], how='left', predicate='within')
        points_in_kkprl = joined_kkprl[~joined_kkprl.index_right.isna()]
        if not points_in_kkprl.empty:
            st.success(f"{len(points_in_kkprl)} titik berada di dalam area KKPRL ⚠️⚠️")
            st.subheader("Detail Titik di KKPRL")
            st.dataframe(points_in_kkprl[['id']])
        else:
            st.info("Tidak ada titik yang berada di area KKPRL ✅✅")

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

    if kkprl_gdf is not None:
        overlay_kkprl = gpd.overlay(gdf, kkprl_gdf[['geometry']], how='intersection')
        if not overlay_kkprl.empty:
            st.success("Poligon bersinggungan dengan area KKPRL ⚠️⚠️")
            st.subheader("Detail Overlay Poligon dengan KKPRL")
            st.dataframe(overlay_kkprl[['id']])
        else:
            st.info("Poligon tidak bersinggungan dengan area KKPRL ✅✅")
