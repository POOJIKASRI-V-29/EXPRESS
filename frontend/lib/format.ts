/** Date/number formatting shared by every module page. */

export function fmtDue(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  const dayDiff = Math.round(
    (new Date(iso).setHours(0, 0, 0, 0) - new Date().setHours(0, 0, 0, 0)) / 86400000,
  );
  const t = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (dayDiff === 0) return `Today, ${t}`;
  if (dayDiff === 1) return `Tomorrow, ${t}`;
  if (dayDiff === -1) return `Yesterday, ${t}`;
  return `${d.toLocaleDateString([], { month: "short", day: "numeric" })}, ${t}`;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
}

export function fmtShort(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString([], { month: "short", day: "numeric" });
}

export function daysUntil(iso: string | null | undefined): number | null {
  if (!iso) return null;
  return Math.round((new Date(iso).setHours(0, 0, 0, 0) - new Date().setHours(0, 0, 0, 0)) / 86400000);
}

export function isOverdue(iso: string | null | undefined): boolean {
  return !!iso && new Date(iso).getTime() < Date.now();
}

/** Value for <input type="datetime-local">, in the browser's local zone. */
export function toLocalInput(iso?: string | null, fallbackHour = 9, dayOffset = 0): string {
  const d = iso ? new Date(iso) : new Date();
  if (!iso) {
    d.setDate(d.getDate() + dayOffset);
    d.setHours(fallbackHour, 0, 0, 0);
  }
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** A datetime-local value back to an absolute ISO instant. */
export function fromLocalInput(v: string): string {
  return new Date(v).toISOString();
}

export function inDays(n: number, hour = 9): string {
  const d = new Date();
  d.setDate(d.getDate() + n);
  d.setHours(hour, 0, 0, 0);
  return d.toISOString();
}

export function money(n: number): string {
  return n.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

export function minutes(n: number): string {
  if (!n) return "0m";
  const h = Math.floor(n / 60), m = n % 60;
  return h ? `${h}h${m ? ` ${m}m` : ""}` : `${m}m`;
}

export function titleCase(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
