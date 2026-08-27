"use client";
/**
 * Spider-Sense visual primitives.
 *
 * The concept: things in EXPRESS are nodes, relationships between them are
 * threads, and the system noticing something is a pulse. Everything here is
 * built from those three ideas, so the interface reads as one system rather
 * than a set of unrelated widgets.
 *
 * Two rules hold throughout:
 *   1. Nothing here invents data. Every number traces to a real record, and
 *      `deriveState` is deliberately simple enough to explain in a sentence.
 *   2. Motion is never the only signal. Each state also carries a word and a
 *      shape, so the UI is unchanged in meaning under prefers-reduced-motion.
 */
import { ReactNode } from "react";
import { Icon } from "./icons";
import type { Notification } from "@/lib/types";

export type SenseState = "calm" | "steady" | "attention" | "critical";

/** Copy for each state. The label is what makes the colour redundant. */
const STATE_COPY: Record<SenseState, { label: string; icon: keyof typeof Icon }> = {
  calm: { label: "Quiet", icon: "check" },
  steady: { label: "Steady", icon: "joc" },
  attention: { label: "Needs attention", icon: "spider" },
  critical: { label: "Spider Sense", icon: "spider" },
};

/**
 * Turn real signals into an ambient state.
 *
 * Transparent by design — severity comes straight from Spider Sense, which
 * derives it from actual records. No score is synthesised.
 */
export function deriveState(signals: Notification[], scheduledToday = 0): SenseState {
  if (signals.some((s) => s.severity >= 5)) return "critical";
  if (signals.some((s) => s.severity >= 3)) return "attention";
  if (signals.length > 0 || scheduledToday > 0) return "steady";
  return "calm";
}

/** Signals that genuinely want an action, as opposed to being informational. */
export function pressing(signals: Notification[]): Notification[] {
  return signals.filter((s) => s.severity >= 3);
}

/* ────────────────────────────────────────────────────────────────────────
   Sense Core
   A hero figure inside a meter. The figure is a count of real signals; the
   meter is a real ratio (today's items finished over today's items). The
   rings are ambience and encode nothing.
   ──────────────────────────────────────────────────────────────────────── */
export function SenseCore({
  state, count, done, total, note,
}: {
  state: SenseState;
  count: number;
  done: number;
  total: number;
  note?: string;
}) {
  const R = 92;
  const C = 2 * Math.PI * R;
  const ratio = total > 0 ? done / total : 0;
  const copy = STATE_COPY[state];
  const StateIcon = Icon[copy.icon];

  // Faint web geometry — radial spokes and arcs. Structural, not illustrative.
  const spokes = Array.from({ length: 12 }, (_, i) => {
    const a = (i / 12) * Math.PI * 2 - Math.PI / 2;
    return { x: 116 + Math.cos(a) * 112, y: 116 + Math.sin(a) * 112 };
  });

  const summary =
    total > 0
      ? `${done} of ${total} scheduled items done today`
      : "Nothing scheduled today";

  return (
    <div className="sense" data-state={state}>
      <div className="sense-stage">
        <svg className="sense-svg" viewBox="0 0 232 232" aria-hidden="true">
          <g className="sense-web">
            {spokes.map((p, i) => (
              <line key={i} x1="116" y1="116" x2={p.x} y2={p.y} />
            ))}
            {[46, 74, 102].map((r) => (
              <circle key={r} cx="116" cy="116" r={r} />
            ))}
          </g>

          {/* Ambient rings. Three, staggered, so the breath overlaps softly. */}
          {[0, 1, 2].map((i) => (
            <circle key={i} className="sense-halo" cx="116" cy="116" r={R} />
          ))}

          <circle className="sense-track" cx="116" cy="116" r={R} />
          <circle
            className="sense-meter"
            cx="116" cy="116" r={R}
            strokeDasharray={C}
            strokeDashoffset={C * (1 - ratio)}
            transform="rotate(-90 116 116)"
          />
        </svg>

        <div className="sense-face">
          {count > 0 ? (
            <>
              <div className="sense-figure">{count}</div>
              <div className="sense-unit">{count === 1 ? "thing to handle" : "things to handle"}</div>
            </>
          ) : (
            <div className="sense-figure quiet">The web is quiet.</div>
          )}
          <div className="sense-state">
            <StateIcon s={12} /> {copy.label}
          </div>
        </div>
      </div>

      {/* The meter's value in words — the ring alone is not a readable number. */}
      <div className="sense-note">{note || summary}</div>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────────
   Thread — a vertical line with nodes on it.
   Used for the day's timeline and for any chain of related records.
   ──────────────────────────────────────────────────────────────────────── */
export function Thread({ children }: { children: ReactNode }) {
  return <div className="thread">{children}</div>;
}

export function ThreadRow({
  when, title, meta, tone = "idle", lit = false, right, onClick,
}: {
  when?: string;
  title: ReactNode;
  meta?: ReactNode;
  /** idle · now (happening) · done (settled) · alert (wants attention) */
  tone?: "idle" | "now" | "done" | "alert";
  lit?: boolean;
  right?: ReactNode;
  onClick?: () => void;
}) {
  const body = (
    <>
      {when !== undefined && <div className="thread-when">{when}</div>}
      <div className={"thread-rail" + (lit ? " lit" : "")}>
        <span className="thread-node" />
      </div>
      <div className="thread-body">
        <div className="thread-title">{title}</div>
        {meta && <div className="thread-meta">{meta}</div>}
      </div>
      {right}
    </>
  );

  // Only render a button when it actually does something, so keyboard users
  // aren't given empty tab stops.
  return onClick ? (
    <div className={`thread-row ${tone}`}>
      <button
        onClick={onClick}
        style={{ display: "contents", textAlign: "left" }}
        aria-label={typeof title === "string" ? title : undefined}
      >
        {body}
      </button>
    </div>
  ) : (
    <div className={`thread-row ${tone}`}>{body}</div>
  );
}

/* ────────────────────────────────────────────────────────────────────────
   JOCasta thinking — nodes finding each other.
   The stage label is the real status; the animation decorates it.
   ──────────────────────────────────────────────────────────────────────── */
export function JocastaThinking({ stage, label = "Connecting threads…" }:
  { stage?: string; label?: string }) {
  const nodes = [
    { cx: 23, cy: 6 }, { cx: 40, cy: 18 }, { cx: 34, cy: 38 },
    { cx: 12, cy: 38 }, { cx: 6, cy: 18 },
  ];
  return (
    <div className="think" role="status" aria-live="polite">
      <svg className="think-web" viewBox="0 0 46 46" aria-hidden="true">
        {nodes.map((n, i) => {
          const next = nodes[(i + 1) % nodes.length];
          return <line key={i} x1={n.cx} y1={n.cy} x2={next.cx} y2={next.cy} />;
        })}
        {nodes.map((n, i) => <circle key={i} cx={n.cx} cy={n.cy} r={2.4} />)}
      </svg>
      <div>
        <div className="think-label">{label}</div>
        {stage && <div className="think-stage">{stage}</div>}
      </div>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────────
   Signal — what happened, why it matters, and the one thing to do.
   ──────────────────────────────────────────────────────────────────────── */
const SEV_WORD: Record<number, string> = {
  5: "Critical", 4: "Critical", 3: "Act", 2: "Watch", 1: "Info",
};

export function SignalRow({
  signal, onAct, onDismiss,
}: {
  signal: Notification;
  onAct?: (s: Notification) => void;
  onDismiss?: (s: Notification) => void;
}) {
  return (
    <div className="signal" data-sev={signal.severity}>
      <span className="signal-mark" aria-hidden="true" />
      <div className="signal-body">
        <div className="signal-title">{signal.title}</div>
        {signal.explanation && <div className="signal-why">{signal.explanation}</div>}
        <div className="signal-foot">
          <span className="signal-sev">{SEV_WORD[signal.severity] || "Info"}</span>
          {signal.action_label && onAct && (
            <button className="link" onClick={() => onAct(signal)}>
              {signal.action_label} <Icon.chev s={11} />
            </button>
          )}
        </div>
      </div>
      {onDismiss && (
        <button className="iconbtn sm" aria-label={`Dismiss: ${signal.title}`}
          onClick={() => onDismiss(signal)}>
          <Icon.check s={13} />
        </button>
      )}
    </div>
  );
}
