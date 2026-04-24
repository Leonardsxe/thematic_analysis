import streamlit as st

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        # Sidebar & General
        "nav_title": "Thematic Analysis",
        "nav_subtitle": "Computer-assisted qualitative research",
        "nav_header": "Navigation",
        "nav_corpus": "Corpus",
        "nav_immersion": "Immersion",
        "nav_coding": "Coding",
        "nav_codebook": "Codebook",
        "nav_clusters": "Clusters",
        "nav_comparison": "Comparison",
        "nav_export": "Export",
        "version_tag": "v0.1.0 — Research preview",
        "lang_label": "Language / Idioma",
        
        # Main Landing
        "main_title": "Thematic Analysis Platform",
        "main_subtitle": "Computer-assisted qualitative analysis for interviews and community documents",
        "status_ai_model": "AI model",
        "status_ollama": "Ollama server",
        "status_database": "Database",
        "status_ready": "ready",
        "status_error": "error",
        "status_online": "online",
        "status_offline": "offline",
        
        # Quick Start
        "quick_start_title": "Quick start",
        "qs_step_1_title": "1 — Import a transcript from the audio-transcriber",
        "qs_step_1_body": "Go to **Corpus → Import** and select a `.transcript.json` file produced by the audio-transcriber project. The platform preserves speaker labels, timestamps, and confidence scores.",
        "qs_step_2_title": "2 — Read and familiarise yourself with the material",
        "qs_step_2_body": "Open **Immersion** to read transcripts with audio playback. Create free-form memos and highlight passages before formal coding begins.",
        "qs_step_3_title": "3 — Code segments and build your codebook",
        "qs_step_3_body": "In **Coding**, select any segment and apply codes manually. Request AI suggestions at any time — all suggestions start as PENDING and require your explicit approval.",
        "qs_step_4_title": "4 — Explore clusters and validate themes",
        "qs_step_4_body": "In **Clusters**, review semantic clusters generated from embeddings. Label clusters, promote them to categories, and synthesise themes with evidence-backed justification.",
        "qs_step_5_title": "5 — Export your evidence matrix and codebook",
        "qs_step_5_body": "In **Export**, download a versioned codebook, evidence matrix, and audit trail suitable for academic research workflows.",
        
        # Footer
        "advisory_note": "All AI suggestions are advisory only. The platform never automatically adopts a model output as a final finding. Every decision is yours.",

        # Corpus Page
        "corpus_title": "Corpus management",
        "tab_projects": "Projects",
        "tab_import": "Import",
        "tab_sources": "Sources",
        "active_project": "Active project",
        "create_project": "Create project",
        "name_label": "Name",
        "research_question": "Research question",
        "create_btn": "Create",
        "select_existing": "Select existing project",
        "activate_btn": "Activate",
        "active_project_info": "Active project: **{name}**",
    },
    "es": {
        # Sidebar & General
        "nav_title": "Análisis Temático",
        "nav_subtitle": "Investigación cualitativa asistida por computadora",
        "nav_header": "Navegación",
        "nav_corpus": "Corpus",
        "nav_immersion": "Inmersión",
        "nav_coding": "Codificación",
        "nav_codebook": "Libro de códigos",
        "nav_clusters": "Clusters",
        "nav_comparison": "Comparación",
        "nav_export": "Exportar",
        "version_tag": "v0.1.0 — Vista previa de investigación",
        "lang_label": "Idioma / Language",
        
        # Main Landing
        "main_title": "Plataforma de Análisis Temático",
        "main_subtitle": "Análisis cualitativo computacional para entrevistas y documentos comunitarios",
        "status_ai_model": "Modelo de IA",
        "status_ollama": "Servidor Ollama",
        "status_database": "Base de datos",
        "status_ready": "listo",
        "status_error": "error",
        "status_online": "en línea",
        "status_offline": "desconectado",
        
        # Quick Start
        "quick_start_title": "Inicio rápido",
        "qs_step_1_title": "1 — Importar una transcripción del audio-transcriber",
        "qs_step_1_body": "Vaya a **Corpus → Importar** y seleccione un archivo `.transcript.json` generado por el proyecto audio-transcriber. La plataforma conserva etiquetas de hablante, marcas de tiempo y puntajes de confianza.",
        "qs_step_2_title": "2 — Leer y familiarizarse con el material",
        "qs_step_2_body": "Abra **Inmersión** para leer transcripciones con reproducción de audio. Cree memorándums libres y resalte pasajes antes de que comience la codificación formal.",
        "qs_step_3_title": "3 — Codificar segmentos y construir su libro de códigos",
        "qs_step_3_body": "En **Codificación**, seleccione cualquier segmento y aplique códigos manualmente. Solicite sugerencias de IA en cualquier momento; todas las sugerencias comienzan como PENDIENTES y requieren su aprobación explícita.",
        "qs_step_4_title": "4 — Explorar clusters y validar temas",
        "qs_step_4_body": "En **Clusters**, revise los grupos semánticos generados a partir de los embeddings. Etiquete los clusters, promuévalos a categorías y sintetice temas con justificación basada en evidencia.",
        "qs_step_5_title": "5 — Exportar su matriz de evidencia y libro de códigos",
        "qs_step_5_body": "En **Exportar**, descargue un libro de códigos versionado, una matriz de evidencia y una pista de auditoría adecuada para flujos de trabajo de investigación académica.",
        
        # Footer
        "advisory_note": "Todas las sugerencias de IA son solo consultivas. La plataforma nunca adopta automáticamente el resultado de un modelo como hallazgo final. Cada decisión es suya.",

        # Corpus Page
        "corpus_title": "Gestión del Corpus",
        "tab_projects": "Proyectos",
        "tab_import": "Importar",
        "tab_sources": "Fuentes",
        "active_project": "Proyecto activo",
        "create_project": "Crear proyecto",
        "name_label": "Nombre",
        "research_question": "Pregunta de investigación",
        "create_btn": "Crear",
        "select_existing": "Seleccionar proyecto existente",
        "activate_btn": "Activar",
        "active_project_info": "Proyecto activo: **{name}**",
    },
}

def t(key: str) -> str:
    """Helper to get translated string for current session language."""
    lang = st.session_state.get("language", "en")
    return TRANSLATIONS.get(lang, TRANSLATIONS["en"]).get(key, key)
