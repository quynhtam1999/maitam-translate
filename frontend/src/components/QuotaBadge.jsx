export default function QuotaBadge({ quota }) {
  if (!quota) return null;
  const rpdLeft = Math.max(0, quota.rpd_limit - quota.rpd_used);
  return (
    <p className="quota-badge">
      📊 Phút này: {quota.rpm_used}/{quota.rpm_limit} yêu cầu, {quota.tpm_used}/
      {quota.tpm_limit} token; hôm nay: {quota.rpd_used}/{quota.rpd_limit} yêu cầu (còn {rpdLeft})
    </p>
  );
}
