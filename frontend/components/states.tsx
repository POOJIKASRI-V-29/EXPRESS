export function Loading({ label = "Connecting threads…" }: { label?: string }) {
  return <div className="center-state"><div className="spinner" /><div>{label}</div></div>;
}
export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="center-state">
      <div style={{ color: "var(--red)" }}>Lost the thread</div>
      <div style={{ color: "var(--text-3)" }}>{message}</div>
      {onRetry && <button className="btn sm" onClick={onRetry}>Try again</button>}
    </div>
  );
}
export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="empty">{children}</div>;
}
