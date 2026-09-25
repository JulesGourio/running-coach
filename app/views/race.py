from datetime import date, time

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from coach import plan_edit as pe
from coach import raceplan as rp
from coach import service
from common import BLUE, ctx, fdate, fdur, fnum, fpace, pace_ticks, route_map, style

s, db = ctx()
st.title("Jour J")
race_day = date.fromisoformat(s.goal_date) if s.goal_date else date.today()
D = s.goal_distance_m
st.caption(f"{s.goal_label} le {fdate(race_day)} · J-{(race_day - date.today()).days}")


def parse_time(txt: str) -> float | None:
    try:
        parts = [int(x) for x in txt.strip().split(":")]
    except ValueError:
        return None
    return parts[0] * 3600 + parts[1] * 60 + parts[2] if len(parts) == 3 else parts[0] * 60 + parts[1] if len(parts) == 2 else None


# ---- target, course, weather -------------------------------------------------------------------------------
pr = service.progress(db, s)
targets = {f"Objectif A ({fdur(s.goal_a)})": s.goal_a, f"Objectif B ({fdur(s.goal_b)})": s.goal_b}
if pr.get("projection"):
    targets[f"Projection au jour J ({fdur(pr['projection']['projected'])})"] = pr["projection"]["projected"]
targets["Autre temps"] = None
c1, c2 = st.columns([2, 1])
tgt_label = c1.radio("Temps visé", list(targets), horizontal=True, key="rp-target")
target = targets[tgt_label] or parse_time(c2.text_input("Temps (min:s ou h:min:s)", fdur(s.goal_a), key="rp-custom")) or s.goal_a

c1, c2 = st.columns([2, 1])
src = c1.radio("Parcours", ["Plat", "Fichier GPX", "Une de mes sorties"], horizontal=True, key="rp-src",
               help="Charge le GPX officiel de la course, ou choisis une de tes sorties faite sur le parcours.")
course = None
if src == "Une de mes sorties":
    runs = [x for x in service.sessions(db, 3650) if x.get("distance_km") and x["distance_km"] >= D / 1000 * 0.6]
    near = sorted(runs, key=lambda x: abs(x["distance_km"] - D / 1000))
    pick = c2.selectbox("Sortie", near[:60], format_func=lambda x: f"{fdate(x['date'])} · {x['name']} ({fnum(x['distance_km'], 1)} km)",
                        key="rp-run")
    if pick:
        d = service.session_detail(db, pick["label_id"], with_records=True)
        if d and d.get("records") is not None and len(d["records"]):
            course = rp.course_from_records(d["records"])
elif src == "Fichier GPX":
    up = c2.file_uploader("Trace GPX du parcours", type=["gpx"], key="rp-gpx")
    if up:
        course = rp.course_from_gpx(up.getvalue())
if course is None or len(course) < 2:
    course = rp.flat_course(D)
    if src != "Plat":
        st.caption("Pas de parcours chargé : calcul sur un parcours plat.")
prof = rp.km_profile(course, D)

st.subheader("Météo", divider="gray")
c1, c2, c3 = st.columns([1, 1, 2])
start = c1.time_input("Heure de départ", time(10, 0), step=900, key="rp-hour")
auto = c2.toggle("Météo automatique", value=True, key="rp-auto", help="Open-Meteo : prévision à moins de 16 jours, sinon la "
                                                                     "météo observée à cette date les 3 années précédentes.")
lat = course["lat"].dropna().iloc[0] if course["lat"].notna().any() else 43.6
lon = course["lon"].dropna().iloc[0] if course["lon"].notna().any() else 1.44


@st.cache_data(ttl=3600, show_spinner="Météo Open-Meteo…")
def get_weather(la, lo, day, hour):
    return rp.weather(la, lo, day, hour)


wx = None
if auto:
    try:
        wx = get_weather(round(lat, 2), round(lon, 2), race_day, start.hour)
        c3.markdown(f"**{fnum(wx['temp'], 0)} °C**, humidité {wx['humidity']:.0f} %, vent {fnum(wx['wind'] * 3.6, 0)} km/h "
                    f"venant du {int(wx['wind_dir'])}°  \n:gray[{wx['source']}"
                    + (f", entre {fnum(wx['temp_range'][0], 0)} et {fnum(wx['temp_range'][1], 0)} °C selon les années" if wx.get("temp_range") else "")
                    + "]")
    except Exception as e:  # noqa: BLE001
        c3.warning(f"Météo indisponible ({e}) : saisis-la à la main.")
if not auto or wx is None:
    cc = st.columns(4)
    wx = {"source": "saisie", "temp": cc[0].number_input("Température (°C)", -10.0, 40.0, 8.0, 1.0, key="rp-t"),
          "humidity": cc[1].number_input("Humidité (%)", 0, 100, 75, 5, key="rp-h"),
          "wind": cc[2].number_input("Vent (km/h)", 0.0, 60.0, 10.0, 1.0, key="rp-w") / 3.6,
          "wind_dir": cc[3].number_input("Venant de (°, 0 = nord)", 0, 359, 300, 15, key="rp-wd")}
mode = st.segmented_control("Stratégie", ["Temps réaliste avec la météo", "Tenir le temps visé"], default="Temps réaliste avec la météo",
                            key="rp-mode") or "Temps réaliste avec la météo"
res = rp.plan(prof, target, wx, start_conservative=True, weather_adjusted=mode.startswith("Temps réaliste"))
flat_calm = rp.plan(prof.assign(cost=1.0, bearing=None), target, None, start_conservative=False)

# ---- result ------------------------------------------------------------------------------------------------
st.subheader("Plan de course", divider="gray")
with st.container(horizontal=True):
    st.metric("Temps prévu", fdur(res["total"]), border=True, delta=f"{fpace(res['total'] / (D / 1000))}/km en moyenne", delta_color="off")
    st.metric("Effet de la chaleur", f"+{fnum(res['heat'] * 100, 1)} %" if res["heat"] else "aucun", border=True,
              delta=f"+{fdur(target * res['heat'])}" if res["heat"] else None, delta_color="off",
              help="Au-delà d'environ 12 °C, chaque degré coûte ~0,3 % de temps, un peu plus par temps humide.")
    st.metric("Effet du vent", f"{res['wind_effect'] * 100:+.1f} %".replace(".", ","), border=True,
              help="Vent de face : ~2 % par m/s sur le km concerné ; vent de dos : environ la moitié en gain.")
    st.metric("Dénivelé", f"+{prof['climb'].clip(lower=0).sum():.0f} m / {prof['climb'].clip(upper=0).sum():.0f} m", border=True)
if mode.startswith("Tenir"):
    st.caption("Tu tiens le temps visé quelles que soient les conditions : l'effort sera plus élevé si la météo est défavorable.")
else:
    st.caption("Le temps visé correspond à des conditions idéales (frais, sans vent) ; le plan ajoute ce que coûtent la chaleur et le vent.")

r = res["rows"]
colors = ["#dc2626" if p_ < res["base_pace"] - 2 else "#2e6fdb" if p_ > res["base_pace"] + 2 else "#64748b" for p_ in r["pace"]]
fig = go.Figure()
fig.add_scatter(x=r["km"], y=r["pace"], mode="lines+markers+text", line=dict(color="#94a3b8", width=2),
                marker=dict(size=13, color=colors), text=r["pace"].map(fpace), textposition="top center",
                customdata=list(zip(r["pace"].map(fpace), r["split"].map(fdur), (r["grade"] * 100).round(1))),
                hovertemplate="km %{x} · %{customdata[0]}/km · passage %{customdata[1]} · pente %{customdata[2]} %<extra></extra>")
fig.add_hline(y=res["base_pace"], line=dict(color="#94a3b8", dash="dot"), annotation_text=f"allure sur plat {fpace(res['base_pace'])}",
              annotation_position="bottom right")
style(fig, 300, "pace").update_layout(title="Allure par km (rouge : plus vite que l'allure sur plat, bleu : plus lent)",
                                      xaxis=dict(title="km", dtick=1), showlegend=False, hovermode="closest")
pace_ticks(fig, list(r["pace"]) + [res["base_pace"]])
st.plotly_chart(fig, width="stretch")

wind_txt = []
for b in r["bearing"]:
    f_ = rp.wind_factor(wx.get("wind", 0), wx.get("wind_dir"), b)
    wind_txt.append("face" if f_ > 1.01 else "dos" if f_ < 0.995 else "—")
st.dataframe(pd.DataFrame({"Km": r["km"], "Allure": r["pace"].map(lambda v: f"{fpace(v)}/km"), "Passage": r["split"].map(fdur),
                           "Pente": (r["grade"] * 100).round(1).map(lambda v: f"{v:+.1f} %".replace(".", ",")),
                           "Vent": wind_txt}), hide_index=True, width="stretch")

if course["lat"].notna().sum() > 10:
    c = course.dropna(subset=["lat", "lon"])
    c = c.iloc[:: max(1, len(c) // 800)]
    km_idx = (c["dist"] / max(c["dist"].iloc[-1], 1) * D // 1000).clip(upper=len(r) - 1).astype(int)
    pace_pts = r["pace"].to_numpy()[km_idx]
    st.plotly_chart(route_map(c["lat"], c["lon"], pace_pts, "allure", [f"km {k + 1} · {fpace(p_)}/km" for k, p_ in zip(km_idx, pace_pts)],
                              height=380), width="stretch")

# ---- to the watch ------------------------------------------------------------------------------------------
race_row = next((d for d in db.plan_days(race_day.isoformat(), race_day.isoformat())), None)
if race_row and not pe.day_is_done(race_row):
    if st.button("Mettre ce plan sur la montre le jour J", type="primary", icon=":material/watch:"):
        pending = st.session_state.setdefault("pending", {})
        pe.queue_change(pending, pe.make_change(race_row, [rp.watch_course(res, s.goal_label)], "Plan de course km par km"))
        st.toast("Mis en attente : envoie-le depuis la page Plan.", icon=":material/pending_actions:")
    st.caption("La séance du jour de course dans COROS sera remplacée par ce plan, un segment par km avec son allure.")
