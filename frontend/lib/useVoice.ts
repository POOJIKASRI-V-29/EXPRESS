"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import type { VoiceSettings } from "./voice";

export interface VoiceSupport {
  /** SpeechRecognition — absent on iOS Safari and older browsers. */
  recognition: boolean;
  /** SpeechSynthesis — present almost everywhere, including iOS. */
  synthesis: boolean;
}

/**
 * One hook over both halves of the Web Speech API.
 *
 * Design notes that matter for real devices:
 *  - iOS Safari has no SpeechRecognition, so `support.recognition` gates all
 *    mic UI and the app stays fully usable by typing.
 *  - SpeechSynthesis on iOS only unlocks after a user gesture, so `prime()` is
 *    called from the tap that starts a voice interaction.
 *  - Chrome silently pauses utterances longer than ~15s; a resume pump keeps
 *    long replies going and is torn down as soon as speech ends.
 */
export function useVoice(settings: VoiceSettings) {
  const [support, setSupport] = useState<VoiceSupport>({ recognition: false, synthesis: false });
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [interim, setInterim] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);

  const recRef = useRef<SpeechRecognition | null>(null);
  const finalCbRef = useRef<((t: string) => void) | null>(null);
  const finalTextRef = useRef("");
  const primedRef = useRef(false);
  const pumpRef = useRef<number | null>(null);

  // Latest settings without forcing speak()/start() to be re-created each render.
  const settingsRef = useRef(settings);
  settingsRef.current = settings;

  // ---- feature detection + voice list (client only) ----
  useEffect(() => {
    if (typeof window === "undefined") return;
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    const hasSynth = "speechSynthesis" in window;
    setSupport({ recognition: !!SR, synthesis: hasSynth });

    if (!hasSynth) return;
    const loadVoices = () => setVoices(window.speechSynthesis.getVoices());
    loadVoices(); // may be empty on first call…
    window.speechSynthesis.addEventListener("voiceschanged", loadVoices); // …filled here
    return () => window.speechSynthesis.removeEventListener("voiceschanged", loadVoices);
  }, []);

  const clearPump = () => {
    if (pumpRef.current !== null) {
      window.clearInterval(pumpRef.current);
      pumpRef.current = null;
    }
  };

  const stopSpeaking = useCallback(() => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    clearPump();
    window.speechSynthesis.cancel();
    setSpeaking(false);
  }, []);

  /** Unlock SpeechSynthesis on iOS by speaking an empty utterance under a gesture. */
  const prime = useCallback(() => {
    if (primedRef.current) return;
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    try {
      const u = new SpeechSynthesisUtterance("");
      u.volume = 0;
      window.speechSynthesis.speak(u);
      window.speechSynthesis.cancel();
      primedRef.current = true;
    } catch {
      /* ignore — worst case the first spoken reply is silent on iOS */
    }
  }, []);

  const speak = useCallback((text: string) => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    const clean = text.trim();
    if (!clean) return;
    const synth = window.speechSynthesis;
    synth.cancel();
    clearPump();

    const u = new SpeechSynthesisUtterance(clean);
    const s = settingsRef.current;
    u.rate = s.rate;
    if (s.voiceURI) {
      const chosen = synth.getVoices().find((v) => v.voiceURI === s.voiceURI);
      if (chosen) u.voice = chosen;
    }
    u.onstart = () => setSpeaking(true);
    u.onend = () => { setSpeaking(false); clearPump(); };
    u.onerror = () => { setSpeaking(false); clearPump(); };
    synth.speak(u);

    // Chrome pauses long utterances; nudge it. Short replies clear this on end
    // before it ever fires.
    pumpRef.current = window.setInterval(() => {
      if (!synth.speaking) { clearPump(); return; }
      synth.pause();
      synth.resume();
    }, 10000);
  }, []);

  const stop = useCallback(() => {
    const r = recRef.current;
    if (r) { try { r.stop(); } catch { /* not started */ } }
  }, []);

  const start = useCallback((onFinal: (t: string) => void) => {
    if (typeof window === "undefined") return;
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { setError("unsupported"); return; }

    prime();        // grab the gesture to unlock TTS for the eventual reply
    stopSpeaking(); // don't let the mic hear JOCasta talking
    setError(null);
    setInterim("");
    finalCbRef.current = onFinal;
    finalTextRef.current = "";

    let rec = recRef.current;
    if (!rec) {
      rec = new SR();
      recRef.current = rec;
    }
    rec.lang = navigator.language || "en-US";
    rec.continuous = false;
    rec.interimResults = true;
    rec.maxAlternatives = 1;

    rec.onresult = (e: SpeechRecognitionEvent) => {
      let live = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const result = e.results[i];
        const phrase = result[0]?.transcript ?? "";
        if (result.isFinal) finalTextRef.current += phrase;
        else live += phrase;
      }
      setInterim(live);
    };
    rec.onerror = (e: SpeechRecognitionErrorEvent) => {
      setError(e.error || "error");
      setListening(false);
    };
    rec.onend = () => {
      setListening(false);
      setInterim("");
      const text = finalTextRef.current.trim();
      if (text && finalCbRef.current) finalCbRef.current(text);
    };

    try {
      rec.start();
      setListening(true);
    } catch {
      // start() throws if it's already running — treat as already listening.
      setListening(true);
    }
  }, [prime, stopSpeaking]);

  // Tear everything down on unmount so a navigation can't leave the mic hot or
  // the synth talking.
  useEffect(() => {
    return () => {
      try { recRef.current?.abort(); } catch { /* noop */ }
      clearPump();
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  return {
    support, listening, speaking, interim, error, voices,
    start, stop, speak, stopSpeaking, prime, setError,
  };
}
