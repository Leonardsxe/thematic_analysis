/**
 * import.js — Transcript / document file upload with progress feedback
 *
 * Uses XMLHttpRequest for upload progress events (fetch() doesn't support them).
 */

"use strict";

const uploadForm = document.getElementById("upload-form");
const progressEl = document.getElementById("upload-progress");
const progressBar = document.getElementById("progress-bar");
const progressText = document.getElementById("progress-text");
const resultEl = document.getElementById("upload-result");

if (uploadForm) {
  uploadForm.addEventListener("submit", (e) => {
    e.preventDefault();

    const fileInput = uploadForm.querySelector("input[type=file]");
    if (!fileInput?.files?.length) {
      showResult("No file selected.", "error");
      return;
    }

    const formData = new FormData();
    formData.append("file", fileInput.files[0]);
    formData.append("csrfmiddlewaretoken", getCsrfToken());

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/corpus/import/");
    xhr.setRequestHeader("X-CSRFToken", getCsrfToken());

    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable) {
        const pct = Math.round((e.loaded / e.total) * 100);
        if (progressEl) progressEl.style.display = "block";
        if (progressBar) progressBar.style.width = `${pct}%`;
        if (progressText) progressText.textContent = `Uploading… ${pct}%`;
      }
    });

    xhr.addEventListener("load", () => {
      if (progressEl) progressEl.style.display = "none";
      try {
        const data = JSON.parse(xhr.responseText);
        if (data.ok) {
          showResult(`✓ Imported: ${data.source_title}`, "success");
          uploadForm.reset();
          document.querySelector(".upload-filename").textContent = "";
          // Refresh source list link if present
          const refreshLink = document.getElementById("refresh-sources");
          if (refreshLink) refreshLink.style.display = "inline-flex";
        } else {
          showResult(data.message ?? "Import failed.", "error");
        }
      } catch {
        showResult("Unexpected server response.", "error");
      }
    });

    xhr.addEventListener("error", () => {
      if (progressEl) progressEl.style.display = "none";
      showResult("Network error during upload.", "error");
    });

    xhr.send(formData);
  });
}

function showResult(message, type) {
  if (!resultEl) return;
  resultEl.className = `alert alert-${type}`;
  resultEl.textContent = message;
  resultEl.style.display = "block";
}
