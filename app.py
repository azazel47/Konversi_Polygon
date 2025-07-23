import streamlit as st

# Atur halaman
st.set_page_config(
    page_title="Situs Dalam Perbaikan",
    page_icon="🚧",
    layout="centered"
)

# Tampilkan pesan utama
st.markdown("""
    <div style="text-align: center; padding-top: 80px;">
        <h1 style="font-size: 3em;">🚧 Situs Sedang Dalam Perbaikan 🚧</h1>
        <p style="font-size: 1.3em; margin-top: 20px;">
            Kami sedang melakukan pemeliharaan sistem.<br>
            Silakan kunjungi kembali dalam beberapa saat.
        </p>
        <p style="margin-top: 40px; font-size: 0.9em; color: gray;">
            Silahkan menggunakan situs verdok lainnya 🙏
        </p>
    </div>
""", unsafe_allow_html=True)
