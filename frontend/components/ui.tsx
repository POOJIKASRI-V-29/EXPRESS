"use client";
import { useCallback, useEffect, useState, ReactNode } from "react";
import { Shell } from "./shell";
import { Atmosphere } from "./atmosphere";
import { Loading, ErrorState } from "./states";
import { Icon } from "./icons";
import { useRequireAuth } from "@/lib/auth";

type State = "loading" | "error" | "ready";

/** Load one module's payload, with reload after every mutation. */
export function useModule<T>(loader: () => Promise<T>, deps: any[] = []) {
  const { user, ready } = useRequireAuth();
  const [data, setData] = useState<T | null>(null);
  const [state, setState] = useState<State>("loading");
  const [error, setError] = useState("");

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setState("loading");
    try {
      setData(await loader());
      setState("ready");
    } catch (e: any) {
      setError(e.message || "Request failed");
      setState("error");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => { if (ready && user) load(); }, [ready, user, load]);

  /** Run a mutation, then refresh from the server so the screen shows what was
   *  actually persisted rather than an optimistic guess. */
  const act = useCallback(async (fn: () => Promise<any>) => {
    try {
      await fn();
      await load(true);
    } catch (e: any) {
      setError(e.message || "Request failed");
      setState("error");
    }
  }, [load]);

  return { user, ready, data, setData, state, error, reload: load, act };
}

export function ModulePage({
  eyebrow, title, sub, actions, state, error, onRetry, red = false, children,
}: {
  eyebrow?: string; title: string; sub?: string; actions?: ReactNode;
  state: State; error: string; onRetry: () => void; red?: boolean; children: ReactNode;
}) {
  return (
    <>
      <Atmosphere red={red} />
      <Shell red={red}>
        <div className="head-row">
          <div>
            {eyebrow && <div className="eyebrow">{eyebrow}</div>}
            <h1 className="page-h" style={{ marginTop: eyebrow ? 8 : 0 }}>{title}</h1>
            {sub && <p className="page-sub">{sub}</p>}
          </div>
          {actions && <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>{actions}</div>}
        </div>
        {state === "loading" && <Loading />}
        {state === "error" && <ErrorState message={error} onRetry={onRetry} />}
        {state === "ready" && <div style={{ marginTop: 22 }}>{children}</div>}
      </Shell>
    </>
  );
}

export function Modal({
  title, sub, onClose, onSubmit, submitLabel = "Save", busy = false, children,
}: {
  title: string; sub?: string; onClose: () => void; onSubmit: () => void;
  submitLabel?: string; busy?: boolean; children: ReactNode;
}) {
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);

  return (
    <div className="modal-wrap" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <form className="modal" onSubmit={(e) => { e.preventDefault(); onSubmit(); }}>
        <h2>{title}</h2>
        {sub && <div className="sub">{sub}</div>}
        <div style={{ marginTop: 8 }}>{children}</div>
        <div className="acts">
          <button type="button" className="btn sm" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn sm primary" disabled={busy}>{busy ? "Saving…" : submitLabel}</button>
        </div>
      </form>
    </div>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="field">
      <label>{label}</label>
      {children}
      {hint && <div className="hint">{hint}</div>}
    </div>
  );
}

export function Bar({ pct, tone = "blue" }: { pct: number; tone?: "blue" | "red" | "plain" }) {
  return (
    <div className={"bar " + (tone === "plain" ? "" : tone)}>
      <i style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
    </div>
  );
}

export function Stat({ k, v, n, tone }: { k: string; v: ReactNode; n?: string; tone?: "red" | "green" }) {
  return (
    <div className={"stat" + (tone ? ` ${tone}` : "")}>
      <div className="k">{k}</div>
      <div className="v num">{v}</div>
      {n && <div className="n">{n}</div>}
    </div>
  );
}

export function AddButton({ onClick, label }: { onClick: () => void; label: string }) {
  return <button className="btn sm primary" onClick={onClick}><Icon.plus s={14} />{label}</button>;
}

export function IconAction({
  onClick, title, icon: I, danger = false,
}: { onClick: () => void; title: string; icon: any; danger?: boolean }) {
  return (
    <button className={"iconbtn sm" + (danger ? " danger" : "")} title={title} aria-label={title} onClick={onClick}>
      <I s={14} />
    </button>
  );
}

/** Confirms before running a destructive action, so a mis-click can't delete. */
export function useConfirm() {
  return useCallback((message: string, fn: () => void) => {
    if (typeof window === "undefined" || window.confirm(message)) fn();
  }, []);
}
