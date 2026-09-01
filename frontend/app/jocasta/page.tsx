"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Shell } from "@/components/shell";
import { Atmosphere } from "@/components/atmosphere";
import { Icon } from "@/components/icons";
import { JocastaThinking } from "@/components/sense";
import { VoiceOrb } from "@/components/voice";
import { useVoice } from "@/lib/voice";
import { useRequireAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import { titleCase } from "@/lib/format";
import type { AttachmentInfo, JocastaResult } from "@/lib/types";

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

export default function JocastaPage() {
  const { user, ready } = useRequireAuth();
  const router = useRouter();
  const [text, setText] = useState("");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState(0);
  /** Tokens already approved or dismissed, so a prompt can't be answered twice. */
  const [settled, setSettled] = useState<Record<string, "approved" | "cancelled">>({});
  const [mode, setMode] = useState<"text" | "voice">("text");
  /** The file the next message applies to. Cleared once it has been sent. */
  const [attached, setAttached] = useState<AttachmentInfo | null>(null);
  const [uploading, setUploading] = useState(false);
  const [attachError, setAttachError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const voice = useVoice({ onTranscript: (said) => send(said) });

  useEffect(() => {
    if (!busy) { setStage(0); return; }
    const t = setInterval(() => setStage((i) => Math.min(i + 1, STAGES.length - 1)), 850);
    return () => clearInterval(t);
  }, [busy]);

  /**
   * The single entry point for a message, whatever produced it.
   *
   * Voice deliberately has no command system of its own: a transcript is just
   * text, so it goes through this exact call and therefore through the same
   * tools, the same validation and the same confirmation gate. Returns the
   * reply so voice can speak it.
   */
  async function send(override?: string): Promise<string> {
    const t = (override ?? text).trim();
    if (!t || busy) return "";
    setMsgs((m) => [...m, { role: "me", text: t }]);
    setText(""); setBusy(true);
    try {
      const res = await api.jocasta(t, attached?.attachment_token);
      setMsgs((m) => [...m, { role: "joc", text: res.reply, result: res }]);
      // A plan awaiting approval is never auto-applied, by voice or otherwise.
      return res.pending
        ? `${res.reply} Say nothing yet — approve it on screen.`
        : res.reply;
    } catch (e: any) {
      const msg = "Lost the thread — " + e.message;
      setMsgs((m) => [...m, { role: "joc", text: msg }]);
      return msg;
    } finally {
      setBusy(false);
      // One instruction per attachment: the user re-attaches to do more.
      setAttached(null);
    }
  }

  async function pickFile(file: File | undefined) {
    if (!file) return;
    setAttachError(""); setUploading(true);
    try {
      setAttached(await api.uploadAttachment(file));
    } catch (e: any) {
      setAttachError(e.message || "I couldn't read that file.");
      setAttached(null);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
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

        <div className="tabs" style={{ marginTop: 20 }}>
          <button className={"tab" + (mode === "text" ? " on" : "")}
            onClick={() => setMode("text")}>Type</button>
          <button className={"tab" + (mode === "voice" ? " on" : "")}
            onClick={() => setMode("voice")}>Speak</button>
        </div>

        {mode === "voice" && (
          <div className="card" style={{ marginTop: 16 }}>
            <VoiceOrb
              state={busy && voice.state === "idle" ? "thinking" : voice.state}
              transcript={voice.transcript}
              error={voice.error}
              supported={voice.support.recognition}
              reason={voice.support.reason}
              speakReplies={voice.speakReplies}
              onToggleSpoken={voice.setSpokenReplies}
              onStart={voice.listen}
              onStop={voice.stop}
              onStopSpeaking={voice.stopSpeaking}
              onRetry={voice.reset}
            />
          </div>
        )}

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
                    {/* No "via rules · read learning · memory" line: it reads as a
                        console trace rather than a conversation. What actually
                        changed is shown by the module chips below, and anything
                        that failed is surfaced explicitly. The full context a
                        reply was built from is still available at
                        GET /jocasta/context for when it's genuinely needed. */}
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

        {(attached || uploading || attachError) && (
          <div className={"attached" + (attachError ? " bad" : "")}>
            {uploading && <><div className="spinner" /><div>Reading the file…</div></>}

            {attachError && (
              <>
                <Icon.x s={16} />
                <div style={{ flex: 1 }}>{attachError}</div>
                <button className="iconbtn sm" aria-label="Dismiss"
                  onClick={() => setAttachError("")}><Icon.x s={13} /></button>
              </>
            )}

            {attached && !uploading && (
              <>
                <Icon.file s={17} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="attached-name">{attached.filename}</div>
                  <div className="mini">
                    {attached.pages} page(s)
                    {attached.found.classes > 0 && ` · ${attached.found.classes} class slot(s)`}
                    {attached.found.modules > 0 &&
                      ` · ${attached.found.modules} module(s), ${attached.found.concepts} concept(s)`}
                    {!attached.found.classes && !attached.found.modules &&
                      " · no timetable or syllabus structure recognised"}
                  </div>
                </div>
                <button className="iconbtn sm" aria-label="Remove attachment"
                  onClick={() => setAttached(null)}><Icon.x s={13} /></button>
              </>
            )}
          </div>
        )}

        {attached && !busy && (
          <div className="chips" style={{ marginTop: 10 }}>
            {attached.found.classes > 0 && (
              <button className="chip" onClick={() => send("add this timetable to my planner")}>
                Add these classes
              </button>
            )}
            {attached.found.modules > 0 && (
              <button className="chip" onClick={() => send("build the course modules from this syllabus")}>
                Build course modules
              </button>
            )}
            <button className="chip" onClick={() => send("what does this say?")}>
              What&rsquo;s in it?
            </button>
          </div>
        )}

        <div className="capture" style={{ marginTop: 12 }}>
          <input ref={fileRef} type="file" hidden
            accept=".pdf,.txt,.md,.csv,application/pdf,text/plain"
            onChange={(e) => pickFile(e.target.files?.[0])} />
          <button className="iconbtn" aria-label="Attach a file" title="Attach a PDF or text file"
            onClick={() => fileRef.current?.click()} disabled={uploading}>
            <Icon.clip s={17} />
          </button>
          <input placeholder={attached ? "What should I do with it?" : "Ask JOCasta…"}
            value={text} aria-label="Message JOCasta"
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
