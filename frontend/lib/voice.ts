/**
 * Voice preferences. These are UI-only presentation settings (does JOCasta
 * read replies aloud, how fast, which voice) — they never change what the
 * backend does. Every actual action still goes through /jocasta/message and
 * the same confirmation handshake as typed input, so voice can't bypass the
 * safety tier: a destructive plan is still approved by tapping on screen.
 */
export interface VoiceSettings {
  /** Read JOCasta's replies aloud via SpeechSynthesis. */
  speakReplies: boolean;
  /** Send automatically when a spoken phrase finalises (vs. drop it in the box). */
  autoSend: boolean;
  /** SpeechSynthesis rate, 0.7–1.4. */
  rate: number;
  /** Chosen voice, by voiceURI. null = the browser default. */
  voiceURI: string | null;
}

export const DEFAULT_VOICE_SETTINGS: VoiceSettings = {
  speakReplies: true,
  autoSend: true,
  rate: 1,
  voiceURI: null,
};

const KEY = "express_voice_settings";

export function loadVoiceSettings(): VoiceSettings {
  if (typeof window === "undefined") return DEFAULT_VOICE_SETTINGS;
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return DEFAULT_VOICE_SETTINGS;
    const parsed = JSON.parse(raw) as Partial<VoiceSettings>;
    // Merge over defaults so an older/partial payload can't produce holes.
    return {
      speakReplies: parsed.speakReplies ?? DEFAULT_VOICE_SETTINGS.speakReplies,
      autoSend: parsed.autoSend ?? DEFAULT_VOICE_SETTINGS.autoSend,
      rate:
        typeof parsed.rate === "number" && parsed.rate >= 0.5 && parsed.rate <= 2
          ? parsed.rate
          : DEFAULT_VOICE_SETTINGS.rate,
      voiceURI: parsed.voiceURI ?? null,
    };
  } catch {
    return DEFAULT_VOICE_SETTINGS;
  }
}

export function saveVoiceSettings(s: VoiceSettings) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    /* storage full or blocked — settings simply won't persist, which is fine. */
  }
}
