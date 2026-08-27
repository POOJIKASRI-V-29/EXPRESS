"use client";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Shell } from "@/components/shell";
import { Atmosphere } from "@/components/atmosphere";
import { Icon, IconName } from "@/components/icons";
import { ErrorState } from "@/components/states";
import {
  JocastaThinking, SenseCore, SignalRow, Thread, ThreadRow,
  deriveState, pressing,
} from "@/components/sense";
import { useRequireAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import { fmtDue, minutes } from "@/lib/format";
import type {
  GoalsPayload, HomePayload, JocastaResult, Notification, PlannerPayload,
} from "@/lib/types";

const MODULE_HREF: Record<string, string> = {
  tasks: "/tasks", planner: "/planner", college: "/college", learning: "/learning",
  projects: "/projects", career: "/career", goals: "/goals", personal: "/personal",
  finance: "/finance", memory: "/memory", progress: "/progress",
};

/** Stages JOCasta actually goes through, shown while the request is in flight. */
const STAGES = [
  "Reading today's schedule…",
  "Checking deadlines and overdue work…",
  "Measuring what time is actually free…",
  "Building a plan…",
];

export default function HomePage() {
  const { user, ready } = useRequireAuth();
  const router = useRouter();

  const [home, setHome] = useState<HomePayload | null>(null);
  const [signals, setSignals] = useState<Notification[]>([]);
  const [today, setToday] = useState<PlannerPayload["today"] | null>(null);
  const [goals, setGoals] = useState<GoalsPayload["goals"]>([]);
  const [state, setState] = useState<"loading" | "error" | "ready">("loading");
  const [error, setError] = useState("");

  const [plan, setPlan] = useState<JocastaResult | null>(null);
  const [planning, setPlanning] = useState(false);
  const [stage, setStage] = useState(0);

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setState("loading");
    try {
      const [h, s, p, g] = await Promise.all([
        api.home(), api.spiderSense(), api.planner(1), api.goals(),
      ]);
      setHome(h); setSignals(s); setToday(p.today); setGoals(g.goals);
      setState("ready");
    } catch (e: any) { setError(e.message); setState("error"); }
  }, []);

  useEffect(() => { if (ready && user) load(); }, [ready, user, load]);

  // Walk the stage labels while the plan is being built.
  useEffect(() => {
    if (!planning) { setStage(0); return; }
    const t = setInterval(() => setStage((i) => Math.min(i + 1, STAGES.length - 1)), 900);
    return () => clearInterval(t);
  }, [planning]);

  async function fixMyDay() {
    if (planning) return;
    setPlanning(true); setPlan(null);
    try { setPlan(await api.jocasta("help me plan my day")); }
    catch (e: any) { setPlan({ reply: "Lost the thread — " + e.message } as JocastaResult); }
    finally { setPlanning(false); }
  }

  async function applyPlan(token: string) {
    setPlanning(true);
    try {
      const res = await api.jocastaConfirm(token);
      setPlan({ ...res, pending: null, confirm_token: null });
      await load(true);
    } catch (e: any) {
      setPlan((p) => (p ? { ...p, reply: "Lost the thread — " + e.message, pending: null } : p));
    } finally { setPlanning(false); }
  }

  if (!ready || !user) return null;

  const items = today?.items ?? [];
  const doneToday = items.filter((i) => i.status === "done").length;
  const senseState = deriveState(signals, items.length);
  // The next thing still to happen today, by wall-clock time. Drives the one
  // focal node on the timeline.
  const clock = new Date().toTimeString().slice(0, 5);
  const nextUp = items.find((i) => i.status !== "done" && i.time >= clock)
    ?? items.find((i) => i.status !== "done");
  const urgent = pressing(signals);
  const banner = home?.banner;
  const critical = signals.find((s) => s.severity >= 5);
  const goalThreads = goals.filter((g) => g.status === "active" && g.links.length > 0).slice(0, 2);

  const goTo = (s: Notification) =>
    router.push(s.action_href || MODULE_HREF[s.module] || "/planner");

  return (
    <>
      <Atmosphere red={!!critical} />
      <Shell red={!!critical}>
        {state === "loading" && (
          <div className="center-state"><JocastaThinking label="Connecting threads…" /></div>
        )}
        {state === "error" && <ErrorState message={error} onRetry={() => load()} />}

        {state === "ready" && home && (
          <>
            <div className="eyebrow">
              {home.greeting}, {home.user_name}{home.semester ? ` · ${home.semester}` : ""}
            </div>

            {/* ── The core: one read on the state of the day ───────────── */}
            <SenseCore
              state={senseState}
              count={urgent.length}
              done={doneToday}
              total={items.length}
            />

            {/* ── What matters now ─────────────────────────────────────── */}
            <section className="section">
              <div className="section-h">
                <span className="section-t">What matters now</span>
                {signals.length > urgent.length && (
                  <span className="section-n">{signals.length - urgent.length} quieter signal(s)</span>
                )}
              </div>
              {urgent.length ? (
                urgent.slice(0, 4).map((s) => (
                  <SignalRow key={s.id} signal={s} onAct={goTo}
                    onDismiss={(x) => api.ackSpider(x.id).then(() => load(true))} />
                ))
              ) : signals.length ? (
                <div className="empty">Nothing urgent. {signals.length} quieter signal(s) waiting.</div>
              ) : (
                <div className="empty">No active signals. The web is quiet.</div>
              )}
            </section>

            {/* ── Fix My Day ───────────────────────────────────────────── */}
            <section className="section">
              <div className="invite">
                <svg className="invite-web" viewBox="0 0 200 200" aria-hidden="true">
                  {Array.from({ length: 9 }, (_, i) => {
                    const a = (i / 9) * Math.PI * 2;
                    return <line key={i} x1="100" y1="100"
                      x2={100 + Math.cos(a) * 96} y2={100 + Math.sin(a) * 96} />;
                  })}
                  {[34, 58, 82].map((r) => <circle key={r} cx="100" cy="100" r={r} />)}
                </svg>

                {!planning && !plan && (
                  <>
                    <div className="invite-t"><Icon.spider s={17} /> Fix My Day</div>
                    <div className="invite-s">
                      JOCasta reads your real deadlines and the time you actually have free,
                      then proposes a way through today. Nothing changes until you say so.
                    </div>
                    <button className="btn primary" style={{ marginTop: 16 }} onClick={fixMyDay}>
                      Let&rsquo;s go
                    </button>
                  </>
                )}

                {planning && <JocastaThinking stage={STAGES[stage]} />}

                {!planning && plan && (
                  <>
                    <div className="invite-t"><Icon.joc s={17} /> JOCasta&rsquo;s read on today</div>
                    <div className="plan-lines" style={{ marginTop: 10 }}>{plan.reply}</div>

                    {plan.pending && plan.confirm_token && (
                      <>
                        <ul style={{ listStyle: "none", padding: 0, margin: "16px 0 0",
                                     display: "flex", flexDirection: "column", gap: 8 }}>
                          {plan.pending.actions.map((a, i) => (
                            <li key={i} style={{ display: "flex", gap: 9, alignItems: "flex-start",
                                                 fontSize: 13, color: "var(--text-2)", lineHeight: 1.45 }}>
                              <span className={"signal-sev" + (a.risk === "sensitive" ? "" : "")}
                                style={a.risk === "sensitive"
                                  ? { color: "var(--critical)", borderColor: "var(--red-line)" } : undefined}>
                                {a.risk}
                              </span>
                              <span>{a.summary}</span>
                            </li>
                          ))}
                        </ul>
                        <div style={{ display: "flex", gap: 10, marginTop: 18, flexWrap: "wrap" }}>
                          <button className="btn sm amber" onClick={() => applyPlan(plan.confirm_token!)}>
                            <Icon.check s={14} /> Apply plan
                          </button>
                          <button className="btn sm" onClick={() => setPlan(null)}>Not now</button>
                        </div>
                      </>
                    )}

                    {!plan.pending && (
                      <div style={{ display: "flex", gap: 10, marginTop: 16, flexWrap: "wrap" }}>
                        <button className="btn sm" onClick={() => router.push("/planner")}>Open Planner</button>
                        <button className="btn sm" onClick={() => setPlan(null)}>Dismiss</button>
                      </div>
                    )}
                  </>
                )}
              </div>
            </section>

            {/* ── Today's web ──────────────────────────────────────────── */}
            <section className="section">
              <div className="section-h">
                <span className="section-t">Today&rsquo;s web</span>
                <span className="section-n">
                  {items.length ? `${doneToday}/${items.length} done · ${minutes(today?.booked_minutes || 0)} booked` : ""}
                </span>
              </div>
              {items.length ? (
                <Thread>
                  {items.map((it) => {
                    const I = Icon[(it.icon as IconName)] || Icon.tasks;
                    const tone = it.status === "done" ? "done"
                      : it.id === nextUp?.id ? "now"
                      : "idle";
                    return (
                      <ThreadRow
                        key={`${it.kind}-${it.id}`}
                        when={it.time}
                        tone={tone}
                        title={it.title}
                        meta={<><I s={11} /> {it.meta}{it.end ? ` · until ${it.end}` : ""}</>}
                      />
                    );
                  })}
                </Thread>
              ) : (
                <div className="empty">Nothing scheduled. The web is quiet today.</div>
              )}
            </section>

            {/* ── Important threads: relationships that already exist ──── */}
            {goalThreads.length > 0 && (
              <section className="section">
                <div className="section-h">
                  <span className="section-t">Important threads</span>
                  <button className="link" onClick={() => router.push("/goals")}>All goals</button>
                </div>
                {goalThreads.map((g) => (
                  <div key={g.id} style={{ marginBottom: 20 }}>
                    <Thread>
                      <ThreadRow
                        lit
                        tone={g.progress >= 70 ? "done" : "now"}
                        title={g.title}
                        meta={`${g.progress}% · from ${g.progress_source}`}
                        onClick={() => router.push("/goals")}
                      />
                      {g.links.map((l) => (
                        <ThreadRow
                          key={l.id}
                          tone={l.progress >= 100 ? "done" : "idle"}
                          title={l.label}
                          meta={`${l.ref_type} · ${l.progress}%`}
                          onClick={() => router.push(MODULE_HREF[l.ref_type + "s"] || "/goals")}
                        />
                      ))}
                    </Thread>
                  </div>
                ))}
              </section>
            )}

            {/* ── Quiet progress strip ─────────────────────────────────── */}
            <section className="section">
              <div className="section-h"><span className="section-t">Where you stand</span></div>
              <div className="stats">
                <button className="stat" style={{ textAlign: "left" }} onClick={() => router.push("/college")}>
                  <div className="k">Attendance</div>
                  <div className="v num"
                    style={home.course_count > 0 && home.attendance < 75
                      ? { color: "var(--critical)" } : undefined}>
                    {home.course_count > 0 ? `${home.attendance}%` : "—"}
                  </div>
                  <div className="n">
                    {home.course_count > 0 ? "across your courses" : "no courses yet"}
                  </div>
                </button>
                <button className="stat" style={{ textAlign: "left" }} onClick={() => router.push("/planner")}>
                  <div className="k">Today</div>
                  <div className="v num">{doneToday}/{items.length}</div>
                  <div className="n">scheduled items done</div>
                </button>
                <button className="stat" style={{ textAlign: "left" }} onClick={() => router.push("/goals")}>
                  <div className="k">Active goals</div>
                  <div className="v num">{goals.filter((g) => g.status === "active").length}</div>
                  <div className="n">tracking real work</div>
                </button>
              </div>
            </section>

            {banner && !urgent.some((s) => s.id === banner.id) && (
              <section className="section">
                <div className="ss-banner">
                  <div className="lbl"><Icon.spider s={14} /> SPIDER SENSE</div>
                  <div className="msg">{banner.title}</div>
                  <button className="btn red sm"
                    onClick={() => {
                      const sig = signals.find((x) => x.id === banner.id);
                      router.push(sig?.action_href || "/planner");
                    }}>Resolve it</button>
                </div>
              </section>
            )}
          </>
        )}
      </Shell>
    </>
  );
}
