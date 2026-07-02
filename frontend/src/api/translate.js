import { authHeadersForProvider } from "./keys.js";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000/api";

async function handle(res) {
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || err.error || `Lỗi ${res.status}`);
  }
  return res.json();
}

// --- Providers ---
export async function listProviders() {
  return handle(await fetch(`${API_URL}/providers`));
}

export async function getQuota(provider) {
  return handle(await fetch(`${API_URL}/providers/${provider}/quota`));
}

// --- Cài đặt (API key, base URL, quota, dọn cache) ---
export async function getSettings() {
  return handle(await fetch(`${API_URL}/settings`));
}

export async function updateSettings(patch) {
  return handle(
    await fetch(`${API_URL}/settings`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    })
  );
}

export async function clearTranslationCache() {
  return handle(await fetch(`${API_URL}/settings/cache/clear`, { method: "POST" }));
}

export async function clearJobs() {
  return handle(await fetch(`${API_URL}/settings/jobs/clear`, { method: "POST" }));
}

// --- Dịch PDF (mẫu job) ---
export async function createPdfJob(file, provider, { targetLang = "vi", forceRetranslate = false } = {}) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("provider", provider);
  formData.append("target_lang", targetLang);
  formData.append("force_retranslate", String(forceRetranslate));
  return handle(
    await fetch(`${API_URL}/pdf/jobs`, {
      method: "POST",
      headers: authHeadersForProvider(provider),
      body: formData,
    })
  );
}

export async function getJobStatus(jobId) {
  return handle(await fetch(`${API_URL}/pdf/jobs/${jobId}`));
}

export async function resumeJob(jobId, provider) {
  return handle(
    await fetch(`${API_URL}/pdf/jobs/${jobId}/resume`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeadersForProvider(provider) },
      body: JSON.stringify({ provider }),
    })
  );
}

export function downloadUrl(jobId) {
  return `${API_URL}/pdf/jobs/${jobId}/download`;
}

// --- Dịch văn bản dán tay ---
export async function translateText(text, provider, targetLang = "vi") {
  return handle(
    await fetch(`${API_URL}/text/translate`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeadersForProvider(provider) },
      body: JSON.stringify({ text, provider, target_lang: targetLang }),
    })
  );
}

// --- Helper: poll trạng thái job tới khi kết thúc ---
const TERMINAL = ["done", "failed", "paused_quota"];

export async function pollJobUntilDone(jobId, onProgress, intervalMs = 2000) {
  return new Promise((resolve, reject) => {
    const tick = async () => {
      try {
        const status = await getJobStatus(jobId);
        if (onProgress) onProgress(status);
        if (TERMINAL.includes(status.status)) {
          resolve(status);
        } else {
          setTimeout(tick, intervalMs);
        }
      } catch (err) {
        reject(err);
      }
    };
    tick();
  });
}
