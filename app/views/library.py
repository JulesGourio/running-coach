import json
from datetime import date

import streamlit as st

from coach import plan_edit as pe
from coach import service
from coach import workouts as wk
from coach.text import course_text
from common import ctx, fdate, fdur, fnum, fpace, tint, type_color

s, db = ctx()
a = service.athlete(db, s)
st.title("Séances types")
st.caption("Toutes les séances de fractionné, allures calculées sur ta VMA. Personnalise-les, puis ajoute-les au plan : "
           "elles partent sur COROS depuis la page Plan, après confirmation.")

vma_ret = service.progress(db, s)["vma"].get("retenue") or 1000 / (a.threshold_pace * 0.87)


def parse_pace(txt: str, default: float) -> float:
    try:
        m, sec = str(txt).strip().split(":")
        return int(m) * 60 + int(sec)
    except ValueError:
        return default


# ---- global parameters -----------------------------------------------------------------------------------
with st.container(border=True):
    c1, c2, c3, c4 = st.columns(4)
    vma_kmh = c1.number_input("VMA (km/h)", 12.0, 24.0, round(vma_ret * 3.6, 1), 0.1, key="lib-vma",
                              help="Par défaut ta VMA d'entraînement (page Progression). Change-la pour voir les allures d'une autre VMA.")
    goal = parse_pace(c2.text_input("Allure objectif 10 km", fpace((s.goal_a or 2400) / 10), key="lib-goal"), (s.goal_a or 2400) / 10)
    thr = parse_pace(c3.text_input("Allure seuil", fpace(a.threshold_pace), key="lib-thr"), a.threshold_pace)
    walk = c4.segmented_control("Récupération", ["trottée", "marchée"], default="trottée", key="lib-walk") == "marchée"
vma = vma_kmh / 3.6
easy = pe.default_paces(a, vma)["easy"]

# ---- plan days to add a workout to -----------------------------------------------------------------------
plan = json.loads(db.get_meta("plan") or "null")
days = [d for d in db.plan_days(date.today().isoformat()) if not pe.day_is_done(d)] if plan else []
pending: dict = st.session_state.setdefault("pending", {})


def current(d: dict) -> list[dict]:
    ch = pending.get(d["date"])
    return [c for c in ch["after"] if c.get("sportType") != 4] if ch else pe.day_courses(d)


def card(w: wk.Workout) -> None:
    k = f"w-{w.key}"
    with st.container(border=True):
        with st.expander("Personnaliser", icon=":material/tune:"):
            if not w.ladder:
                cc = st.columns(3)
                reps = cc[0].number_input("Répétitions", 1, 20, w.reps, key=f"{k}-reps")
                value = cc[1].number_input("Distance (m)" if w.unit == "m" else "Durée (s)", 10, 6000, int(w.value), 10 if w.unit == "s" else 50,
                                           key=f"{k}-val")
                if w.intensity == "vma":
                    lo, hi = cc[2].slider("% de VMA", 80, 115, (int(w.lo), int(w.hi)), key=f"{k}-pct")
                elif w.intensity in ("seuil", "objectif"):
                    lo, hi = cc[2].slider(f"Écart à l'allure {'seuil' if w.intensity == 'seuil' else 'objectif'} (s/km)",
                                          -20, 20, (int(w.lo), int(w.hi)), key=f"{k}-off")
                else:
                    lo, hi = w.lo, w.hi
                cc = st.columns(3)
                rec = cc[0].number_input("Récupération", 0, 600, int(w.rec), 5, key=f"{k}-rec")
                rec_unit = cc[1].segmented_control("en", ["s", "m"], default=w.rec_unit, key=f"{k}-ru") or w.rec_unit
                sets = cc[2].number_input("Séries", 1, 4, w.sets, key=f"{k}-sets")
                set_rec = st.number_input("Récupération entre séries (s)", 0, 600, int(w.set_rec_s or 180), 30, key=f"{k}-sr") if sets > 1 else 0
                w = wk.customise(w, reps=reps, value=value, lo=lo, hi=hi, rec=rec, rec_unit=rec_unit, sets=sets, set_rec_s=set_rec)
            else:
                st.caption("Pyramide : distances et intensités fixes, seules la VMA et la récupération (trottée/marchée) changent.")
        sm = wk.summary(w, vma, thr, goal, easy, walk)
        c1, c2, c3 = st.columns([3, 2, 2], vertical_alignment="center")
        color = type_color({"Fractionné court": "VMA", "Fractionné long": "VMA", "Seuil": "Seuil",
                            "Allure spécifique 10 km": "Allure", "Côtes": "Côtes"}.get(w.category, "Fartlek"))
        c1.markdown(f"<span style='color:{color};font-weight:700'>{wk.name_of(w)}</span>", unsafe_allow_html=True)
        c1.caption(w.objective or wk.describe(w, vma, thr, goal, walk))
        lo, hi = sm["pace"]
        c2.markdown(f"**{fpace(lo)}–{fpace(hi)}/km**  \n:gray[{sm['per_rep']}]" if w.intensity != "cote"
                    else "**Effort en côte**  \n:gray[à la sensation, FC proche du seuil]")
        c2.markdown(f":{'green' if walk else 'blue'}[{sm['rec']}]")
        c3.markdown(f"≈ **{fnum(sm['total_m'] / 1000, 1)} km** · {fdur(sm['total_s'])}  \n"
                    f":gray[dont {fnum(sm['work_m'] / 1000, 1)} km d'effort]")
        if days:
            cc1, cc2 = st.columns([3, 1], vertical_alignment="bottom")
            day = cc1.selectbox("Ajouter au plan le", days, key=f"{k}-day", label_visibility="collapsed",
                                format_func=lambda d: f"{fdate(d['date'])} · à la place de : {pe.describe(current(d))}")
            if cc2.button("Ajouter au plan", key=f"{k}-add", icon=":material/event_available:", width="stretch"):
                course = wk.build(w, vma, thr, goal, easy, walk=walk)
                errs = pe.validate(course)
                if errs:
                    st.error(" ; ".join(errs))
                else:
                    pe.queue_change(pending, pe.make_change(day, [course], f"Séance type : {wk.name_of(w)}"))
                    st.toast(f"Ajoutée au {fdate(day['date'])}, en attente dans la page Plan.", icon=":material/pending_actions:")


if pending:
    st.info(f"{len(pending)} modification(s) en attente d'envoi sur COROS.", icon=":material/pending_actions:")
    st.page_link("views/plan.py", label="Voir et envoyer depuis la page Plan", icon=":material/arrow_forward:")

tabs = st.tabs(wk.CATEGORIES)
for tab, cat in zip(tabs, wk.CATEGORIES):
    with tab:
        for w in (x for x in wk.CATALOG if x.category == cat):
            card(w)
