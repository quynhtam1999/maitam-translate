import { useEffect, useState } from "react";
import { changePassword } from "../api/translate.js";

export default function ChangePasswordModal({ open, onClose }) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [toast, setToast] = useState(null);

  useEffect(() => {
    if (!open) return;
    setCurrentPassword("");
    setNewPassword("");
    setError(null);
    setToast(null);
  }, [open]);

  if (!open) return null;

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await changePassword(currentPassword, newPassword);
      setCurrentPassword("");
      setNewPassword("");
      setToast("Đã đổi mật khẩu");
      setTimeout(() => {
        setToast(null);
        onClose();
      }, 1200);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal modal-narrow" onClick={(e) => e.stopPropagation()}>
        <header className="modal-header">
          <h2>Đổi mật khẩu</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Đóng">
            ×
          </button>
        </header>

        <div className="modal-body">
          <form onSubmit={handleSubmit} className="admin-create-form">
            <label className="field">
              <span>Mật khẩu hiện tại</span>
              <input
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </label>
            <label className="field">
              <span>Mật khẩu mới</span>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                autoComplete="new-password"
                minLength={8}
                required
              />
            </label>
            {error && <p className="error">{error}</p>}
            <button className="btn-primary" type="submit" disabled={saving}>
              {saving ? "Đang đổi..." : "Đổi mật khẩu"}
            </button>
          </form>
        </div>

        <footer className="modal-footer">
          {toast && <span className="toast">{toast}</span>}
          <button className="btn-ghost" onClick={onClose}>
            Đóng
          </button>
        </footer>
      </div>
    </div>
  );
}
