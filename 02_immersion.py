"""
02_immersion.py — Immersion workspace
=======================================

Reading-first space for familiarising with transcript material before
formal coding begins. Supports memos, bookmarks, and audio playback alignment.
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Immersion | Thematic Analysis", layout="wide")

st.title("Immersion")
st.caption(
    "Read and familiarise yourself with the material before coding. "
    "Write memos, highlight passages, and note initial impressions."
)

# ── Source selector ───────────────────────────────────────────────────────────
with st.sidebar:
    st.subheader("Source")
    # Placeholder — replace with DB query
    sources = ["Entrevista_Natalia_Peliroja_2", "Entrevista_Lisa_Trujillo"]
    selected_source = st.selectbox("Select transcript", sources)
    speaker_filter = st.multiselect(
        "Show speakers", ["INTERVIEWEE", "INTERVIEWER"], default=["INTERVIEWEE"]
    )
    st.divider()
    show_timestamps = st.checkbox("Show timestamps", value=True)
    show_confidence = st.checkbox("Show confidence", value=False)
    st.divider()
    st.subheader("Quick memo")
    quick_memo = st.text_area("General impression", height=100, placeholder="Initial thoughts…")
    if st.button("Save memo"):
        if quick_memo.strip():
            st.success("Memo saved.")

# ── Demo segments ─────────────────────────────────────────────────────────────
demo_turns = [
    {"speaker": "INTERVIEWER", "start_s": 0, "text": "Buenos días. ¿Me puede contar sobre su experiencia en el proyecto?"},
    {"speaker": "INTERVIEWEE", "start_s": 8, "text": "Buenos días. Claro, con mucho gusto. Empecé hace tres años, cuando la comunidad decidió organizar los talleres de lectura en el barrio. Al principio éramos cinco personas, pero poco a poco fuimos creciendo."},
    {"speaker": "INTERVIEWER", "start_s": 42, "text": "¿Y qué desafíos encontraron en ese proceso?"},
    {"speaker": "INTERVIEWEE", "start_s": 48, "text": "El principal fue el espacio. Nos prestaban un salón comunitario pero después nos quitaron el acceso sin consultarnos. Eso fue muy difícil porque ya teníamos cuarenta personas participando cada semana."},
    {"speaker": "INTERVIEWEE", "start_s": 78, "text": "La comunidad respondió muy bien. Empezamos a rotar entre casas particulares. Eso en realidad nos unió más, porque la gente se sintió más dueña del proceso."},
    {"speaker": "INTERVIEWER", "start_s": 105, "text": "¿Cómo fue la relación con las instituciones locales?"},
    {"speaker": "INTERVIEWEE", "start_s": 112, "text": "Complicada. Hubo momentos de apoyo pero siempre condicionado a que adoptáramos su metodología. Nosotros queríamos mantener nuestro enfoque popular, basado en las experiencias propias de los participantes."},
]

visible = [t for t in demo_turns if t["speaker"] in speaker_filter]

st.subheader(f"{selected_source} — {len(visible)} turns")

for i, turn in enumerate(visible):
    with st.container(border=False):
        speaker = turn["speaker"]
        color = "#0F6E56" if speaker == "INTERVIEWEE" else "#534AB7"
        time_label = ""
        if show_timestamps and turn.get("start_s") is not None:
            t = int(turn["start_s"])
            time_label = f" · {t//60}:{t%60:02d}"

        st.markdown(
            f"<span style='color:{color};font-weight:500;font-size:13px'>"
            f"{speaker}{time_label}</span>",
            unsafe_allow_html=True,
        )
        st.markdown(turn["text"])

        col_memo, col_bookmark = st.columns([3, 1])
        with col_memo:
            if st.button("Add memo", key=f"memo_{i}"):
                st.session_state[f"open_memo_{i}"] = True
        with col_bookmark:
            if st.button("Bookmark", key=f"bm_{i}"):
                st.success("Bookmarked.")

        if st.session_state.get(f"open_memo_{i}"):
            memo_text = st.text_area("Memo for this passage", key=f"memo_txt_{i}", height=70)
            if st.button("Save", key=f"save_memo_{i}"):
                if memo_text.strip():
                    st.success("Memo saved.")
                st.session_state[f"open_memo_{i}"] = False

        st.divider()
