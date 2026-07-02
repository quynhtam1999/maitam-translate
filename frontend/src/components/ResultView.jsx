import { downloadUrl } from "../api/translate.js";

export default function ResultView({ jobId, status }) {
  if (!jobId || status !== "done") return null;
  return (
    <div className="result-view">
      <h3>Kết quả</h3>
      <a className="download-btn" href={downloadUrl(jobId)} download>
        ⬇ Tải file đã dịch
      </a>
    </div>
  );
}
