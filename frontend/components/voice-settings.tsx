"use client";
/**
 * Voice settings — presentation only. Nothing here can change what an action
 * does on the server; it governs whether/how JOCasta speaks and whether a
 * finished phrase auto-sends. Built from the existing .modal / .field
 * primitives so it matches every other dialog in the app.
 */
import { Icon } from "./icons";
import type { VoiceSettings } from "@/lib/voice";
import type { VoiceSupport } from "@/lib/useVoice";

function Switch({
  on, onToggle, disabled, label,
}: {
  on: boolean; onToggle: () => void; disabled?: boolean; label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      className={"vswitch" + (on ? " on" : "")}
      disabled={disabled}
      onClick={onToggle}
    >
      <i />
    </button>
  );
}

export function VoiceSettingsModal({
  settings, support, voices, onChange, onClose, onTest,
}: {
  settings: VoiceSettings;
  support: VoiceSupport;
  voices: SpeechSynthesisVoice[];
  onChange: (patch: Partial<VoiceSettings>) => void;
  onClose: () => void;
  onTest: () => void;
}) {
  return (
    <div className="modal-wrap" role="dialog" aria-modal="true" aria-label="Voice settings" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
          <div>
            <h2>Voice</h2>
            <div className="sub">How JOCasta listens and speaks on this device.</div>
          </div>
          <button className="iconbtn sm" aria-label="Close" onClick={onClose}><Icon.x s={15} /></button>
        </div>

        {!support.recognition && (
          <div className="mini" style={{ marginTop: 14, color: "var(--red)", lineHeight: 1.5 }}>
            This browser can&rsquo;t transcribe speech (this is expected on iPhone Safari). You can still
            type, and JOCasta can read replies aloud if your device supports it.
          </div>
        )}

        <div style={{ marginTop: 16 }}>
          <div className="vrow">
            <div>
              <div className="vlabel">Read replies aloud</div>
              <div className="vsub">
                {support.synthesis ? "Speak each answer as it arrives." : "Not available in this browser."}
              </div>
            </div>
            <Switch
              label="Read replies aloud"
              on={settings.speakReplies && support.synthesis}
              disabled={!support.synthesis}
              onToggle={() => onChange({ speakReplies: !settings.speakReplies })}
            />
          </div>

          <div className="vrow">
            <div>
              <div className="vlabel">Send after speaking</div>
              <div className="vsub">
                {support.recognition
                  ? "Submit as soon as a phrase is captured."
                  : "Needs speech input, not available here."}
              </div>
            </div>
            <Switch
              label="Send after speaking"
              on={settings.autoSend && support.recognition}
              disabled={!support.recognition}
              onToggle={() => onChange({ autoSend: !settings.autoSend })}
            />
          </div>

          <div className="vrow">
            <div style={{ flex: 1 }}>
              <div className="vlabel">Speaking rate</div>
              <div className="vsub">{settings.rate.toFixed(2)}×</div>
            </div>
            <input
              className="vrange"
              type="range"
              min={0.7}
              max={1.4}
              step={0.05}
              value={settings.rate}
              disabled={!support.synthesis}
              aria-label="Speaking rate"
              onChange={(e) => onChange({ rate: Number(e.target.value) })}
            />
          </div>

          {support.synthesis && voices.length > 0 && (
            <div className="vrow" style={{ alignItems: "flex-start" }}>
              <div style={{ flex: 1 }}>
                <div className="vlabel">Voice</div>
                <div className="vsub">Uses your system voices.</div>
              </div>
              <select
                className="vselect"
                value={settings.voiceURI ?? ""}
                aria-label="Voice"
                onChange={(e) => onChange({ voiceURI: e.target.value || null })}
              >
                <option value="">Browser default</option>
                {voices.map((v) => (
                  <option key={v.voiceURI} value={v.voiceURI}>
                    {v.name} ({v.lang})
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        <div className="acts">
          {support.synthesis && (
            <button className="btn sm" onClick={onTest}>
              <Icon.joc s={14} /> Test voice
            </button>
          )}
          <button className="btn sm primary" onClick={onClose}>Done</button>
        </div>
      </div>
    </div>
  );
}
