"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Shell } from "@/components/shell";
import { Atmosphere } from "@/components/atmosphere";
import { Icon } from "@/components/icons";
import { JocastaThinking } from "@/components/sense";
import { VoiceOrb, type VoiceState } from "@/components/voice-orb";
import { VoiceSettingsModal } from "@/components/voice-settings";
import { useVoice } from "@/lib/useVoice";
import { loadVoiceSettings, saveVoiceSettings, DEFAULT_VOICE_SETTINGS, type VoiceSettings } from "@/lib/voice";
import { useRequireAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import { titleCase } from "@/lib/format";
import type { JocastaResult } from "@/lib/types";

interface Msg { role: "me" | "joc"; text: string; result?: JocastaResult; }

const MODULE_HREF: Record<string, string> = {
  tasks: "/tasks", planner: "/planner", college: "/college", learning: "/learning",
  projects: "/projects", career: "/career", goals: "/goals", personal: "/personal",
  finance: "/finance", memory: "/memory", progress: "/progress", "spider-sense": "/",
};

const EXAMPLES = [
  "help me plan my week",
  "what's due?",
  "studied trees for 45 minutes",
  "spent 320 on food today",
  "remember I prefer DSA at night",
  "missed operating systems",
  "i'm behind, help me catch up",
];

/** The orchestrator's actual stages, walked while a request is in flight. */
const STAGES = [
  "Reading your current state…",
  "Working out which threads matter…",
  "Choosing what to do…",
];

/** Turn a raw SpeechRecognition error code into something a person can act on. */
function speechErrorText(code: string | null): string {
  switch (code) {
    case "not-allowed":
    case "service-not-allowed":
      return "Microphone access is blocked. Allow it in your browser settings, then tap again.";
    case "no-speech":
      return "I didn't catch anything — tap the orb and try again.";
    case "audio-capture":
      return "No microphone was found on this device.";
    case "network":
      return "The speech service is unreachable right now. You can type instead.";
    case "aborted":
      return "Listening stopped.";
    case "unsupported":
      return "Voice input isn't supported in this browser. You can type, and I can still read replies aloud.";
    default:
      return code ? "Voice input hit a problem — you can type instead." : "";
  }
}

/** What JOCasta should say out loud. A plan awaiting approval is never spoken as
 *  done — voice cannot approve a destructive action; that still happens on screen. */
function spokenReply(r: JocastaResult): string {
  if (r.pending) {
    return `${r.reply} I need your confirmation on screen before I make that change.`;
  }
  return r.reply;
}

export default function JocastaPage() {
  const { user, ready } = useRequireAuth();
  const router = useRouter();
  const [text, setText] = useState("");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState(0);
  /** Tokens already approved or dismissed, so a prompt can't be answered twice. */
  const [settled, setSettled] = useState<Record<string, "approved" | "cancelled">>({});

  useEffect(() => {
    if (!busy) { setStage(0); return; }
    const t = setInterval(() => setStage((i) => Math.min(i + 1, STAGES.length - 1)), 850);
    return () => clearInterval(t);
  }, [busy]);

  async function send(override?: string) {
    const t = (override ?? text).trim();
    if (!t || busy) return;
    setMsgs((m) => [...m, { role: "me", text: t }]);
    setText(""); setBusy(true);
    try {
      const res = await api.jocasta(t);
      setMsgs((m) => [...m, { role: "joc", text: res.reply, result: res }]);
    } catch (e: any) {
      setMsgs((m) => [...m, { role: "joc", text: "I hit an error: " + e.message }]);
    } finally { setBusy(false); }
  }

  async function approve(token: string) {
    if (busy) return;
    setBusy(true);
    try {
      const res = await api.jocastaConfirm(token);
      setSettled((s) => ({ ...s, [token]: "approved" }));
      setMsgs((m) => [...m, { role: "joc", text: res.reply, result: res }]);
    } catch (e: any) {
      setMsgs((m) => [...m, { role: "joc", text: "I couldn't apply that: " + e.message }]);
    } finally { setBusy(false); }
  }

  if (!ready || !user) return null;

  return (
    <>
      <Atmosphere />
      <Shell>
        <div className="eyebrow">JOCASTA · Neural Core</div>
        <h1 className="page-h" style={{ marginTop: 8 }}>Tell me once.</h1>
        <p className="page-sub">
          Capture anything, or ask me to plan. I read your real deadlines, free time and
          progress before I answer — and I&rsquo;ll show you anything destructive before I do it.
        </p>

        <div style={{ marginTop: 24, display: "flex", flexDirection: "column", gap: 12, minHeight: 220 }}>
          {msgs.length === 0 && (
            <div className="card">
              <div className="card-h"><span className="card-t">Trace a thread</span></div>
              <div className="chips">
                {EXAMPLES.map((e) => (
                  <button key={e} className="chip" style={{ textTransform: "none", letterSpacing: 0, fontWeight: 500 }}
                    onClick={() => send(e)}>{e}</button>
                ))}
              </div>
            </div>
          )}

          {msgs.map((m, i) => {
            if (m.role === "me") return <div className="bubble me" key={i}>{m.text}</div>;
            const r = m.result;
            const token = r?.confirm_token || "";
            const state = token ? settled[token] : undefined;
            const v = r?.verification;

            return (
              <div key={i}>
                <div className="gotit">
                  <div className="dot-on" />
                  <div style={{ flex: 1 }}>
                    <div className="plan-lines" style={{ color: "var(--text)", fontWeight: 500 }}>{m.text}</div>
                    {r && (r.calls.length > 0 || (r.context_used?.length ?? 0) > 0) && (
                      <div className="mini" style={{ marginTop: 6 }}>
                        {r.calls.length > 0 && (
                          <>{r.calls.map((c) => `${c.tool}${c.ok ? "" : " (failed)"}`).join(" · ")} · </>
                        )}
                        via {r.planner}
                        {r.context_used?.length ? ` · read ${r.context_used.join(", ")}` : ""}
                      </div>
                    )}
                    {v && v.failed > 0 && (
                      <div className="mini" style={{ marginTop: 6, color: "var(--red)" }}>
                        {v.succeeded}/{v.attempted} applied · {v.failures.map((f) => `${f.tool}: ${f.error}`).join("; ")}
                      </div>
                    )}
                  </div>
                </div>

                {r?.pending && token && !state && (
                  <div className="confirm-box">
                    <div className="lbl"><Icon.spider s={13} /> Needs your go-ahead</div>
                    <div className="why">{r.pending.reason}</div>
                    <ul>
                      {r.pending.actions.map((a, j) => (
                        <li key={j}>
                          <span className={"rk" + (a.risk === "sensitive" ? " sensitive" : "")}>{a.risk}</span>
                          <span>{a.summary}</span>
                        </li>
                      ))}
                    </ul>
                    <div style={{ display: "flex", gap: 10 }}>
                      <button className="btn sm amber" disabled={busy} onClick={() => approve(token)}>
                        <Icon.check s={14} /> Do it
                      </button>
                      <button className="btn sm" disabled={busy}
                        onClick={() => setSettled((s) => ({ ...s, [token]: "cancelled" }))}>
                        Leave it
                      </button>
                    </div>
                  </div>
                )}

                {state === "cancelled" && (
                  <div className="mini" style={{ marginTop: 8, paddingLeft: 4 }}>
                    Left alone — nothing was changed.
                  </div>
                )}

                {r && r.modules.length > 0 && (
                  <div className="chips" style={{ marginTop: 8 }}>
                    {r.modules.filter((x) => MODULE_HREF[x]).map((x) => (
                      <button key={x} className="chip" onClick={() => router.push(MODULE_HREF[x])}>
                        Open {titleCase(x)} <Icon.chev s={11} />
                      </button>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
          {busy && (
            <div className="bubble joc" style={{ paddingTop: 12, paddingBottom: 12 }}>
              <JocastaThinking stage={STAGES[stage]} />
            </div>
          )}
        </div>

        <div className="capture" style={{ marginTop: 12 }}>
          <input placeholder="Ask JOCasta…" value={text} aria-label="Message JOCasta"
            onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()} />
          <button className="mic" aria-label="Voice"><Icon.mic s={18} /></button>
          <button className="send" aria-label="Send" onClick={() => send()} disabled={busy || !text.trim()}>
            <Icon.send s={18} />
          </button>
        </div>
      </Shell>
    </>
  );
}
