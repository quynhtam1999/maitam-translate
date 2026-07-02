// Key của người dùng KHÔNG gửi lên server để lưu — chỉ lưu ở trình duyệt của
// chính họ (localStorage) và đính kèm mỗi request qua header. Site public
// nhiều người dùng, mỗi người tự chịu trách nhiệm key/quota của mình.
const STORAGE_KEYS = {
  gemini: "mtt_key_gemini",
  qwen: "mtt_key_qwen",
};

export function getLocalKey(kind) {
  try {
    return localStorage.getItem(STORAGE_KEYS[kind]) || "";
  } catch {
    return "";
  }
}

export function setLocalKey(kind, value) {
  try {
    if (value) localStorage.setItem(STORAGE_KEYS[kind], value);
    else localStorage.removeItem(STORAGE_KEYS[kind]);
  } catch {
    /* trình duyệt chặn localStorage (chế độ ẩn danh nghiêm ngặt) — bỏ qua */
  }
}

export function hasLocalKey(kind) {
  return Boolean(getLocalKey(kind));
}

// gemini và gemma dùng chung Google AI Studio key.
export function localKeyKindForProvider(providerName) {
  if (providerName === "gemini" || providerName === "gemma") return "gemini";
  if (providerName === "qwen") return "qwen";
  return null;
}

export function authHeadersForProvider(providerName) {
  const kind = localKeyKindForProvider(providerName);
  if (!kind) return {};
  const key = getLocalKey(kind);
  if (!key) return {};
  return kind === "gemini" ? { "X-Gemini-Key": key } : { "X-Qwen-Key": key };
}
