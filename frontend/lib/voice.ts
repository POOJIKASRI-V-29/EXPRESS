"use client";
/**
 * Browser speech, wrapped so the UI never has to think about vendor prefixes
 * or capability gaps.
 *
 * What this does NOT do, deliberately:
 *   • No audio is recorded, buffered or uploaded. `SpeechRecognition` hands
 *     back text; we never touch MediaRecorder or a raw stream, so there is no
 *     audio to leak or persist.
 *   • Nothing is spoken until the user has asked for voice at least once —
 *     browsers block autoplay anyway, and surprising speech is worse than none.
 *
 * Support is genuinely uneven. Recognition is a Chrome/Edge feature; **Safari
 * on iOS does not implement SpeechRecognition at all**, so on an iPhone the mic
 * is unavailable and the UI has to say so rather than appear broken. Synthesis
 * is far more widely available, including on iOS, but there it only starts from
 * inside a user gesture.
 */
import { useCallback, useEffect, useRef, useState } from "react";

export type VoiceState = "idle" | "listening" | "thinking" | "speaking" | "error";

export interface VoiceSupport {
  recognition: boolean;
  synthesis: boolean;
  /** Present when recognition is unavailable — shown verbatim to the user. */
  reason: string;
}

function detect(): VoiceSupport {
  if (typeof window === "undefined") {
    return { recognition: false, synthesis: false, reason: "" };
  }
  const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
  const synthesis = typeof window.speechSynthesis !== "undefined";
  if (SR) return { recognition: true, synthesis, reason: "" };

  const ua = navigator.userAgent;
  const iOS = /iPad|iPhone|iPod/.test(ua) ||
    (navigator.platform === "MacIntel" && (navigator as any).maxTouchPoints > 1);
  return {
    recognition: false,
    synthesis,
    reason: iOS
      ? "Speech recognition isn't available in Safari on iPhone or iPad — every browser there uses WebKit, so this affects Chrome and Firefox on iOS too. You can still type, and JOCasta can still speak replies."
      : "This browser doesn't support speech recognition. Chrome or Edge on desktop does. You can still type.",
  };
}

export function useVoice(opts: {
  /** Runs with the final transcript. Should return JOCasta's reply text. */
  onTranscript: (text: string) => Promise<string | void>;
}) {
  const [support, setSupport] = useState<VoiceSupport>({
    recognition: false, synthesis: false, reason: "",
  });
  const [state, setState] = useState<VoiceState>("idle");
  const [transcript, setTranscript] = useState("");
  const [error, setError] = useState("");
  /** Whether replies are spoken aloud. Off until the user turns it on. */
  const [speakReplies, setSpeakReplies] = useState(false);

  const recognitionRef = useRef<any>(null);
  const finalRef = useRef("");
  const onTranscriptRef = useRef(opts.onTranscript);
  onTranscriptRef.current = opts.onTranscript;

  useEffect(() => {
    setSupport(detect());
    // Restore the user's earlier choice about spoken replies.
    try {
      setSpeakReplies(localStorage.getItem("express_voice_replies") === "on");
    } catch { /* private mode — default to off */ }
  }, []);

  const setSpoken = useCallback((on: boolean) => {
    setSpeakReplies(on);
    try { localStorage.setItem("express_voice_replies", on ? "on" : "off"); } catch {}
    if (!on && typeof window !== "undefined") window.speechSynthesis?.cancel();
  }, []);

  const speak = useCallback((text: string) => {
    if (!text || typeof window === "undefined" || !window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 1.02;
    u.pitch = 1;
    u.onstart = () => setState("speaking");
    u.onend = () => setState("idle");
    u.onerror = () => setState("idle");
    window.speechSynthesis.speak(u);
  }, []);

  const stopSpeaking = useCallback(() => {
    if (typeof window !== "undefined") window.speechSynthesis?.cancel();
    setState("idle");
  }, []);

  const stop = useCallback(() => {
    try { recognitionRef.current?.stop(); } catch {}
    setState("idle");
  }, []);

  const listen = useCallback(() => {
    setError("");
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) { setError(detect().reason); setState("error"); return; }

    // Speaking over the mic would feed JOCasta its own words.
    window.speechSynthesis?.cancel();

    const rec = new SR();
    recognitionRef.current = rec;
    rec.lang = navigator.language || "en-US";
    rec.interimResults = true;      // so the user sees words appear as they talk
    rec.continuous = false;         // one utterance per tap
    rec.maxAlternatives = 1;
    finalRef.current = "";
    setTranscript("");

    rec.onstart = () => setState("listening");

    rec.onresult = (e: any) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const chunk = e.results[i][0].transcript;
        if (e.results[i].isFinal) finalRef.current += chunk;
        else interim += chunk;
      }
      setTranscript((finalRef.current + interim).trim());
    };

    rec.onerror = (e: any) => {
      const map: Record<string, string> = {
        "not-allowed": "Microphone access was blocked. Allow it in your browser settings and try again.",
        "service-not-allowed": "Microphone access was blocked by the browser.",
        "no-speech": "I didn't catch anything. Try again?",
        "audio-capture": "No microphone found.",
        network: "The speech service couldn't be reached.",
      };
      // An aborted recognition is the user stopping it — not an error.
      if (e.error === "aborted") { setState("idle"); return; }
      setError(map[e.error] || `Lost the thread (${e.error}).`);
      setState("error");
    };

    rec.onend = async () => {
      const said = finalRef.current.trim();
      if (!said) {
        setState((s) => (s === "error" ? "error" : "idle"));
        return;
      }
      setState("thinking");
      try {
        const reply = await onTranscriptRef.current(said);
        if (speakReplies && typeof reply === "string" && reply) speak(reply);
        else setState("idle");
      } catch (err: any) {
        setError(err?.message || "Lost the thread.");
        setState("error");
      }
    };

    try { rec.start(); }
    catch { setError("Couldn't start listening."); setState("error"); }
  }, [speakReplies, speak]);

  // Stop everything if the component goes away mid-utterance.
  useEffect(() => () => {
    try { recognitionRef.current?.abort(); } catch {}
    if (typeof window !== "undefined") window.speechSynthesis?.cancel();
  }, []);

  return {
    support, state, transcript, error,
    speakReplies, setSpokenReplies: setSpoken,
    listen, stop, speak, stopSpeaking,
    reset: () => { setError(""); setTranscript(""); setState("idle"); },
  };
}
