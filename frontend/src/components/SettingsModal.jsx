import { useEffect, useState } from "react";
import {
  getSettings,
  updateSettings,
  clearTranslationCache,
  clearJobs,
} from "../api/translate.js";

const EMPTY = {
  qwen_base_url: "",
  default_target_lang: "vi",
  gemini_rpm_limit: 0,
  gemini_tpm_limit: 0,
  gemini_rpd_limit: 0,
  qwen_rpm_limit: 0,
  qwen_tpm_limit: 0,
  qwen_rpd_limit: 0,
};

export default function SettingsModal({ open, onClose, onSaved }) {
  const [info, setInfo] = useState(null); // dữ liệu gốc từ server (chứa masked key)
  const [form, setForm] = useState(EMPTY);
  const [geminiKey, setGeminiKey] = useState(""); // "" = giữ nguyên
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
          default_target_lang: s.default_target_lang || "vi",
          gemini_rpm_limit: s.gemini_rpm_limit,
          gemini_tpm_limit: s.gemini_tpm_limit,
          gemini_rpd_limit: s.gemini_rpd_limit,
          qwen_rpm_limit: s.qwen_rpm_limit,
          qwen_tpm_limit: s.qwen_tpm_limit,
          qwen_rpd_limit: s.qwen_rpd_limit,
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
      // Key: chỉ gửi khi người dùng gõ gì đó (rỗng = giữ nguyên).
      if (geminiKey.trim() !== "") patch.gemini_api_key = geminiKey.trim();
      if (qwenKey.trim() !== "") patch.qwen_api_key = qwenKey.trim();
      const s = await updateSettings(patch);
      setInfo(s);
      setGeminiKey("");
      setQwenKey("");
      flash("✓ Đã lưu cài đặt");
      onSaved && onSaved();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleClearKey = (which) => async () => {
    if (!window.confirm("Xóa API key này?")) return;
    setSaving(true);
    setError(null);
    try {
      const patch = which === "gemini" ? { gemini_api_key: "" } : { qwen_api_key: "" };
      const s = await updateSettings(patch);
      setInfo(s);
      flash("✓ Đã xóa key");
      onSaved && onSaved();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleClearCache = async () => {
    if (!window.confirm("Xóa toàn bộ bộ nhớ đệm bản dịch? Lần dịch sau sẽ gọi API lại từ đầu.")) return;
    setSaving(true);
    try {
      const r = await clearTranslationCache();
      const s = await getSettings();
      setInfo(s);
      flash(`✓ ${r.message}`);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleClearJobs = async () => {
    if (!window.confirm("Xóa lịch sử job và các file PDF gốc/đã dịch trên máy chủ?")) return;
    setSaving(true);
    try {
      const r = await clearJobs();
      const s = await getSettings();
      setInfo(s);
      flash(`✓ ${r.message}`);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const cache = info?.cache || {};

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <header className="modal-header">
          <h2>⚙ Cài đặt</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Đóng">
            ✕
          </button>
        </header>

        {loading ? (
          <p className="muted">Đang tải cài đặt…</p>
        ) : (
          <div className="modal-body">
            {/* --- API keys --- */}
            <section className="settings-section">
              <h3>API Key</h3>
              <label className="field">
                <span>
                  Gemini / Gemma (Google AI Studio)
                  {info?.gemini_api_key_set && (
                    <em className="tag ok"> đã lưu: {info.gemini_api_key_masked}</em>
                  )}
                </span>
                <div className="field-row">
                  <input
                    type={showKeys ? "text" : "password"}
                    placeholder={
                      info?.gemini_api_key_set ? "Để trống nếu giữ nguyên" : "Dán API key vào đây"
                    }
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
              </label>

              <label className="field">
                <span>
                  Qwen (ModelScope)
                  {info?.qwen_api_key_set && (
                    <em className="tag ok"> đã lưu: {info.qwen_api_key_masked}</em>
                  )}
                </span>
                <div className="field-row">
                  <input
                    type={showKeys ? "text" : "password"}
                    placeholder={
                      info?.qwen_api_key_set ? "Để trống nếu giữ nguyên" : "Dán API key vào đây"
                    }
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
              </label>

              <p className="note">
                <strong>Qwen3-235B-A22B-Instruct-2507</strong> qua ModelScope — miễn phí
                <strong> 2.000 lượt gọi/ngày</strong> (chung mọi model)
              </p>

              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={showKeys}
                  onChange={(e) => setShowKeys(e.target.checked)}
                />
                Hiện API key
              </label>

              <label className="field">
                <span>Qwen Base URL</span>
                <input
                  type="text"
                  value={form.qwen_base_url}
                  onChange={setField("qwen_base_url")}
                  placeholder="https://api-inference.modelscope.ai/v1"
                />
              </label>

              <label className="field">
                <span>Ngôn ngữ đích mặc định</span>
                <input
                  type="text"
                  value={form.default_target_lang}
                  onChange={setField("default_target_lang")}
                  placeholder="vi"
                />
              </label>
            </section>

            {/* --- Giới hạn quota --- */}
            <section className="settings-section">
              <h3>Giới hạn quota</h3>
              <div className="quota-grid">
                <span className="quota-grid-head" />
                <span className="quota-grid-head">RPM</span>
                <span className="quota-grid-head">TPM</span>
                <span className="quota-grid-head">RPD</span>

                <span className="quota-grid-label">Gemini / Gemma</span>
                <input type="number" min="0" value={form.gemini_rpm_limit} onChange={setNumField("gemini_rpm_limit")} />
                <input type="number" min="0" value={form.gemini_tpm_limit} onChange={setNumField("gemini_tpm_limit")} />
                <input type="number" min="0" value={form.gemini_rpd_limit} onChange={setNumField("gemini_rpd_limit")} />

                <span className="quota-grid-label">Qwen</span>
                <input type="number" min="0" value={form.qwen_rpm_limit} onChange={setNumField("qwen_rpm_limit")} />
                <input type="number" min="0" value={form.qwen_tpm_limit} onChange={setNumField("qwen_tpm_limit")} />
                <input type="number" min="0" value={form.qwen_rpd_limit} onChange={setNumField("qwen_rpd_limit")} />
              </div>
              <p className="muted sm">RPM: yêu cầu/phút · TPM: token/phút · RPD: yêu cầu/ngày</p>
            </section>

            {/* --- Bộ nhớ đệm / dọn dẹp --- */}
            <section className="settings-section">
              <h3>Bộ nhớ đệm & dọn dẹp</h3>
              <div className="cache-stats">
                <span>📦 {cache.segments ?? 0} đoạn dịch đã cache</span>
                <span>🗂 {cache.jobs ?? 0} job</span>
                <span>📄 {cache.upload_files ?? 0} PDF gốc · {cache.output_files ?? 0} PDF đã dịch</span>
              </div>
              <div className="cache-actions">
                <button type="button" className="btn-danger-ghost" onClick={handleClearCache} disabled={saving}>
                  🧹 Xóa cache bản dịch
                </button>
                <button type="button" className="btn-danger-ghost" onClick={handleClearJobs} disabled={saving}>
                  🗑 Xóa lịch sử job & file
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
            {saving ? "Đang lưu…" : "Lưu cài đặt"}
          </button>
        </footer>
      </div>
    </div>
  );
}
