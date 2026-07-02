const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000/api";

async function handle(res) {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || data.error || `Lỗi ${res.status}`);
  }
  return data;
}

function apiFetch(path, options = {}) {
  return fetch(`${API_URL}${path}`, {
    credentials: "include",
    ...options,
    headers: options.headers || undefined,
  });
}

// --- Auth ---
export async function getMe() {
  return handle(await apiFetch("/auth/me"));
}

export async function login(username, password) {
  return handle(
    await apiFetch("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    })
  );
}

export async function logout() {
  return handle(await apiFetch("/auth/logout", { method: "POST" }));
}

export async function changePassword(currentPassword, newPassword) {
  return handle(
    await apiFetch("/auth/change-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    })
  );
}

// --- Admin: user management ---
export async function listUsers() {
  return handle(await apiFetch("/auth/users"));
}

export async function createUser({ username, password, isAdmin = false }) {
  return handle(
    await apiFetch("/auth/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password, is_admin: isAdmin }),
    })
  );
}

export async function deleteUser(userId) {
  return handle(await apiFetch(`/auth/users/${userId}`, { method: "DELETE" }));
}

export async function resetUserPassword(userId, newPassword) {
  return handle(
    await apiFetch(`/auth/users/${userId}/reset-password`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ new_password: newPassword }),
    })
  );
}

// --- Providers ---
export async function listProviders() {
  return handle(await apiFetch("/providers"));
}

export async function getQuota(provider) {
  return handle(await apiFetch(`/providers/${provider}/quota`));
}

// --- Settings ---
export async function getSettings() {
  return handle(await apiFetch("/settings"));
}

export async function updateSettings(patch) {
  return handle(
    await apiFetch("/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    })
  );
}

export async function clearTranslationCache() {
  return handle(await apiFetch("/settings/cache/clear", { method: "POST" }));
}

export async function clearJobs() {
  return handle(await apiFetch("/settings/jobs/clear", { method: "POST" }));
}

// --- PDF jobs ---
export async function createPdfJob(
  file,
  provider,
  { targetLang = "vi", forceRetranslate = false } = {}
) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("provider", provider);
  formData.append("target_lang", targetLang);
  formData.append("force_retranslate", String(forceRetranslate));
  return handle(
    await apiFetch("/pdf/jobs", {
      method: "POST",
      body: formData,
    })
  );
}

export async function getJobStatus(jobId) {
  return handle(await apiFetch(`/pdf/jobs/${jobId}`));
}

export async function resumeJob(jobId, provider) {
  return handle(
    await apiFetch(`/pdf/jobs/${jobId}/resume`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider }),
    })
  );
}

export function downloadUrl(jobId) {
  return `${API_URL}/pdf/jobs/${jobId}/download`;
}

// --- Text translation ---
export async function translateText(text, provider, targetLang = "vi") {
  return handle(
    await apiFetch("/text/translate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, provider, target_lang: targetLang }),
    })
  );
}

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
