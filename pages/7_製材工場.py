import streamlit as st
st.set_page_config(page_title="製材工場", page_icon="🪚", layout="wide")
from utils.factory_view import render_factory_page
render_factory_page("製材工場")
