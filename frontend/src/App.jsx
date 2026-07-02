import { useEffect, useState } from "react";
import AdminModal from "./components/AdminModal.jsx";
import AuthPage from "./components/AuthPage.jsx";
import ChangePasswordModal from "./components/ChangePasswordModal.jsx";
import FileUpload from "./components/FileUpload.jsx";
import JobProgress from "./components/JobProgress.jsx";
import ResultView from "./components/ResultView.jsx";
import TextTranslate from "./components/TextTranslate.jsx";
import SettingsModal from "./components/SettingsModal.jsx";
import { createPdfJob, getMe, logout, pollJobUntilDone } from "./api/translate.js";
import "./App.css";

export default function App() {
  const [user, setUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [tab, setTab] = useState("pdf");
  const [loading, setLoading] = useState(false);
  const [jobStatus, setJobStatus] = useState(null);
  const [error, setError] = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [adminOpen, setAdminOpen] = useState(false);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [providersVersion, setProvidersVersion] = useState(0);

  useEffect(() => {
    getMe()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setAuthLoading(false));
  }, []);

  const runPolling = (jobId) => {
    pollJobUntilDone(jobId, (s) => setJobStatus(s))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  const handleSubmit = async (file, provider, opts) => {
    setLoading(true);
    setError(null);
    setJobStatus(null);
    try {
      const { job_id } = await createPdfJob(file, provider, opts);
      runPolling(job_id);
    } catch (err) {
      setError(err.message);
      setLoading(false);
    }
  };

  const handleResumed = () => {
    if (jobStatus?.job_id) {
      setLoading(true);
      runPolling(jobStatus.job_id);
    }
  };

  const handleLogout = async () => {
    await logout().catch(() => {});
    setUser(null);
    setJobStatus(null);
    setError(null);
    setSettingsOpen(false);
    setAdminOpen(false);
    setPasswordOpen(false);
  };

  if (authLoading) {
    return (
      <div className="auth-shell">
        <div className="auth-panel compact">
          <img src="/logo.png" alt="Mai Tam Translate" className="auth-logo" />
          <p className="muted">Đang kiểm tra phiên đăng nhập...</p>
        </div>
      </div>
    );
  }

  if (!user) {
    return <AuthPage onAuthed={setUser} />;
  }

  return (
    <div className="app">
      <header className="app-header">
        <img src="/logo.png" alt="Mai Tam Translate" className="logo" />
        <div className="app-header-text">
          <h1>Mai Tam Translate</h1>
          <p className="subtitle">
            Dịch tài liệu PDF y khoa sang tiếng Việt - giữ nguyên bố cục
          </p>
        </div>
        <div className="header-actions">
          <span className="user-chip" title={user.username}>
            {user.username}
          </span>
          {user.is_admin && (
            <button
              className="btn-ghost"
              onClick={() => setAdminOpen(true)}
              title="Quản trị tài khoản"
            >
              Quản trị
            </button>
          )}
          <button
            className="settings-btn"
            onClick={() => setSettingsOpen(true)}
            aria-label="Cài đặt"
            title="Cài đặt"
          >
            <span className="gear">⚙</span>
            <span className="settings-btn-label">Cài đặt</span>
          </button>
          <button
            className="btn-ghost"
            onClick={() => setPasswordOpen(true)}
            title="Đổi mật khẩu"
          >
            Đổi mật khẩu
          </button>
          <button className="btn-ghost header-logout" onClick={handleLogout}>
            Đăng xuất
          </button>
        </div>
      </header>

      <nav className="tabs">
        <button className={tab === "pdf" ? "active" : ""} onClick={() => setTab("pdf")}>
          Dịch PDF
        </button>
        <button className={tab === "text" ? "active" : ""} onClick={() => setTab("text")}>
          Dịch văn bản
        </button>
      </nav>

      <main className="card">
        {tab === "pdf" && (
          <section>
            <FileUpload
              onSubmit={handleSubmit}
              loading={loading}
              refreshKey={providersVersion}
            />
            {error && <p className="error">{error}</p>}
            <JobProgress status={jobStatus} onResumed={handleResumed} />
            <ResultView jobId={jobStatus?.job_id} status={jobStatus?.status} />
          </section>
        )}

        {tab === "text" && <TextTranslate refreshKey={providersVersion} />}
      </main>

      <footer className="app-footer">
        <span>Engine: Gemini / Gemma - Qwen3 235B</span>
      </footer>

      <SettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onSaved={() => setProvidersVersion((v) => v + 1)}
      />

      <ChangePasswordModal
        open={passwordOpen}
        onClose={() => setPasswordOpen(false)}
      />

      {user.is_admin && (
        <AdminModal
          open={adminOpen}
          onClose={() => setAdminOpen(false)}
          currentUserId={user.id}
        />
      )}
    </div>
  );
}
