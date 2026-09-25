import pandas as pd
import streamlit as st

from coach import service
from common import ctx, fdate, fnum

s, db = ctx()
st.title("Plan")
meta = service.plan_meta(db)
if meta:
    st.caption(f"{meta['name']} · du {fdate(meta['start'])} au {fdate(meta['end'])}")
    if meta.get("phases"):
        st.markdown(" → ".join(f"**{p['name']}** ({p['weeks']} sem.)" for p in meta["phases"]))
else:
    st.info("Aucun plan COROS synchronisé.")

back = st.slider("Jours passés", 0, 28, 14)
days = service.plan_view(db, s, back=back, ahead=21)
if not days:
    st.stop()

done = [d for d in days if d["date"] < pd.Timestamp.today().strftime("%Y-%m-%d") and d["status"] in ("faite", "manquée")]
if done:
    ok = sum(1 for d in done if d["status"] == "faite")
    scores = [x["score"] for d in done for x in d["done"] if x["score"] is not None]
    k = st.columns(2)
    k[0].metric("Séances réalisées", f"{ok}/{len(done)}")
    k[1].metric("Note moyenne", fnum(sum(scores) / len(scores)) if scores else "—")

icons = {"faite": "✓ faite", "manquée": "✗ manquée", "à venir": "à venir", "repos": "repos"}
rows = []
for d in days:
    rows.append({
        "Date": fdate(d["date"]),
        "Statut": icons.get(d["status"], d["status"]),
        "Prévu": " + ".join(c["name"] for c in d["courses"]) or "Repos",
        "Détail": " + ".join(c["summary"] for c in d["courses"]),
        "Réalisé": " + ".join(f"{x['name'] or ''} ({fnum(x['distance_km'])} km)" for x in d["done"]),
        "Note": next((x["score"] for x in d["done"] if x["score"] is not None), None),
    })
st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=min(900, 38 * len(rows) + 40),
             column_config={"Note": st.column_config.ProgressColumn("Note", min_value=0, max_value=10, format="%.1f")})
st.caption("Pour modifier une séance, demande-le à Claude : il utilise le connecteur COROS et met à jour ton calendrier.")
