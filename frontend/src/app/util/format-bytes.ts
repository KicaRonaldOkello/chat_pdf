/**
 * Formats a byte count using 1024-based steps (B, KB, MB, …).
 * The first division moves into KB so the label matches the magnitude of `v`.
 */
export function formatBytesBase2(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) {
    return '0 B';
  }
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  let v = bytes / 1024;
  const units = ['KB', 'MB', 'GB', 'TB'] as const;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v < 10 && i > 0 ? v.toFixed(1) : Math.round(v)} ${units[i]}`;
}

export function formatBytesBase2OrDash(bytes: number | null): string {
  if (bytes == null) {
    return '—';
  }
  return formatBytesBase2(bytes);
}
