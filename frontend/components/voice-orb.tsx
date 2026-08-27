"use client";
/**
 * The Voice Orb — the single tappable affordance for talking to JOCasta.
 *
 * Built from the same primitives as the Sense Core (radial web geometry, a
 * central figure, ambient halos) so voice reads as part of the one system
 * rather than a bolted-on widget. Following the Spider-Sense rule, every state
 * carries a word — the label below is the real signal; the motion only
 * decorates it, and the global prefers-reduced-motion rule disables all of it.
 */
import { Icon } from "./icons";

export type VoiceState =
  | "idle"        // ready, waiting for a tap
  | "listening"   // mic open, transcribing
  | "thinking"    // request in flight to JOCasta
  | "speaking"    // reading a reply aloud
  | "error"       // mic/permission problem, recoverable
  | "unsupported"; // no SpeechRecognition in this browser (e.g. iOS Safari)

const COPY: Record<VoiceState, string> = {
  idle: "Tap to speak",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
  error: "Mic unavailable",
  unsupported: "Voice input not supported here",
};

export function VoiceOrb({
  state,
  onClick,
  disabled = false,
}: {
  state: VoiceState;
  onClick?: () => void;
  disabled?: boolean;
}) {
  // Twelve spokes + three arcs: the faint web behind the core, structural not
  // illustrative — identical construction to SenseCore, scaled to 120px.
  const spokes = Array.from({ length: 12 }, (_, i) => {
    const a = (i / 12) * Math.PI * 2 - Math.PI / 2;
    return { x: 60 + Math.cos(a) * 52, y: 60 + Math.sin(a) * 52 };
  });

  const label = COPY[state];
  const interactive = state !== "unsupported" && !disabled;

  return (
    <div className="voice-orb-wrap" data-state={state}>
      <button
        type="button"
        className="voice-orb"
        data-state={state}
        onClick={onClick}
        disabled={!interactive}
        aria-pressed={state === "listening"}
        aria-label={interactive ? "Talk to JOCasta" : label}
      >
        <svg className="orb-web" viewBox="0 0 120 120" aria-hidden="true">
          <g className="orb-spokes">
            {spokes.map((p, i) => (
              <line key={i} x1="60" y1="60" x2={p.x} y2={p.y} />
            ))}
            {[22, 38, 52].map((r) => (
              <circle key={r} cx="60" cy="60" r={r} />
            ))}
          </g>
          {/* Ambient halos — pure ambience, they encode nothing. */}
          {[0, 1, 2].map((i) => (
            <circle key={i} className="orb-halo" cx="60" cy="60" r="46" />
          ))}
        </svg>

        <span className="orb-core">
          {state === "speaking" ? (
            <span className="orb-eq" aria-hidden="true">
              <i /><i /><i /><i />
            </span>
          ) : (
            <Icon.mic s={26} />
          )}
        </span>
      </button>

      {/* The word is the signal. Colour and motion are redundant to it. */}
      <div className="voice-orb-label" role="status" aria-live="polite">
        {label}
      </div>
    </div>
  );
}
