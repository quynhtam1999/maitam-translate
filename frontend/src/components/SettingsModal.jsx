import { useEffect, useState } from "react";
import {
  getSettings,
  updateSettings,
  clearTranslationCache,
  clearJobs,
} from "../api/translate.js";
import { getLocalKey, setLocalKey } from "../api/keys.js";

const EMPTY = {
  qwen_base_url: "",
  gemini_rpm_limit: 0,
  gemini_tpm_limit: 0,
  gemini_rpd_limit: 0,
  gemma_rpm_limit: 0,
  gemma_tpm_limit: 0,
  gemma_rpd_limit: 0,
  qwen_rpm_limit: 0,
  qwen_tpm_limit: 0,
  qwen_rpd_limit: 0,
};

export default function SettingsModal({ open, onClose, onSaved }) {
  const [info, setInfo] = useState(null); // dữ liệu gốc từ server (không có key)
  const [form, setForm] = useState(EMPTY);
  // Key CHỈ lưu ở trình duyệt của người dùng (localStorage) — không gửi lên server để lưu.
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
    setGeminiKey(getLocalKey("gemini"));
    setQwenKey(getLocalKey("qwen"));
    setLoading(true);
    getSettings()
      .then((s) => {
        setInfo(s);
        setForm({
          qwen_base_url: s.qwen_base_url || "",
          gemini_rpm_limit: s.gemini_rpm_limit,
          gemini_tpm_limit: s.gemini_tpm_limit,
          gemini_rpd_limit: s.gemini_rpd_limit,
          gemma_rpm_limit: s.gemma_rpm_limit,
          gemma_tpm_limit: s.gemma_tpm_limit,
          gemma_rpd_limit: s.gemma_rpd_limit,
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
      // Key: chỉ lưu ở trình duyệt này (localStorage), không gửi lên server.
      setLocalKey("gemini", geminiKey.trim());
      setLocalKey("qwen", qwenKey.trim());
      const s = await updateSettings(form);
      setInfo(s);
      flash("✓ Đã lưu cài đặt");
      onSaved && onSaved();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleClearKey = (which) => () => {
    if (!window.confirm("Xóa API key này khỏi trình duyệt?")) return;
    setLocalKey(which, "");
    if (which === "gemini") setGeminiKey("");
    else setQwenKey("");
    flash("✓ Đã xóa key");
    onSaved && onSaved();
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
            {/* --- API keys (chỉ lưu trên trình duyệt này, KHÔNG gửi lên server) --- */}
            <section className="settings-section">
              <h3>API Key</h3>
              <p className="note">
                Key chỉ lưu trên trình duyệt của bạn (localStorage), không gửi lên server để lưu —
                mỗi người dùng tự chịu quota key của mình.
                {info?.gemini_api_key_set || info?.qwen_api_key_set ? (
                  <> Trang này cũng có key mặc định do quản trị viên cấu hình, dùng khi bạn để trống.</>
                ) : null}
              </p>

              <label className="field">
                <span>Gemini / Gemma (Google AI Studio)</span>
                <div className="field-row">
                  <input
                    type={showKeys ? "text" : "password"}
                    placeholder="Dán API key của bạn vào đây"
                    value={geminiKey}
                    onChange={(e) => setGeminiKey(e.target.value)}
                    autoComplete="off"
                  />
                  {geminiKey && (
                    <button type="button" className="btn-ghost sm" onClick={handleClearKey("gemini")}>
                      Xóa
                    </button>
                  )}
                </div>
              </label>

              <label className="field">
                <span>Qwen (ModelScope)</span>
                <div className="field-row">
                  <input
                    type={showKeys ? "text" : "password"}
                    placeholder="Dán API key của bạn vào đây"
                    value={qwenKey}
                    onChange={(e) => setQwenKey(e.target.value)}
                    autoComplete="off"
                  />
                  {qwenKey && (
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

            </section>

            {/* --- Giới hạn quota --- */}
            <section className="settings-section">
              <h3>Giới hạn quota</h3>
              <div className="quota-grid">
                <span className="quota-grid-head" />
                <span className="quota-grid-head">RPM</span>
                <span className="quota-grid-head">TPM</span>
                <span className="quota-grid-head">RPD</span>

                <span className="quota-grid-label">Gemini 3.1 Flash Lite</span>
                <input type="number" min="0" value={form.gemini_rpm_limit} onChange={setNumField("gemini_rpm_limit")} />
                <input type="number" min="0" value={form.gemini_tpm_limit} onChange={setNumField("gemini_tpm_limit")} />
                <input type="number" min="0" value={form.gemini_rpd_limit} onChange={setNumField("gemini_rpd_limit")} />

                <span className="quota-grid-label">Gemma</span>
                <input type="number" min="0" value={form.gemma_rpm_limit} onChange={setNumField("gemma_rpm_limit")} />
                <input type="number" min="0" value={form.gemma_tpm_limit} onChange={setNumField("gemma_tpm_limit")} />
                <input type="number" min="0" value={form.gemma_rpd_limit} onChange={setNumField("gemma_rpd_limit")} />

                <span className="quota-grid-label">Qwen</span>
                <input type="number" min="0" value={form.qwen_rpm_limit} onChange={setNumField("qwen_rpm_limit")} />
                <input type="number" min="0" value={form.qwen_tpm_limit} onChange={setNumField("qwen_tpm_limit")} />
                <input type="number" min="0" value={form.qwen_rpd_limit} onChange={setNumField("qwen_rpd_limit")} />
              </div>
              <p className="muted sm">
                RPM/TPM: đạt giới hạn trong 1 phút thì tự chờ sang phút kế tiếp; RPD: đạt giới hạn ngày thì ngưng dịch và báo cho người dùng.
              </p>
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
