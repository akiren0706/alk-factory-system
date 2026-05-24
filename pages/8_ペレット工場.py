import streamlit as st
st.set_page_config(page_title="ペレット工場", page_icon="🌿", layout="wide")
from utils.factory_view import render_factory_page
render_factory_page("ペレット工場")
