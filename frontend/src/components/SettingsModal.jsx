import { useEffect, useState } from "react";
import {
  clearJobs,
  clearTranslationCache,
  getSettings,
  updateSettings,
} from "../api/translate.js";

const EMPTY = {
  qwen_base_url: "",
  qwen_model: "",
  gemini_rpm_limit: 0,
  gemini_tpm_limit: 0,
  gemini_rpd_limit: 0,
  gemini_max_tokens_per_request: 0,
  gemma_rpm_limit: 0,
  gemma_tpm_limit: 0,
  gemma_rpd_limit: 0,
  gemma_max_tokens_per_request: 0,
  qwen_rpm_limit: 0,
  qwen_tpm_limit: 0,
  qwen_rpd_limit: 0,
  qwen_max_tokens_per_request: 0,
};

export default function SettingsModal({ open, onClose, onSaved }) {
  const [info, setInfo] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [geminiKey, setGeminiKey] = useState("");
  const [qwenKey, setQwenKey] = useState("");
  const [showKeys, setShowKeys] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [toast, setToast] = useState(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setToast(null);
    setGeminiKey("");
    setQwenKey("");
    setLoading(true);
    getSettings()
      .then((s) => {
        setInfo(s);
        setForm({
          qwen_base_url: s.qwen_base_url || "",
          qwen_model: s.qwen_model || "",
          gemini_rpm_limit: s.gemini_rpm_limit,
          gemini_tpm_limit: s.gemini_tpm_limit,
          gemini_rpd_limit: s.gemini_rpd_limit,
          gemini_max_tokens_per_request: s.gemini_max_tokens_per_request,
          gemma_rpm_limit: s.gemma_rpm_limit,
          gemma_tpm_limit: s.gemma_tpm_limit,
          gemma_rpd_limit: s.gemma_rpd_limit,
          gemma_max_tokens_per_request: s.gemma_max_tokens_per_request,
          qwen_rpm_limit: s.qwen_rpm_limit,
          qwen_tpm_limit: s.qwen_tpm_limit,
          qwen_rpd_limit: s.qwen_rpd_limit,
          qwen_max_tokens_per_request: s.qwen_max_tokens_per_request,
        });
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [open]);

  if (!open) return null;

  const num = (v) => (v === "" ? 0 : Number(v));
  const setField = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const setNumField = (k) => (e) => setForm((f) => ({ ...f, [k]: num(e.target.value) }));

  const flash = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(null), 2500);
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const patch = { ...form };
      if (geminiKey.trim()) patch.gemini_api_key = geminiKey.trim();
      if (qwenKey.trim()) patch.qwen_api_key = qwenKey.trim();
      const s = await updateSettings(patch);
      setInfo(s);
      setGeminiKey("");
      setQwenKey("");
      flash("Đã lưu cài đặt");
      onSaved && onSaved();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleClearKey = (which) => async () => {
    if (!window.confirm("Xóa API key này khỏi tài khoản?")) return;
    setSaving(true);
    setError(null);
    try {
      const patch = which === "gemini" ? { gemini_api_key: "" } : { qwen_api_key: "" };
      const s = await updateSettings(patch);
      setInfo(s);
      if (which === "gemini") setGeminiKey("");
      else setQwenKey("");
      flash("Đã xóa key");
      onSaved && onSaved();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleClearCache = async () => {
    if (!window.confirm("Xóa cache bản dịch của tài khoản này?")) return;
    setSaving(true);
    setError(null);
    try {
      const r = await clearTranslationCache();
      const s = await getSettings();
      setInfo(s);
      flash(r.message);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleClearJobs = async () => {
    if (!window.confirm("Xóa lịch sử job và file PDF của tài khoản này?")) return;
    setSaving(true);
    setError(null);
    try {
      const r = await clearJobs();
      const s = await getSettings();
      setInfo(s);
      flash(r.message);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const isAdmin = !!info?.is_admin;
  const cache = info?.cache || {};
  const geminiStatus = info?.gemini_api_key_set
    ? `Đã lưu ${info.gemini_api_key_masked}`
    : "Chưa lưu key";
  const qwenStatus = info?.qwen_api_key_set
    ? `Đã lưu ${info.qwen_api_key_masked}`
    : "Chưa lưu key ModelScope";

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <header className="modal-header">
          <h2>Cài đặt</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Đóng">
            ×
          </button>
        </header>

        {loading ? (
          <p className="muted modal-loading">Đang tải cài đặt...</p>
        ) : (
          <div className="modal-body">
            <section className="settings-section">
              <h3>API Key</h3>
              <p className="note">
                API key được lưu mã hóa trong tài khoản. Backend chỉ trả về trạng thái đã lưu
                và dạng che ký tự, không trả lại key gốc.
              </p>

              <label className="field">
                <span>Gemini / Gemma 4 31B (Google AI Studio)</span>
                <div className="field-row">
                  <input
                    type={showKeys ? "text" : "password"}
                    placeholder={info?.gemini_api_key_set ? "Nhập key mới để thay thế" : "Dán API key"}
                    value={geminiKey}
                    onChange={(e) => setGeminiKey(e.target.value)}
                    autoComplete="off"
                  />
                  {info?.gemini_api_key_set && (
                    <button type="button" className="btn-ghost sm" onClick={handleClearKey("gemini")}>
                      Xóa
                    </button>
                  )}
                </div>
                <span className="key-status">{geminiStatus}</span>
              </label>

              <label className="field">
                <span>Qwen3 235B — API key ModelScope</span>
                <div className="field-row">
                  <input
                    type={showKeys ? "text" : "password"}
                    placeholder={info?.qwen_api_key_set ? "Nhập key mới để thay thế" : "Dán API key ModelScope (ms-...)"}
                    value={qwenKey}
                    onChange={(e) => setQwenKey(e.target.value)}
                    autoComplete="off"
                  />
                  {info?.qwen_api_key_set && (
                    <button type="button" className="btn-ghost sm" onClick={handleClearKey("qwen")}>
                      Xóa
                    </button>
                  )}
                </div>
                <span className="key-status">
                  {qwenStatus} — lấy tại{" "}
                  <a href="https://modelscope.ai" target="_blank" rel="noreferrer">
                    modelscope.ai
                  </a>
                </span>
              </label>

              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={showKeys}
                  onChange={(e) => setShowKeys(e.target.checked)}
                />
                Hiện key đang nhập
              </label>

              <label className="field">
                <span>Qwen Base URL</span>
                <input
                  type="text"
                  value={form.qwen_base_url}
                  onChange={setField("qwen_base_url")}
                  placeholder="https://api-inference.modelscope.ai/v1"
                />
                <span className="key-status">
                  Endpoint OpenAI-compatible của ModelScope API-Inference (mặc định
                  https://api-inference.modelscope.ai/v1).
                </span>
              </label>

              <label className="field">
                <span>Qwen — Tên model</span>
                <input
                  type="text"
                  value={form.qwen_model}
                  onChange={setField("qwen_model")}
                  placeholder="Qwen/Qwen3-235B-A22B-Instruct-2507"
                />
                <span className="key-status">
                  Mặc định Qwen/Qwen3-235B-A22B-Instruct-2507.
                </span>
              </label>
            </section>

            <section className="settings-section">
              <h3>Giới hạn quota {!isAdmin && <span className="tag">chỉ đọc</span>}</h3>
              {!isAdmin && (
                <p className="note">Chỉ quản trị viên mới chỉnh được giới hạn quota chung.</p>
              )}
              <div className="quota-grid">
                <span className="quota-grid-head" />
                <span className="quota-grid-head">RPM</span>
                <span className="quota-grid-head">TPM</span>
                <span className="quota-grid-head">RPD</span>
                <span className="quota-grid-head">Max token/request</span>

                <span className="quota-grid-label">Gemini 3.5 Flash Lite</span>
                <label className="quota-cell"><span className="quota-cell-label">RPM</span><input type="number" min="0" disabled={!isAdmin} value={form.gemini_rpm_limit} onChange={setNumField("gemini_rpm_limit")} /></label>
                <label className="quota-cell"><span className="quota-cell-label">TPM</span><input type="number" min="0" disabled={!isAdmin} value={form.gemini_tpm_limit} onChange={setNumField("gemini_tpm_limit")} /></label>
                <label className="quota-cell"><span className="quota-cell-label">RPD</span><input type="number" min="0" disabled={!isAdmin} value={form.gemini_rpd_limit} onChange={setNumField("gemini_rpd_limit")} /></label>
                <label className="quota-cell"><span className="quota-cell-label">Max token/request</span><input type="number" min="0" disabled={!isAdmin} value={form.gemini_max_tokens_per_request} onChange={setNumField("gemini_max_tokens_per_request")} /></label>

                <span className="quota-grid-label">Gemma 4 31B</span>
                <label className="quota-cell"><span className="quota-cell-label">RPM</span><input type="number" min="0" disabled={!isAdmin} value={form.gemma_rpm_limit} onChange={setNumField("gemma_rpm_limit")} /></label>
                <label className="quota-cell"><span className="quota-cell-label">TPM</span><input type="number" min="0" disabled={!isAdmin} value={form.gemma_tpm_limit} onChange={setNumField("gemma_tpm_limit")} /></label>
                <label className="quota-cell"><span className="quota-cell-label">RPD</span><input type="number" min="0" disabled={!isAdmin} value={form.gemma_rpd_limit} onChange={setNumField("gemma_rpd_limit")} /></label>
                <label className="quota-cell"><span className="quota-cell-label">Max token/request</span><input type="number" min="0" disabled={!isAdmin} value={form.gemma_max_tokens_per_request} onChange={setNumField("gemma_max_tokens_per_request")} /></label>

                <span className="quota-grid-label">Qwen</span>
                <label className="quota-cell"><span className="quota-cell-label">RPM</span><input type="number" min="0" disabled={!isAdmin} value={form.qwen_rpm_limit} onChange={setNumField("qwen_rpm_limit")} /></label>
                <label className="quota-cell"><span className="quota-cell-label">TPM</span><input type="number" min="0" disabled={!isAdmin} value={form.qwen_tpm_limit} onChange={setNumField("qwen_tpm_limit")} /></label>
                <label className="quota-cell"><span className="quota-cell-label">RPD</span><input type="number" min="0" disabled={!isAdmin} value={form.qwen_rpd_limit} onChange={setNumField("qwen_rpd_limit")} /></label>
                <label className="quota-cell"><span className="quota-cell-label">Max token/request</span><input type="number" min="0" disabled={!isAdmin} value={form.qwen_max_tokens_per_request} onChange={setNumField("qwen_max_tokens_per_request")} /></label>
              </div>
            </section>

            <section className="settings-section">
              <h3>Dữ liệu tài khoản</h3>
              <div className="cache-stats">
                <span>{cache.segments ?? 0} đoạn dịch đã cache</span>
                <span>{cache.jobs ?? 0} job</span>
                <span>{cache.upload_files ?? 0} PDF gốc / {cache.output_files ?? 0} PDF đã dịch</span>
              </div>
              <div className="cache-actions">
                <button type="button" className="btn-danger-ghost" onClick={handleClearCache} disabled={saving}>
                  Xóa cache bản dịch
                </button>
                <button type="button" className="btn-danger-ghost" onClick={handleClearJobs} disabled={saving}>
                  Xóa lịch sử job và file
                </button>
              </div>
            </section>

            {error && <p className="error">{error}</p>}
          </div>
        )}

        <footer className="modal-footer">
          {toast && <span className="toast">{toast}</span>}
          <button className="btn-ghost" onClick={onClose}>
            Đóng
          </button>
          <button className="btn-primary" onClick={handleSave} disabled={loading || saving}>
            {saving ? "Đang lưu..." : "Lưu cài đặt"}
          </button>
        </footer>
      </div>
    </div>
  );
}
