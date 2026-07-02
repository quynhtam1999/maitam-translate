import { useEffect, useState } from "react";
import { createUser, deleteUser, listUsers, resetUserPassword } from "../api/translate.js";

export default function AdminModal({ open, onClose, currentUserId }) {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [toast, setToast] = useState(null);

  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newIsAdmin, setNewIsAdmin] = useState(false);
  const [creating, setCreating] = useState(false);

  const [resetTarget, setResetTarget] = useState(null);
  const [resetPassword, setResetPassword] = useState("");

  const flash = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(null), 2500);
  };

  const refresh = () => {
    setLoading(true);
    setError(null);
    return listUsers()
      .then(setUsers)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (!open) return;
    setError(null);
    setToast(null);
    setNewUsername("");
    setNewPassword("");
    setNewIsAdmin(false);
    setResetTarget(null);
    refresh();
  }, [open]);

  if (!open) return null;

  const handleCreate = async (event) => {
    event.preventDefault();
    setCreating(true);
    setError(null);
    try {
      await createUser({ username: newUsername.trim(), password: newPassword, isAdmin: newIsAdmin });
      setNewUsername("");
      setNewPassword("");
      setNewIsAdmin(false);
      flash("Đã tạo tài khoản");
      await refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = (user) => async () => {
    if (!window.confirm(`Xóa tài khoản "${user.username}"? Toàn bộ dữ liệu của tài khoản này sẽ bị xóa.`)) {
      return;
    }
    setError(null);
    try {
      await deleteUser(user.id);
      flash("Đã xóa tài khoản");
      await refresh();
    } catch (e) {
      setError(e.message);
    }
  };

  const handleResetSubmit = async (event) => {
    event.preventDefault();
    if (!resetTarget) return;
    setError(null);
    try {
      await resetUserPassword(resetTarget.id, resetPassword);
      flash(`Đã đặt lại mật khẩu cho "${resetTarget.username}"`);
      setResetTarget(null);
      setResetPassword("");
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <header className="modal-header">
          <h2>Quản trị tài khoản</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Đóng">
            ×
          </button>
        </header>

        <div className="modal-body">
          <section className="settings-section">
            <h3>Thêm tài khoản</h3>
            <form onSubmit={handleCreate} className="admin-create-form">
              <label className="field">
                <span>Tên đăng nhập</span>
                <input
                  type="text"
                  value={newUsername}
                  onChange={(e) => setNewUsername(e.target.value)}
                  minLength={3}
                  required
                />
              </label>
              <label className="field">
                <span>Mật khẩu tạm thời</span>
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  minLength={8}
                  required
                />
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={newIsAdmin}
                  onChange={(e) => setNewIsAdmin(e.target.checked)}
                />
                Cấp quyền quản trị viên
              </label>
              <button className="btn-primary" type="submit" disabled={creating}>
                {creating ? "Đang tạo..." : "Tạo tài khoản"}
              </button>
            </form>
          </section>

          <section className="settings-section">
            <h3>Danh sách tài khoản</h3>
            {loading ? (
              <p className="muted">Đang tải...</p>
            ) : (
              <table className="admin-user-table">
                <thead>
                  <tr>
                    <th>Tên đăng nhập</th>
                    <th>Quyền</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.id}>
                      <td>{u.username}</td>
                      <td>{u.is_admin ? "Admin" : "User"}</td>
                      <td className="admin-user-actions">
                        <button
                          type="button"
                          className="btn-ghost sm"
                          onClick={() => {
                            setResetTarget(u);
                            setResetPassword("");
                          }}
                        >
                          Đặt lại mật khẩu
                        </button>
                        <button
                          type="button"
                          className="btn-danger-ghost"
                          onClick={handleDelete(u)}
                          disabled={u.id === currentUserId}
                        >
                          Xóa
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          {resetTarget && (
            <section className="settings-section">
              <h3>Đặt lại mật khẩu cho "{resetTarget.username}"</h3>
              <form onSubmit={handleResetSubmit} className="admin-create-form">
                <label className="field">
                  <span>Mật khẩu mới</span>
                  <input
                    type="password"
                    value={resetPassword}
                    onChange={(e) => setResetPassword(e.target.value)}
                    minLength={8}
                    required
                  />
                </label>
                <div className="field-row">
                  <button className="btn-primary" type="submit">
                    Lưu mật khẩu mới
                  </button>
                  <button
                    type="button"
                    className="btn-ghost"
                    onClick={() => setResetTarget(null)}
                  >
                    Hủy
                  </button>
                </div>
              </form>
            </section>
          )}

          {error && <p className="error">{error}</p>}
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
