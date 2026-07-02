import { useState } from "react";
import { login, register } from "../api/translate.js";

export default function AuthPage({ onAuthed }) {
  const [mode, setMode] = useState("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const isRegister = mode === "register";

  const handleSubmit = async (event) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const data = isRegister
        ? await register(username.trim(), password)
        : await login(username.trim(), password);
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
          {isRegister ? "Tạo tài khoản để lưu API key riêng." : "Đăng nhập để sử dụng ứng dụng."}
        </p>

        <div className="auth-tabs" role="tablist">
          <button
            type="button"
            className={mode === "login" ? "active" : ""}
            onClick={() => setMode("login")}
          >
            Đăng nhập
          </button>
          <button
            type="button"
            className={mode === "register" ? "active" : ""}
            onClick={() => setMode("register")}
          >
            Tạo tài khoản
          </button>
        </div>

        <label className="field">
          <span>Tên đăng nhập</span>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            minLength={3}
            required
          />
        </label>

        <label className="field">
          <span>Mật khẩu</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={isRegister ? "new-password" : "current-password"}
            minLength={isRegister ? 8 : 1}
            required
          />
        </label>

        {isRegister && <p className="muted sm">Mật khẩu cần tối thiểu 8 ký tự.</p>}
        {error && <p className="error">{error}</p>}

        <button className="btn-primary auth-submit" type="submit" disabled={loading}>
          {loading ? "Đang xử lý..." : isRegister ? "Tạo tài khoản" : "Đăng nhập"}
        </button>
      </form>
    </div>
  );
}
