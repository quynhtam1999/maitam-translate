import { useEffect, useState } from "react";
import { listProviders } from "../api/translate.js";

export default function FileUpload({ onSubmit, loading, refreshKey }) {
  const [file, setFile] = useState(null);
  const [provider, setProvider] = useState("");
  const [forceRetranslate, setForceRetranslate] = useState(false);
  const [providers, setProviders] = useState([]);

  useEffect(() => {
    listProviders()
      .then((list) => {
        setProviders(list);
        setProvider((prev) => {
          if (prev && list.some((p) => p.name === prev)) return prev;
          return list.length ? list[0].name : "";
        });
      })
      .catch(() => setProviders([]));
  }, [refreshKey]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (file && provider) onSubmit(file, provider, { forceRetranslate });
  };

  return (
    <form onSubmit={handleSubmit} className="upload-form">
      <input type="file" accept=".pdf" onChange={(e) => setFile(e.target.files[0])} />

      <label>
        Mô hình dịch:
        <select value={provider} onChange={(e) => setProvider(e.target.value)}>
          {providers.map((p) => (
            <option key={p.name} value={p.name} disabled={!p.key_configured}>
              {p.display_name} {p.key_configured ? "" : "(chưa có key)"}
            </option>
          ))}
        </select>
      </label>

      <label className="checkbox">
        <input
          type="checkbox"
          checked={forceRetranslate}
          onChange={(e) => setForceRetranslate(e.target.checked)}
        />
        Dịch lại từ đầu
      </label>

      <button type="submit" disabled={!file || !provider || loading}>
        {loading ? "Đang dịch..." : "Dịch PDF"}
      </button>
    </form>
  );
}
