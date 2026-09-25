import streamlit as st

from common import sync_bar

st.set_page_config(page_title="Carnet de course", page_icon=":material/directions_run:", layout="wide",
                   initial_sidebar_state="collapsed")

pages = st.navigation([
    st.Page("views/today.py", title="Aujourd'hui", icon=":material/today:", default=True),
    st.Page("views/sessions.py", title="Séances", icon=":material/directions_run:"),
    st.Page("views/load.py", title="Charge", icon=":material/monitor_heart:"),
    st.Page("views/progress.py", title="Progression", icon=":material/trending_up:"),
    st.Page("views/history.py", title="Historique", icon=":material/history:"),
    st.Page("views/recovery.py", title="Récupération", icon=":material/bedtime:"),
    st.Page("views/plan.py", title="Plan", icon=":material/calendar_month:"),
    st.Page("views/library.py", title="Séances types", icon=":material/fitness_center:"),
    st.Page("views/race.py", title="Jour J", icon=":material/flag:"),
    st.Page("views/help.py", title="Aide", icon=":material/help:"),
], position="top")
sync_bar()
pages.run()
