/**
 * Ambient declarations for the SpeechRecognition half of the Web Speech API.
 * The TS DOM lib ships `speechSynthesis`/`SpeechSynthesisUtterance` but omits
 * recognition, and the vendor-prefixed `webkitSpeechRecognition` entirely — so
 * we declare just enough of the shape we actually use, typed rather than `any`.
 */
interface SpeechRecognitionAlternative {
  readonly transcript: string;
  readonly confidence: number;
}
interface SpeechRecognitionResult {
  readonly length: number;
  readonly isFinal: boolean;
  item(index: number): SpeechRecognitionAlternative;
  [index: number]: SpeechRecognitionAlternative;
}
interface SpeechRecognitionResultList {
  readonly length: number;
  item(index: number): SpeechRecognitionResult;
  [index: number]: SpeechRecognitionResult;
}
interface SpeechRecognitionEvent extends Event {
  readonly resultIndex: number;
  readonly results: SpeechRecognitionResultList;
}
interface SpeechRecognitionErrorEvent extends Event {
  /** "not-allowed" | "no-speech" | "audio-capture" | "network" | "aborted" | … */
  readonly error: string;
  readonly message: string;
}
interface SpeechRecognition extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((this: SpeechRecognition, ev: SpeechRecognitionEvent) => unknown) | null;
  onerror: ((this: SpeechRecognition, ev: SpeechRecognitionErrorEvent) => unknown) | null;
  onend: ((this: SpeechRecognition, ev: Event) => unknown) | null;
  onstart: ((this: SpeechRecognition, ev: Event) => unknown) | null;
  onspeechend: ((this: SpeechRecognition, ev: Event) => unknown) | null;
}
type SpeechRecognitionCtor = { prototype: SpeechRecognition; new (): SpeechRecognition };
declare var SpeechRecognition: SpeechRecognitionCtor;

interface Window {
  SpeechRecognition?: SpeechRecognitionCtor;
  webkitSpeechRecognition?: SpeechRecognitionCtor;
}
