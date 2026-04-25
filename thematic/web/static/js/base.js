/**
 * base.js — shared UI logic across all pages
 *
 * No framework. No build step. Just vanilla JS.
 * Loaded at the bottom of base.html via defer.
 */

"use strict";

// ── CSRF helper (Django requires this on all POST/PUT/DELETE fetch calls) ──────
function getCsrfToken() {
  return document.cookie
    .split(";")
    .map((c) => c.trim())
    .find((c) => c.startsWith("csrftoken="))
    ?.split("=")[1] ?? "";
}

/**
 * Thin fetch wrapper that always sends CSRF token and JSON body.
 *
 * Usage:
 *   const data = await api("POST", "/api/coding/apply/", { segment_id, code_id });
 */
async function api(method, url, body = null) {
  const opts = {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
  };
  if (body) opts.body = JSON.stringify(body);

  const res = await fetch(url, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ message: res.statusText }));
    throw new Error(err.message || `HTTP ${res.status}`);
  }
  return res.json();
}

// ── Tabs ───────────────────────────────────────────────────────────────────────
document.querySelectorAll(".tabs").forEach((tabGroup) => {
  const btns = tabGroup.querySelectorAll(".tab-btn");
  const panels = document.querySelectorAll(
    tabGroup.dataset.panels ? `${tabGroup.dataset.panels} .tab-panel` : ".tab-panel"
  );

  btns.forEach((btn, i) => {
    btn.addEventListener("click", () => {
      btns.forEach((b) => b.classList.remove("active"));
      panels.forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      if (panels[i]) panels[i].classList.add("active");
    });
  });

  // Activate first tab by default
  if (btns[0]) btns[0].click();
});

// ── Expanders (accordion) ──────────────────────────────────────────────────────
document.querySelectorAll(".expander-header").forEach((header) => {
  header.addEventListener("click", () => {
    header.closest(".expander").classList.toggle("open");
  });
});

// ── Language toggle ────────────────────────────────────────────────────────────
document.querySelectorAll(".lang-btn[data-lang]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const lang = btn.dataset.lang;
    const form = document.getElementById("lang-form");
    if (form) {
      form.querySelector("[name=language]").value = lang;
      form.querySelector("[name=next]").value = window.location.pathname + window.location.search;
      form.submit();
    }
  });
});

// ── Flash message auto-dismiss ────────────────────────────────────────────────
document.querySelectorAll(".alert[data-auto-dismiss]").forEach((el) => {
  setTimeout(() => {
    el.style.transition = "opacity 0.5s";
    el.style.opacity = "0";
    setTimeout(() => el.remove(), 500);
  }, 4000);
});

// ── Upload zone drag-and-drop enhancement ─────────────────────────────────────
document.querySelectorAll(".upload-zone").forEach((zone) => {
  const input = zone.querySelector("input[type=file]");

  zone.addEventListener("click", () => input?.click());

  zone.addEventListener("dragover", (e) => {
    e.preventDefault();
    zone.classList.add("drag-over");
  });

  zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));

  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("drag-over");
    if (input && e.dataTransfer.files.length) {
      input.files = e.dataTransfer.files;
      zone.querySelector(".upload-filename").textContent =
        e.dataTransfer.files[0].name;
    }
  });

  if (input) {
    input.addEventListener("change", () => {
      if (input.files.length) {
        zone.querySelector(".upload-filename").textContent = input.files[0].name;
      }
    });
  }
});
