import { useEffect, useState } from "react";
import { listProviders, translateText } from "../api/translate.js";
import { hasLocalKey, localKeyKindForProvider } from "../api/keys.js";
import QuotaBadge from "./QuotaBadge.jsx";

function isUsable(p) {
  const kind = localKeyKindForProvider(p.name);
  return p.key_configured || (kind && hasLocalKey(kind));
}

export default function TextTranslate({ refreshKey }) {
  const [providers, setProviders] = useState([]);
  const [provider, setProvider] = useState("");
  const [source, setSource] = useState("");
  const [result, setResult] = useState("");
  const [quota, setQuota] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    listProviders().then((list) => {
      setProviders(list);
      setProvider((prev) => {
        if (prev && list.some((p) => p.name === prev)) return prev;
        return list.length ? list[0].name : "";
      });
    });
  }, [refreshKey]);

  const handleTranslate = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await translateText(source, provider, "vi");
      setResult(data.translated_text);
      setQuota(data.quota);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="text-translate">
      <div className="text-toolbar">
        <select value={provider} onChange={(e) => setProvider(e.target.value)}>
          {providers.map((p) => (
            <option key={p.name} value={p.name} disabled={!isUsable(p)}>
              {p.display_name} {isUsable(p) ? "" : "(chưa có key)"}
            </option>
          ))}
        </select>
        <button onClick={handleTranslate} disabled={!source || !provider || loading}>
          {loading ? "Đang dịch..." : "Dịch →"}
        </button>
      </div>

      <div className="text-columns">
        <textarea
          placeholder="Dán văn bản cần dịch..."
          value={source}
          onChange={(e) => setSource(e.target.value)}
        />
        <textarea placeholder="Bản dịch tiếng Việt..." value={result} readOnly />
      </div>

      {error && <p className="error">{error}</p>}
      <QuotaBadge quota={quota} />
    </div>
  );
}
