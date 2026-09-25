"""Plan tab: plans other than the main COROS plan — the generator and the local drafts."""
from __future__ import annotations

import asyncio
from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from coach import plan_builder as pb
from coach import plan_edit as pe
from coach import service
from coach import workouts as wk
from coach.text import course_text
from coach.verdict import TYPE_FR, classify
from common import BLUE, MUTED, fdate, fdur, fnum, fpace, style, type_badge


def _hms(txt: str) -> float | None:
    try:
        parts = [int(x) for x in txt.strip().split(":")]
    except ValueError:
        return None
    return parts[0] * 3600 + parts[1] * 60 + parts[2] if len(parts) == 3 else parts[0] * 60 + parts[1] if len(parts) == 2 else None


def _label(c: dict, a) -> str:
    if c.get("sportType") == 4:
        return "Repos"
    if c["courseName"].startswith("COURSE"):
        return "Course"
    k = classify(c, {}, a)
    return TYPE_FR.get(k, k)


def generator(db, s) -> None:
    a = service.athlete(db, s)
    vma = service.progress(db, s)["vma"].get("retenue") or 17 / 3.6
    st.subheader("Nouveau plan", divider="gray")
    st.caption("Génère un plan complet (base, développement, spécifique, affûtage) pour une course. Il reste en brouillon "
               "ici, modifiable, et se crée dans COROS quand son début est à moins de 14 jours (règle COROS).")
    c1, c2, c3 = st.columns(3)
    goal = c1.selectbox("Objectif", list(pb.GOALS), index=2, key="g-goal")
    race = c2.date_input("Date de la course", date.today() + timedelta(weeks=24), min_value=date.today() + timedelta(weeks=4),
                         format="DD/MM/YYYY", key="g-race")
    default_t = {"5 km": "19:00", "10 km": "40:00", "Semi-marathon": "1:29:00", "Marathon": "3:15:00"}[goal]
    gt = _hms(c3.text_input("Temps visé", default_t, key=f"g-time-{goal}")) or 0
    name = st.text_input("Nom du plan", f"{goal} - {race.strftime('%d/%m/%Y')}", key=f"g-name-{goal}-{race}")
    c1, c2, c3 = st.columns(3)
    weeks = c1.slider("Semaines", 4, 16, 12 if goal in ("Semi-marathon", "Marathon") else 10, key="g-weeks")
    run_days = c2.multiselect("Jours de course", list(range(7)), default=[1, 2, 3, 5, 6], format_func=lambda d: pb.WEEKDAYS[d], key="g-days")
    long_day = c3.selectbox("Sortie longue le", sorted(run_days) or [6], index=len(run_days) - 1 if run_days else 0,
                            format_func=lambda d: pb.WEEKDAYS[d], key="g-long")
    c1, c2, c3, c4 = st.columns(4)
    quality = c1.number_input("Séances de qualité / sem.", 1, 3, 3, key="g-q", help="Sortie longue avec allure comprise à partir de 3.")
    start_km = c2.number_input("Volume de départ (km)", 15, 150, 50, 5, key="g-start")
    peak_km = c3.number_input("Volume au pic (km)", 20, 180, 70 if goal != "Marathon" else 85, 5, key="g-peak")
    vma_kmh = c4.number_input("VMA (km/h)", 12.0, 24.0, round(vma * 3.6, 1), 0.1, key="g-vma")
    if len(run_days) < 3 or not gt:
        st.warning("Au moins 3 jours de course et un temps visé au format 1:29:00.")
        return
    p = pb.Params(name=name, goal=goal, race_date=race, weeks=weeks, run_days=sorted(run_days), quality=quality,
                  start_km=start_km, peak_km=peak_km, vma=vma_kmh / 3.6, threshold_pace=a.threshold_pace, goal_time=gt,
                  long_day=long_day)
    plan = pb.build(p)
    start = date.fromisoformat(plan["start"])
    st.markdown(f"**Du {fdate(start)} au {fdate(race)}** · allure objectif **{fpace(gt / (pb.GOALS[goal] / 1000))}/km** · "
                + " → ".join(f"{x['name']} ({x['weeks']} sem.)" for x in plan["phases"]))
    rows = []
    for w in range(weeks):
        ws = start + timedelta(weeks=w)
        days = [(d, cs[0]) for d, cs in sorted(plan["days"].items()) if ws.isoformat() <= d < (ws + timedelta(days=7)).isoformat()]
        rows.append({"Semaine": f"S{w + 1}", "Du": fdate(ws), "Km": round(sum(pe.course_km(c) for _, c in days)),
                     **{pb.WEEKDAYS[d_][:3]: next((c["courseName"] for d, c in days if date.fromisoformat(d).weekday() == d_), "")
                        for d_ in range(7)}})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=min(600, 36 * len(rows) + 40))
    if st.button("Enregistrer le brouillon", type="primary", icon=":material/save:"):
        st.session_state["plan-choice-next"] = pb.save_draft(db, p, plan)
        st.rerun()


def draft_view(db, s, draft: dict) -> None:
    a = service.athlete(db, s)
    plan, prm = draft["plan"], draft["params"]
    start = date.fromisoformat(plan["start"])
    race = date.fromisoformat(prm["race_date"])
    today = date.today()
    st.subheader(prm["name"], divider="gray")
    st.caption(f"{prm['goal']} le {fdate(race)} · {plan['weeks']} semaines à partir du {fdate(start)} · "
               + " → ".join(f"{x['name']} ({x['weeks']} sem.)" for x in plan["phases"]) + f" · statut : {draft['status']}")
    st.markdown(plan["overview"])

    frm = pb.creatable_from(draft)
    c1, c2 = st.columns([3, 1], vertical_alignment="center")
    if draft["status"] != "brouillon":
        c1.success("Plan créé dans COROS.", icon=":material/cloud_done:")
    elif today < frm:
        c1.info(f"COROS accepte un plan qui démarre dans les 14 jours : envoi possible à partir du **{fdate(frm)}**.",
                icon=":material/schedule:")
    elif start < today:
        c1.warning("La date de début est passée : régénère le plan avec une date plus lointaine.")
    else:
        c1.markdown("Prêt à être créé dans COROS.")
        if c2.button("Créer dans COROS", type="primary", icon=":material/cloud_upload:", width="stretch"):
            _confirm_create(db, s, draft)
    if c2.button("Supprimer le brouillon", icon=":material/delete:", width="stretch", key="del-draft"):
        pb.delete_draft(db, draft["id"])
        st.session_state["plan-choice-next"] = "main"
        st.rerun()

    vols = []
    for w in range(plan["weeks"]):
        ws = start + timedelta(weeks=w)
        vols.append(sum(pe.course_km(c) for d, cs in plan["days"].items() for c in cs
                        if ws.isoformat() <= d < (ws + timedelta(days=7)).isoformat()))
    fig = go.Figure(go.Bar(x=[f"S{i + 1}" for i in range(len(vols))], y=vols, marker_color=BLUE,
                           hovertemplate="%{x} : %{y:.0f} km<extra></extra>"))
    style(fig, 240).update_layout(title="Volume prévu par semaine (km)", showlegend=False, hovermode="closest")
    st.plotly_chart(fig, width="stretch")

    week = st.select_slider("Semaine", options=list(range(plan["weeks"])), value=0, format_func=lambda i: f"S{i + 1}", key=f"dw-{draft['id']}")
    ws = start + timedelta(weeks=week)
    vma = prm["vma"]
    goal_pace = prm["goal_time"] / (pb.GOALS[prm["goal"]] / 1000)
    easy = (int(5 * round(1000 / (vma * 0.72) / 5)), int(5 * round(1000 / (vma * 0.64) / 5)))
    for i in range(7):
        d = ws + timedelta(days=i)
        k = d.isoformat()
        cs = plan["days"].get(k, [])
        with st.container(border=True):
            c1, c2, c3 = st.columns([1.2, 6, 2], vertical_alignment="center")
            c1.markdown(f"**{fdate(d).split()[0].capitalize()}**  \n:gray[{d.day} {fdate(d).split()[2]}]")
            if cs:
                c2.markdown(f"{type_badge(_label(cs[0], a))} :gray[≈ {fnum(sum(pe.course_km(c) for c in cs), 1)} km]  \n"
                            + "  \n".join(f"**{c['courseName']}** · :gray[{course_text(c)}]" for c in cs))
            else:
                c2.markdown(type_badge("Repos"))
            with c3.popover("Remplacer", icon=":material/swap_horiz:", width="stretch"):
                opts = ["repos", "footing", "footing_acc", "longue", *[w.key for w in wk.CATALOG]]
                names = {"repos": "Repos", "footing": "Footing", "footing_acc": "Footing + accélérations", "longue": "Sortie longue",
                         **{w.key: f"{w.category} · {wk.name_of(w)}" for w in wk.CATALOG}}
                choice = st.selectbox("Séance", opts, format_func=names.get, key=f"dr-{k}")
                km = st.number_input("Km", 3.0, 40.0, 8.0 if choice != "longue" else 16.0, 0.5, key=f"dk-{k}") \
                    if choice in ("footing", "footing_acc", "longue") else None
                if st.button("Valider", key=f"dv-{k}", type="primary"):
                    if choice == "repos":
                        new = []
                    elif km is not None:
                        new = [pe.build(choice, {"km": km, "easy": easy})]
                    else:
                        new = [wk.build(wk.by_key(choice), vma, prm["threshold_pace"], goal_pace, easy)]
                    pb.set_draft_day(db, draft["id"], k, new)
                    st.rerun()


@st.dialog("Créer le plan dans COROS")
def _confirm_create(db, s, draft: dict) -> None:
    plan = draft["plan"]
    st.markdown(f"**{draft['params']['name']}** · {plan['weeks']} semaines à partir du {fdate(date.fromisoformat(plan['start']))}.  \n"
                "Le plan démarre automatiquement à cette date dans COROS (et sur ta montre).")
    principal = service.plan_meta(db)
    if principal and principal.get("end") and principal["end"] >= plan["start"]:
        st.warning(f"Il chevauche le plan en cours (jusqu'au {fdate(date.fromisoformat(principal['end']))}) : les deux "
                   "apparaîtront dans le calendrier sur la période commune.")
    if st.button("Confirmer la création", type="primary"):
        from coach.sources.coros_mcp import describe
        try:
            with st.spinner("Création dans COROS…"):
                msg = asyncio.run(pb.create_in_coros(s, db, draft["id"]))
            st.success(msg or "Plan créé.")
        except pe.PlanError as e:
            st.error(str(e))
        except Exception as e:  # noqa: BLE001
            st.error(f"COROS a refusé ou n'a pas répondu : {describe(e)}")
