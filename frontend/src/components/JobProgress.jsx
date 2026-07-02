import { useEffect, useState } from "react";
import { listProviders, resumeJob } from "../api/translate.js";
import QuotaBadge from "./QuotaBadge.jsx";

const STATUS_LABEL = {
  queued: "Đang chờ...",
  running: "Đang dịch...",
  paused_quota: "Tạm dừng do quota",
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
        const firstUsable = list.find((p) => p.key_configured);
        setNewProvider(firstUsable ? firstUsable.name : "");
      });
    }
  }, [status?.status]);

  if (!status) return null;

  const { progress = {} } = status;
  const phase = progress.phase || "";
  const total = progress.segments_total || 0;
  const done = progress.segments_translated || 0;
  const percent = total ? Math.round((done / total) * 100) : 0;
  const isDailyLimit = /RPD|giới hạn ngày/i.test(status.error || "");
  const isActive = status.status === "running" || status.status === "queued";
  const isTranslating = phase === "translating" && total > 0;

  const phaseLabel = () => {
    if (phase === "extracting") return "Đang bóc tách cấu trúc PDF...";
    if (phase === "rendering") return "Đang chèn bản dịch và tạo file PDF...";
    if (isTranslating) return `Đang dịch ${done}/${total} đoạn (${percent}%)`;
    return "Đang chuẩn bị...";
  };

  const canResume = newProvider && providers.some((p) => p.name === newProvider && p.key_configured);

  const handleResume = async () => {
    if (!canResume) return;
    await resumeJob(status.job_id, newProvider);
    if (onResumed) onResumed();
  };

  return (
    <div className="job-progress">
      <p className="status-line">
        {isDailyLimit ? "Đã hết giới hạn ngày của model này" : STATUS_LABEL[status.status] || status.status}
      </p>

      {isActive && (
        <>
          <p className="progress-phase">{phaseLabel()}</p>
          <div className={`progress-bar${isTranslating ? "" : " indeterminate"}`}>
            <div
              className="progress-fill"
              style={isTranslating ? { width: `${percent}%` } : undefined}
            />
          </div>
          {isTranslating && (
            <p className="progress-text">
              {done}/{total} đoạn ({percent}%)
            </p>
          )}
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
          <button onClick={handleResume} disabled={!canResume}>Đổi mô hình & dịch tiếp</button>
        </div>
      )}

      {status.error && <p className="error">{status.error}</p>}
      <QuotaBadge quota={status.quota} />
    </div>
  );
}
