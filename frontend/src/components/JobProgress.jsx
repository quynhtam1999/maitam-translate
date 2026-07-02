import { useEffect, useState } from "react";
import { listProviders, resumeJob } from "../api/translate.js";
import QuotaBadge from "./QuotaBadge.jsx";

const STATUS_LABEL = {
  queued: "Đang chờ...",
  running: "Đang dịch...",
  paused_quota: "Đã hết quota — cần đổi mô hình để dịch tiếp",
  done: "Hoàn tất",
  failed: "Thất bại",
};

export default function JobProgress({ status, onResumed }) {
  const [providers, setProviders] = useState([]);
  const [newProvider, setNewProvider] = useState("");

  useEffect(() => {
    if (status?.status === "paused_quota") {
      listProviders().then((list) => {
        setProviders(list);
        if (list.length) setNewProvider(list[0].name);
      });
    }
  }, [status?.status]);

  if (!status) return null;

  const { progress = {} } = status;
  const total = progress.segments_total || 0;
  const done = progress.segments_translated || 0;
  const percent = total ? Math.round((done / total) * 100) : 0;

  const handleResume = async () => {
    await resumeJob(status.job_id, newProvider);
    if (onResumed) onResumed();
  };

  return (
    <div className="job-progress">
      <p className="status-line">{STATUS_LABEL[status.status] || status.status}</p>

      {(status.status === "running" || status.status === "queued") && total > 0 && (
        <>
          <div className="progress-bar">
            <div className="progress-fill" style={{ width: `${percent}%` }} />
          </div>
          <p className="progress-text">
            {done}/{total} đoạn ({percent}%)
          </p>
        </>
      )}

      {status.status === "paused_quota" && (
        <div className="resume-box">
          <select value={newProvider} onChange={(e) => setNewProvider(e.target.value)}>
            {providers.map((p) => (
              <option key={p.name} value={p.name} disabled={!p.key_configured}>
                {p.display_name}
              </option>
            ))}
          </select>
          <button onClick={handleResume}>Đổi mô hình & dịch tiếp</button>
        </div>
      )}

      {status.error && <p className="error">{status.error}</p>}
      <QuotaBadge quota={status.quota} />
    </div>
  );
}
