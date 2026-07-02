import { useState } from "react";
import FileUpload from "./components/FileUpload.jsx";
import JobProgress from "./components/JobProgress.jsx";
import ResultView from "./components/ResultView.jsx";
import TextTranslate from "./components/TextTranslate.jsx";
import SettingsModal from "./components/SettingsModal.jsx";
import { createPdfJob, pollJobUntilDone } from "./api/translate.js";
import "./App.css";

export default function App() {
  const [tab, setTab] = useState("pdf");
  const [loading, setLoading] = useState(false);
  const [jobStatus, setJobStatus] = useState(null);
  const [error, setError] = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [providersVersion, setProvidersVersion] = useState(0);

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

  return (
    <div className="app">
      <header className="app-header">
        <img src="/logo.png" alt="Mai Tam Translate" className="logo" />
        <div className="app-header-text">
          <h1>Mai Tam Translate</h1>
          <p className="subtitle">
            Dịch tài liệu PDF y khoa sang tiếng Việt — giữ nguyên bố cục
          </p>
        </div>
        <button
          className="settings-btn"
          onClick={() => setSettingsOpen(true)}
          aria-label="Cài đặt"
          title="Cài đặt"
        >
          <span className="gear">⚙</span>
          <span className="settings-btn-label">Cài đặt</span>
        </button>
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
        <span>Engine: Gemini / Gemma · Qwen3 235B</span>
      </footer>

      <SettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onSaved={() => setProvidersVersion((v) => v + 1)}
      />
    </div>
  );
}
