import { useState } from "react";
import { login } from "../api/translate.js";

export default function AuthPage({ onAuthed }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const data = await login(username.trim(), password);
      onAuthed(data.user);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-shell">
      <form className="auth-panel" onSubmit={handleSubmit}>
        <img src="/logo.png" alt="Mai Tam Translate" className="auth-logo" />
        <h1>Mai Tam Translate</h1>
        <p className="auth-subtitle">
          Đăng nhập để sử dụng ứng dụng. Tài khoản do quản trị viên cấp.
        </p>

        <label className="field">
          <span>Tên đăng nhập</span>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            required
          />
        </label>

        <label className="field">
          <span>Mật khẩu</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>

        {error && <p className="error">{error}</p>}

        <button className="btn-primary auth-submit" type="submit" disabled={loading}>
          {loading ? "Đang xử lý..." : "Đăng nhập"}
        </button>
      </form>
    </div>
  );
}
