const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000/api";

class ApiError extends Error {
  constructor(message, status, data) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

async function handle(res) {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new ApiError(data.detail || data.error || `Lỗi ${res.status}`, res.status, data);
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

export async function getJobStatus(jobId, signal) {
  return handle(await apiFetch(`/pdf/jobs/${jobId}`, { signal }));
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
const JOB_STATUSES = ["queued", "running", ...TERMINAL];
const MAX_TRANSIENT_POLL_FAILURES = 8;
const MAX_POLL_RETRY_DELAY_MS = 15000;

function jobStatusFromError(err, jobId) {
  const data = err?.data;
  if (
    data &&
    data.job_id === jobId &&
    JOB_STATUSES.includes(data.status) &&
    data.progress &&
    typeof data.progress === "object"
  ) {
    return data;
  }
  return null;
}

function isTransientPollError(err) {
  // fetch() dùng TypeError cho lỗi mạng; gateway/proxy thường trả 5xx.
  if (err instanceof TypeError) return true;
  const status = Number(err?.status || 0);
  return status === 408 || status === 425 || status === 429 || status >= 500;
}

export async function pollJobUntilDone(jobId, onProgress, intervalMs = 2000, signal) {
  return new Promise((resolve, reject) => {
    let transientFailures = 0;
    let timerId = null;
    let settled = false;

    const abortError = () => {
      const error = new Error("Đã hủy theo dõi job");
      error.name = "AbortError";
      return error;
    };

    const cleanup = () => {
      if (timerId !== null) clearTimeout(timerId);
      signal?.removeEventListener("abort", handleAbort);
    };

    const finish = (callback, value) => {
      if (settled) return;
      settled = true;
      cleanup();
      callback(value);
    };

    const handleAbort = () => finish(reject, abortError());

    const schedule = (delay) => {
      if (settled || signal?.aborted) return;
      timerId = setTimeout(tick, delay);
    };

    const acceptStatus = (status) => {
      transientFailures = 0;
      if (onProgress) onProgress(status);
      if (TERMINAL.includes(status.status)) {
        finish(resolve, status);
        return true;
      }
      return false;
    };

    const tick = async () => {
      if (settled || signal?.aborted) return;
      try {
        const status = await getJobStatus(jobId, signal);
        if (!acceptStatus(status)) {
          schedule(intervalMs);
        }
      } catch (err) {
        if (settled) return;
        if (err?.name === "AbortError") {
          finish(reject, err);
          return;
        }

        // Một số proxy có thể gắn status 502 dù body upstream đã là JobStatus hợp lệ.
        // Trong trường hợp đó body có job_id đúng vẫn là nguồn trạng thái đáng tin cậy.
        const status = jobStatusFromError(err, jobId);
        if (status) {
          if (!acceptStatus(status)) schedule(intervalMs);
          return;
        }

        if (!isTransientPollError(err)) {
          finish(reject, err);
          return;
        }

        transientFailures += 1;
        if (transientFailures > MAX_TRANSIENT_POLL_FAILURES) {
          finish(
            reject,
            new Error(
              "Mất kết nối tới máy chủ quá lâu. Job vẫn có thể đang chạy; vui lòng tải lại trang sau ít phút."
            )
          );
          return;
        }

        const retryDelay = Math.min(
          intervalMs * 2 ** (transientFailures - 1),
          MAX_POLL_RETRY_DELAY_MS
        );
        schedule(retryDelay);
      }
    };

    if (signal?.aborted) {
      finish(reject, abortError());
      return;
    }
    signal?.addEventListener("abort", handleAbort, { once: true });
    tick();
  });
}
