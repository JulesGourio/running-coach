import asyncio
import json
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from coach import plan_edit as pe
from coach import service
from coach.text import course_text
from coach.verdict import TYPE_FR, classify
from common import ctx, fdate, fnum, fpace, type_badge

s, db = ctx()
a = service.athlete(db, s)
today = date.today()
st.title("Plan")


def reload_plan() -> None:
    from coach.sources.coros_mcp import CorosMCP, NeedsLogin, describe
    from coach.sync import refresh_plan

    async def run():
        async with CorosMCP(s) as c:
            return await refresh_plan(c, db)
    try:
        with st.spinner("Lecture du plan COROS…"):
            asyncio.run(run())
        st.toast("Plan rechargé depuis COROS.", icon=":material/check_circle:")
    except NeedsLogin as e:
        st.warning(f"{e}\n\nLance la commande dans le terminal, puis réessaie.")
    except Exception as e:  # noqa: BLE001
        st.error(f"Lecture impossible : {describe(e)}")


plan = json.loads(db.get_meta("plan") or "null")
if not plan:
    st.info("Aucun plan COROS synchronisé.")
    if st.button("Charger le plan depuis COROS", icon=":material/download:"):
        reload_plan()
        st.rerun()
    st.stop()

pending: dict = st.session_state.setdefault("pending", {})
vma = service.progress(db, s)["vma"].get("fractionnes")
P = pe.default_paces(a, vma, s.goal_a, s.goal_b)
start, end = date.fromisoformat(plan["start"]), date.fromisoformat(plan["end"])
n_weeks = plan.get("weeks") or (end - start).days // 7 + 1
phases = json.loads(db.get_meta("phases") or "[]")
stored = {d["date"]: d for d in db.plan_days(plan["start"], plan["end"])}


# ---- helpers ----------------------------------------------------------------------------------------

def effective(day: dict) -> list[dict]:
    """The day's courses including a queued change."""
    ch = pending.get(day["date"])
    return [c for c in ch["after"] if c.get("sportType") != 4] if ch else pe.day_courses(day)


def editable(day: dict | None) -> bool:
    return bool(day) and day["date"] >= today.isoformat() and not pe.day_is_done(day)


def kind_label(courses: list[dict]) -> str:
    c = next((x for x in courses if x.get("sportType") != 4), None)
    if not c:
        return "Repos"
    k = classify(c, {}, a)
    return TYPE_FR.get(k, k)


def queue(changes: list[dict]) -> None:
    for ch in changes:
        pe.queue_change(pending, ch)


def phase_of(d: date) -> str:
    return next((p["name"] for p in phases if p["start"] <= d.isoformat() <= p["end"]), "")


def parse_pace(txt: str) -> int | None:
    try:
        m, sec = str(txt).strip().replace("'", ":").split(":")
        v = int(m) * 60 + int(sec)
        return v if 120 <= v <= 1499 else None
    except ValueError:
        return None


def pace_pair(label: str, default: tuple[float, float], key: str) -> tuple[int, int]:
    c1, c2 = st.columns(2)
    lo = parse_pace(c1.text_input(f"{label} : de (min:s/km)", fpace(default[0]), key=f"{key}-lo"))
    hi = parse_pace(c2.text_input("à", fpace(default[1]), key=f"{key}-hi"))
    if lo is None or hi is None:
        st.error("Allure au format 4:05, entre 2:00 et 24:59/km.")
        return int(default[0]), int(default[1])
    return lo, hi


def preview(courses: list[dict]) -> None:
    if not courses:
        st.markdown("→ **Repos**")
    for c in courses:
        st.markdown(f"→ **{c['courseName']}** · ≈ {fnum(pe.course_km(c), 1)} km  \n{course_text(c)}")


DEFAULT_TPL = {"Footing": "footing", "Sortie longue": "longue", "Sortie longue avec allure spécifique": "longue_allure",
               "VMA / VO2max": "vma", "Seuil": "seuil", "Allure spécifique": "allure"}


def template_form(tpl: str, cur: list[dict]) -> dict:
    km_now = round(sum(pe.course_km(c) for c in cur))
    k = f"f-{tpl}"
    if tpl == "repos":
        return {}
    if tpl in ("footing", "footing_acc"):
        km = st.number_input("Distance (km)", 3.0, 30.0, float(km_now if 5 <= km_now <= 16 else 9), 0.5, key=f"{k}-km")
        p = {"km": km, "easy": pace_pair("Allure", P["easy"], k)}
        if tpl == "footing_acc":
            p["strides"] = st.number_input("Accélérations de 100 m", 3, 10, 6, key=f"{k}-n")
        return p
    if tpl == "vma":
        c1, c2 = st.columns(2)
        reps = c1.number_input("Répétitions", 1, 20, 8, key=f"{k}-reps")
        rep_m = c2.selectbox("Distance de chaque répétition (m)", [200, 300, 400, 500, 600, 800, 1000, 1200, 1500], index=2, key=f"{k}-m")
        pace = pace_pair("Allure", P["vma_short"] if rep_m <= 500 else P["vma_long"], f"{k}-{rep_m}")
        c1, c2 = st.columns(2)
        unit = c2.radio("Récupération en", ["m", "s"], horizontal=True, key=f"{k}-u")
        rec = c1.number_input("Récupération trottée", 30, 600, 200 if unit == "m" else 90, key=f"{k}-rec-{unit}")
        return {"reps": reps, "rep_m": rep_m, "pace": pace, "rec": rec, "rec_unit": unit, "easy": P["easy"]}
    if tpl == "allure":
        c1, c2 = st.columns(2)
        reps = c1.number_input("Répétitions", 1, 20, 4, key=f"{k}-reps")
        rep_m = c2.selectbox("Distance (m)", [1000, 1500, 2000, 2500, 3000, 4000], index=2, key=f"{k}-m")
        pace = pace_pair("Allure objectif", P["allure"], k)
        rec = st.number_input("Récupération trottée (s)", 30, 600, 120, key=f"{k}-rec")
        return {"reps": reps, "rep_m": rep_m, "pace": pace, "rec": rec, "rec_unit": "s", "easy": P["easy"]}
    if tpl == "seuil":
        c1, c2 = st.columns(2)
        blocks = c1.number_input("Blocs", 1, 6, 2, key=f"{k}-b")
        mins = c2.number_input("Minutes par bloc", 5, 45, 15, key=f"{k}-min")
        pace = pace_pair("Allure seuil", P["seuil"], k)
        rec = st.number_input("Récupération entre blocs (s)", 30, 600, 180, key=f"{k}-rec") if blocks > 1 else 0
        return {"blocks": blocks, "block_min": mins, "pace": pace, "rec": rec, "easy": P["easy"]}
    if tpl == "longue":
        km = st.number_input("Distance (km)", 8.0, 40.0, float(km_now if km_now >= 12 else 16), 0.5, key=f"{k}-km")
        return {"km": km, "easy": pace_pair("Allure", (P["easy"][0], P["easy"][1] - 5), k)}
    if tpl == "longue_allure":
        c1, c2 = st.columns(2)
        km = c1.number_input("Distance totale (km)", 8.0, 40.0, float(km_now if km_now >= 12 else 18), 0.5, key=f"{k}-km")
        fast = c2.number_input("dont en allure (km)", 1.0, 20.0, 5.0, 0.5, key=f"{k}-fast")
        pace = pace_pair("Allure de la partie rapide", P["allure"], k)
        return {"km": km, "fast_km": fast, "pace": pace, "easy": P["easy"]}
    return {}


@st.dialog("Modifier la séance", width="large")
def editor(day: dict) -> None:
    cur = effective(day)
    st.markdown(f"**{fdate(day['date'])}** · {type_badge(kind_label(cur))} {pe.describe(cur)}")
    t_adj, t_new, t_move = st.tabs([":material/tune: Ajuster", ":material/swap_horiz: Remplacer", ":material/event: Déplacer"])
    with t_adj:
        if not cur:
            st.info("Jour de repos : utilise « Remplacer » pour y mettre une séance.")
        else:
            vol = st.slider("Volume", 50, 150, 100, 5, format="%d %%",
                            help="Distances, durées et nombre de répétitions. L'échauffement, le retour au calme et les accélérations ne changent pas.")
            shift = st.slider("Allures de qualité (s/km)", -15, 15, 0,
                              help="Négatif = plus vite. Seules les parties rapides bougent, pas l'endurance.")
            new = [pe.shift_paces(pe.scale(c, vol / 100), shift, a.threshold_pace) for c in cur]
            preview(new)
            if st.button("Ajouter aux modifications", key="adj", type="primary", disabled=vol == 100 and shift == 0):
                why = [f"volume {vol} %"] if vol != 100 else []
                why += [f"allures {shift:+d} s/km"] if shift else []
                queue([pe.make_change(day, new, "Ajustement : " + ", ".join(why))])
                st.rerun()
    with t_new:
        keys = list(pe.TEMPLATES)
        default = DEFAULT_TPL.get(kind_label(cur), "footing")
        tpl = st.selectbox("Type de séance", keys, index=keys.index(default), format_func=pe.TEMPLATES.get)
        params = template_form(tpl, cur)
        try:
            new, errs = pe.build(tpl, params), []
            errs = pe.validate(new)
        except (pe.PlanError, KeyError) as e:
            new, errs = None, [str(e)]
        if new is not None:
            preview([] if new.get("sportType") == 4 else [new])
        for e in errs:
            st.error(e)
        if st.button("Ajouter aux modifications", key="new", type="primary", disabled=bool(errs) or new is None):
            queue([pe.make_change(day, [new], f"Remplacée : {pe.TEMPLATES[tpl]}")])
            st.rerun()
    with t_move:
        d0 = date.fromisoformat(day["date"])
        others = [d for k_, d in sorted(stored.items()) if d is not day and editable(d)
                  and abs((date.fromisoformat(k_) - d0).days) <= 10]
        if not others:
            st.info("Aucun autre jour modifiable dans les 10 jours autour.")
        else:
            target = st.selectbox("Échanger avec", others,
                                  format_func=lambda d: f"{fdate(d['date'])} · {pe.describe(effective(d))}")
            st.caption("Les deux jours échangent leurs séances (un repos compte comme une séance).")
            if st.button("Échanger les deux jours", key="swap", type="primary"):
                cur_t = effective(target)
                queue([pe.make_change(day, cur_t or [pe.REST], "Séances interverties"),
                       pe.make_change(target, cur or [pe.REST], "Séances interverties")])
                st.rerun()


@st.dialog("Envoyer sur COROS")
def confirm_push() -> None:
    changes = sorted(pending.values(), key=lambda c: c["date"])
    st.markdown(f"**{len(changes)} jour{'s' if len(changes) > 1 else ''}** vont être réécrits dans ton plan COROS "
                "(et donc sur ta montre). Les jours déjà réalisés ne sont jamais modifiés.")
    for ch in changes:
        st.markdown(f"- **{fdate(ch['date'])}** : {pe.describe(ch['after'])}")
    if st.button("Confirmer l'envoi", type="primary", icon=":material/cloud_upload:"):
        from coach.sources.coros_mcp import NeedsLogin, describe
        try:
            with st.spinner("Écriture dans COROS…"):
                res = asyncio.run(pe.push_changes(s, db, changes))
            pending.clear()
            st.session_state["push_result"] = res
            st.rerun()
        except NeedsLogin as e:
            st.warning(f"{e}\n\nLance la commande dans le terminal, puis réessaie.")
        except pe.PlanError as e:
            st.error(str(e))
        except Exception as e:  # noqa: BLE001
            st.error(f"COROS a refusé ou n'a pas répondu : {describe(e)}. Vérifie le plan (bouton « Recharger ») avant de réessayer.")


# ---- result of the last push ------------------------------------------------------------------------
res = st.session_state.pop("push_result", None)
if res:
    st.success(f"Plan mis à jour dans COROS : {len(res['applied'])} jour(s) modifié(s)."
               + (f" {len(res['skipped'])} jour(s) déjà réalisé(s) laissé(s) tel(s) quel(s)." if res["skipped"] else ""),
               icon=":material/cloud_done:")

# ---- header -----------------------------------------------------------------------------------------
cur_week = min(max((today - start).days // 7, 0), n_weeks - 1)
h1, h2 = st.columns([4, 1], vertical_alignment="bottom")
h1.caption(f"{plan['name']} · du {fdate(start)} au {fdate(end)} · "
           + " → ".join(f"**{p['name']}** ({p['weeks']} sem.)" for p in phases))
if h2.button("Recharger", icon=":material/sync:", help="Relit le plan complet depuis COROS."):
    reload_plan()
    st.rerun()

# ---- pending changes --------------------------------------------------------------------------------
if pending:
    with st.container(border=True):
        st.markdown(f"#### :orange[:material/pending_actions:] Modifications en attente ({len(pending)})")
        st.dataframe(pd.DataFrame([{"Jour": fdate(ch["date"]), "Avant": pe.describe(ch["before"]),
                                    "Après": pe.describe(ch["after"]), "Raison": ch["reason"]}
                                   for ch in sorted(pending.values(), key=lambda c: c["date"])]),
                     hide_index=True, width="stretch")
        b1, b2, _ = st.columns([2, 1, 3])
        if b1.button("Envoyer sur COROS", type="primary", icon=":material/cloud_upload:", width="stretch"):
            confirm_push()
        if b2.button("Tout annuler", width="stretch"):
            pending.clear()
            st.rerun()

# ---- suggestions ------------------------------------------------------------------------------------
sugg = pe.suggestions(db, s)
for i, sg in enumerate(sugg):
    with st.container(border=True):
        c1, c2 = st.columns([5, 1], vertical_alignment="center")
        c1.markdown(f":violet[:material/auto_awesome:] **{sg['title']}**  \n{sg['why']}")
        if c2.button("Proposer", key=f"sugg-{i}", width="stretch"):
            queue(sg["changes"])
            st.rerun()

# ---- week view --------------------------------------------------------------------------------------
week = st.segmented_control("Semaine", list(range(n_weeks)), default=cur_week, key="week",
                            format_func=lambda i: f"S{i + 1}" + (" ●" if i == cur_week else ""))
week = cur_week if week is None else week
ws = start + timedelta(weeks=week)
we = ws + timedelta(days=6)
view = {p["date"]: p for p in service.plan_view(db, s, back=(today - ws).days, ahead=(we - today).days)}
dates = [ws + timedelta(days=i) for i in range(7)]
eff = {d.isoformat(): effective(stored[d.isoformat()]) if d.isoformat() in stored else [] for d in dates}
planned_km = sum(pe.course_km(c) for cs in eff.values() for c in cs)
done_km = sum(x.get("distance_km") or 0 for p in view.values() for x in p["done"])
n_quality = sum(1 for cs in eff.values() if any(pe.is_quality_course(c, a.threshold_pace) for c in cs))

st.markdown(f"### Semaine {week + 1} · {phase_of(ws)}  \n:gray[{fdate(ws)} → {fdate(we)}]")
with st.container(horizontal=True):
    st.metric("Volume prévu", f"{fnum(planned_km, 0)} km", border=True)
    st.metric("Réalisé", f"{fnum(done_km, 1)} km", border=True)
    st.metric("Séances de qualité", n_quality, border=True)

for d in dates:
    k_ = d.isoformat()
    day, p = stored.get(k_), view.get(k_, {})
    courses = eff.get(k_, [])
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([1.3, 5, 2.2, 1.4], vertical_alignment="center")
        c1.markdown(f"**{'Aujourd’hui' if d == today else fdate(d).split()[0].capitalize()}**  \n:gray[{d.day} {fdate(d).split()[2]}]")
        if not day:
            c2.caption("Non synchronisé")
            continue
        label = kind_label(courses)
        tag = " :orange-badge[en attente]" if k_ in pending else ""
        if courses:
            c2.markdown(f"{type_badge(label)}{tag}  \n" + "  \n".join(f"**{c['courseName']}** · {course_text(c)}" for c in courses))
        else:
            c2.markdown(f"{type_badge('Repos')}{tag}")
        if k_ in pending:
            c2.caption(f"~~{pe.describe(pending[k_]['before'])}~~")
        status = p.get("status", "")
        icon = {"faite": ":green[:material/check_circle: faite]", "manquée": ":red[:material/cancel: manquée]",
                "à venir": ":gray[à venir]", "repos": ""}.get(status, "")
        km = sum(pe.course_km(c) for c in courses)
        c3.markdown((f"≈ {fnum(km, 1)} km  \n" if km else "") + icon)
        for x in p.get("done", []):
            c3.caption(f"{x['name'] or ''} · {fnum(x['distance_km'], 1)} km" + (f" · {fnum(x['score'])}/10" if x.get("score") is not None else ""))
        if editable(day):
            if c4.button("Modifier", key=f"edit-{k_}", icon=":material/edit:", width="stretch"):
                editor(day)
            if k_ in pending and c4.button("Annuler", key=f"undo-{k_}", width="stretch"):
                pending.pop(k_)
                st.rerun()

# ---- whole-week adjustment --------------------------------------------------------------------------
with st.expander("Ajuster plusieurs séances d'un coup", icon=":material/tune:"):
    scope = st.radio("Portée", ["Cette semaine", "Toutes les semaines restantes"], horizontal=True, key="wk-scope")
    only_q = st.toggle("Seulement les séances de qualité", key="wk-q",
                       help="Laisse les footings et sorties longues faciles tels quels.")
    pool = [stored[d.isoformat()] for d in dates] if scope == "Cette semaine" else [d for _, d in sorted(stored.items())]
    future = [dy for dy in pool if editable(dy) and effective(dy)
              and (not only_q or any(pe.is_quality_course(c, a.threshold_pace) for c in effective(dy)))]
    vol = st.slider("Volume", 50, 150, 100, 5, format="%d %%", key="wk-vol")
    shift = st.slider("Allures de qualité (s/km, négatif = plus vite)", -15, 15, 0, key="wk-shift",
                      help="Par exemple -3 si ta VMA estimée a progressé d'environ 0,2 km/h.")
    st.caption(f"{len(future)} séance(s) concernée(s). Les jours passés ou déjà réalisés ne bougent pas.")
    if st.button("Ajouter aux modifications", key="wk-apply", type="primary", disabled=(vol == 100 and shift == 0) or not future):
        why = ", ".join(([f"volume {vol} %"] if vol != 100 else []) + ([f"allures {shift:+d} s/km"] if shift else []))
        queue([pe.make_change(dy, [pe.shift_paces(pe.scale(c, vol / 100), shift, a.threshold_pace) for c in effective(dy)],
                              f"{'Semaine' if scope == 'Cette semaine' else 'Plan'} ajusté : {why}") for dy in future])
        st.rerun()

# ---- history ----------------------------------------------------------------------------------------
hist = db.plan_changes(30)
if hist:
    with st.expander(f"Historique des modifications ({len(hist)})", icon=":material/history:"):
        st.dataframe(pd.DataFrame([{"Envoyée le": h["created_at"][:16].replace("T", " "), "Jour": fdate(h["date"]),
                                    "Avant": pe.describe(h["before"]), "Après": pe.describe(h["after"]),
                                    "Raison": h["reason"], "Statut": h["status"]} for h in hist]),
                     hide_index=True, width="stretch")
st.caption("Chaque modification est d'abord mise en attente, puis envoyée sur COROS après confirmation. "
           "Tu peux aussi demander à Claude de modifier le plan : il utilise le même plan COROS.")
