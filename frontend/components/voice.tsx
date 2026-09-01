"use client";
/**
 * The JOCasta voice orb.
 *
 * Built from the same vocabulary as the rest of EXPRESS — nodes, threads and a
 * pulse — rather than a microphone glyph. Each state has a word next to it, so
 * the orb is decoration over a text status and never the only signal; with
 * reduced motion on, nothing is lost.
 */
import { Icon } from "./icons";
import type { VoiceState } from "@/lib/voice";

const COPY: Record<VoiceState, string> = {
  idle: "Tap to speak",
  listening: "Listening…",
  thinking: "Connecting threads…",
  speaking: "JOCasta is speaking…",
  error: "Lost the thread.",
};

export function VoiceOrb({
  state, transcript, error, supported, reason,
  speakReplies, onToggleSpoken, onStart, onStop, onStopSpeaking, onRetry,
}: {
  state: VoiceState;
  transcript: string;
  error: string;
  supported: boolean;
  reason: string;
  speakReplies: boolean;
  onToggleSpoken: (on: boolean) => void;
  onStart: () => void;
  onStop: () => void;
  onStopSpeaking: () => void;
  onRetry: () => void;
}) {
  const busy = state === "listening" || state === "thinking" || state === "speaking";
  const label = error && state === "error" ? error : COPY[state];

  return (
    <div className="voice" data-state={state}>
      <div className="voice-stage">
        <button
          className="orb"
          disabled={!supported && state !== "speaking"}
          aria-label={state === "listening" ? "Stop listening" : "Start speaking to JOCasta"}
          onClick={() => {
            if (state === "listening") return onStop();
            if (state === "speaking") return onStopSpeaking();
            if (state === "error") return onRetry();
            onStart();
          }}
        >
          <svg className="orb-svg" viewBox="0 0 140 140" aria-hidden="true">
            {/* Web geometry: spokes and rings, the same motif as the Sense Core. */}
            <g className="orb-web">
              {Array.from({ length: 10 }, (_, i) => {
                const a = (i / 10) * Math.PI * 2 - Math.PI / 2;
                return <line key={i} x1="70" y1="70"
                  x2={70 + Math.cos(a) * 62} y2={70 + Math.sin(a) * 62} />;
              })}
              {[26, 42, 58].map((r) => <circle key={r} cx="70" cy="70" r={r} />)}
            </g>
            {/* Ambient rings; their speed is set per state in CSS. */}
            {[0, 1, 2].map((i) => (
              <circle key={i} className="orb-ring" cx="70" cy="70" r="54" />
            ))}
            <circle className="orb-core" cx="70" cy="70" r="17" />
          </svg>

          <span className="orb-glyph">
            {state === "listening" ? <Icon.mic s={22} />
              : state === "speaking" ? <Icon.joc s={22} />
              : state === "error" ? <Icon.x s={22} />
              : <Icon.mic s={22} />}
          </span>
        </button>
      </div>

      <div className="voice-label" role="status" aria-live="polite">{label}</div>

      {transcript && (
        <div className="voice-transcript">&ldquo;{transcript}&rdquo;</div>
      )}

      {!supported && reason && (
        <div className="voice-note">{reason}</div>
      )}

      <div className="voice-actions">
        {state === "listening" && (
          <button className="btn sm" onClick={onStop}>Stop</button>
        )}
        {state === "speaking" && (
          <button className="btn sm" onClick={onStopSpeaking}>Stop speaking</button>
        )}
        {state === "error" && (
          <button className="btn sm" onClick={onRetry}>Try again</button>
        )}
        <button
          className={"chip" + (speakReplies ? " on" : "")}
          aria-pressed={speakReplies}
          onClick={() => onToggleSpoken(!speakReplies)}
        >
          {speakReplies ? "Spoken replies on" : "Spoken replies off"}
        </button>
      </div>
    </div>
  );
}
