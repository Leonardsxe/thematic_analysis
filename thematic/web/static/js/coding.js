/**
 * coding.js — Coding workspace interactions
 *
 * Handles:
 *   - Apply code to segment (POST /api/coding/apply/)
 *   - AI suggest codes    (POST /api/coding/suggest/)
 *   - Accept suggestion   (POST /api/coding/accept/)
 *   - Reject suggestion   (POST /api/coding/reject/)
 *   - Find similar        (GET  /api/segments/similar/?q=...)
 */

"use strict";

// ── Apply code ────────────────────────────────────────────────────────────────
document.querySelectorAll(".apply-code-btn").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const segId  = btn.dataset.segmentId;
    const codeId = btn.dataset.codeId;
    if (!segId || !codeId) return;

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span>';

    try {
      await api("POST", "/api/coding/apply/", { segment_id: segId, code_id: codeId });
      // Mark the chip as applied in the UI
      const card = document.getElementById(`segment-${segId}`);
      if (card) {
        const applied = card.querySelector(".applied-codes");
        const label   = btn.closest(".code-option")?.querySelector(".code-label")?.textContent ?? "Code";
        if (applied) {
          const chip = document.createElement("span");
          chip.className = "code-chip";
          chip.textContent = label;
          applied.appendChild(chip);
        }
      }
      btn.innerHTML = "✓";
      btn.classList.replace("btn-secondary", "btn-success");
    } catch (err) {
      btn.disabled = false;
      btn.innerHTML = "Apply";
      showToast(err.message, "error");
    }
  });
});

// ── AI suggest ────────────────────────────────────────────────────────────────
document.querySelectorAll(".suggest-btn").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const segId = btn.dataset.segmentId;
    const panel = document.getElementById(`suggestions-${segId}`);
    if (!panel) return;

    btn.disabled = true;
    panel.innerHTML = '<div class="spinner" style="margin:8px auto;display:block"></div>';

    try {
      const data = await api("POST", "/api/coding/suggest/", { segment_id: segId });
      panel.innerHTML = "";

      if (!data.suggestions?.length) {
        panel.innerHTML = '<p style="color:var(--text-muted);font-size:12px">No suggestions returned.</p>';
        btn.disabled = false;
        return;
      }

      data.suggestions.forEach((s) => {
        const card = document.createElement("div");
        card.className = "suggestion-card";
        card.innerHTML = `
          <div class="suggestion-label">${escHtml(s.label)}</div>
          <div class="suggestion-confidence">Confidence: ${(s.confidence * 100).toFixed(0)}%</div>
          <div class="suggestion-justification">${escHtml(s.justification)}</div>
          <div class="suggestion-actions">
            <button class="btn btn-success btn-sm accept-suggestion-btn"
              data-segment-id="${segId}"
              data-label="${escAttr(s.label)}"
              data-justification="${escAttr(s.justification)}">
              ✓ Accept
            </button>
            <button class="btn btn-ghost btn-sm reject-suggestion-btn"
              data-segment-id="${segId}">
              ✗ Reject
            </button>
          </div>`;
        panel.appendChild(card);
      });

      // Bind the freshly created accept/reject buttons
      bindSuggestionActions(panel);
      btn.disabled = false;
    } catch (err) {
      panel.innerHTML = `<p style="color:var(--danger);font-size:12px">${escHtml(err.message)}</p>`;
      btn.disabled = false;
    }
  });
});

function bindSuggestionActions(container) {
  container.querySelectorAll(".accept-suggestion-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const segId         = btn.dataset.segmentId;
      const label         = btn.dataset.label;
      const justification = btn.dataset.justification;

      btn.disabled = true;
      try {
        const data = await api("POST", "/api/coding/accept/", { segment_id: segId, label, justification });
        const card = document.getElementById(`segment-${segId}`);
        if (card) {
          const applied = card.querySelector(".applied-codes");
          if (applied) {
            const chip = document.createElement("span");
            chip.className = "code-chip";
            chip.textContent = label;
            applied.appendChild(chip);
          }
        }
        btn.closest(".suggestion-card").remove();
      } catch (err) {
        btn.disabled = false;
        showToast(err.message, "error");
      }
    });
  });

  container.querySelectorAll(".reject-suggestion-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const segId = btn.dataset.segmentId;
      await api("POST", "/api/coding/reject/", { segment_id: segId }).catch(() => {});
      btn.closest(".suggestion-card").remove();
    });
  });
}

// ── Find similar ──────────────────────────────────────────────────────────────
document.querySelectorAll(".find-similar-btn").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const segId = btn.dataset.segmentId;
    const card  = document.getElementById(`segment-${segId}`);
    const text  = card?.querySelector(".segment-text")?.textContent?.trim() ?? "";
    if (!text) return;

    const panel = document.getElementById(`similar-${segId}`);
    if (!panel) return;

    btn.disabled = true;
    panel.innerHTML = '<div class="spinner" style="margin:8px auto;display:block"></div>';

    try {
      const data = await api("GET", `/api/segments/similar/?q=${encodeURIComponent(text.slice(0, 200))}`);
      panel.innerHTML = "";

      if (!data.segments?.length) {
        panel.innerHTML = '<p style="color:var(--text-muted);font-size:12px">No similar segments found.</p>';
      } else {
        data.segments.forEach((s) => {
          const el = document.createElement("div");
          el.className = "card";
          el.style.marginBottom = "8px";
          el.innerHTML = `
            <div class="segment-meta">
              <span class="speaker-badge ${s.speaker.toLowerCase()}">${escHtml(s.speaker)}</span>
              <span class="segment-time">Score: ${s.score}</span>
            </div>
            <p style="font-size:13px;color:var(--text-muted)">${escHtml(s.text)}</p>`;
          panel.appendChild(el);
        });
      }
      btn.disabled = false;
    } catch (err) {
      panel.innerHTML = `<p style="color:var(--danger);font-size:12px">${escHtml(err.message)}</p>`;
      btn.disabled = false;
    }
  });
});

// ── Utilities ─────────────────────────────────────────────────────────────────
function escHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escAttr(s) { return escHtml(s); }

function showToast(message, type = "info") {
  const el = document.createElement("div");
  el.className = `alert alert-${type}`;
  el.setAttribute("data-auto-dismiss", "");
  el.textContent = message;
  document.querySelector(".main-content")?.prepend(el);
  // auto-dismiss (base.js handles .alert[data-auto-dismiss])
  setTimeout(() => {
    el.style.transition = "opacity 0.5s";
    el.style.opacity = "0";
    setTimeout(() => el.remove(), 500);
  }, 4000);
}
