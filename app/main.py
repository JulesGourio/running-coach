import streamlit as st

from common import sidebar

st.set_page_config(page_title="Carnet de course", page_icon=":material/directions_run:", layout="wide")

pages = st.navigation([
    st.Page("views/today.py", title="Aujourd'hui", icon=":material/today:", default=True),
    st.Page("views/sessions.py", title="Séances", icon=":material/directions_run:"),
    st.Page("views/load.py", title="Charge", icon=":material/monitor_heart:"),
    st.Page("views/progress.py", title="Progression", icon=":material/trending_up:"),
    st.Page("views/recovery.py", title="Récupération", icon=":material/bedtime:"),
    st.Page("views/plan.py", title="Plan", icon=":material/calendar_month:"),
])
sidebar()
pages.run()
