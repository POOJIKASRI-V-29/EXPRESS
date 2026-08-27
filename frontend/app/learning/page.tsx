"use client";
import { useState } from "react";
import { Icon } from "@/components/icons";
import { Empty } from "@/components/states";
import { ModulePage, Modal, Field, Bar, Stat, AddButton, IconAction, useModule, useConfirm } from "@/components/ui";
import { api } from "@/lib/api";
import { fromLocalInput, toLocalInput, minutes, fmtShort, titleCase } from "@/lib/format";
import type { LearningPayload, Topic } from "@/lib/types";

const STATE_PILL: Record<string, string> = {
  strong: "blue", practicing: "", learning: "", needs_revision: "red", not_started: "",
};
type Dialog = null | "topic" | "skill" | "log" | "schedule";

export default function LearningPage() {
  const { user, ready, data, state, error, reload, act } = useModule<LearningPayload>(() => api.learning());
  const [area, setArea] = useState("All");
  const [dialog, setDialog] = useState<Dialog>(null);
  const [target, setTarget] = useState<Topic | null>(null);
  const [f, setF] = useState<any>({});
  const [busy, setBusy] = useState(false);
  const confirm = useConfirm();

  const open = (d: Dialog, init: any = {}, t: Topic | null = null) => { setF(init); setTarget(t); setDialog(d); };

  async function submit(fn: () => Promise<any>) {
    setBusy(true); await act(fn); setBusy(false); setDialog(null);
  }

  if (!ready || !user) return null;
  const l = data;
  const topics = (l?.topics || []).filter((t) => area === "All" || t.area === area);

  return (
    <ModulePage
      eyebrow="LEARNING HUB"
      title="Learning"
      sub="Topics you're building, time actually logged against them, and the skills that come out the other side."
      state={state} error={error} onRetry={reload}
      actions={<>
        <AddButton label="Topic" onClick={() => open("topic", { name: "", area: "DSA", state: "learning", progress: 0 })} />
        <AddButton label="Skill" onClick={() => open("skill", { name: "", pct: 10 })} />
      </>}
    >
      {l && (
        <div className="stack">
          <div className="stats">
            <Stat k="This week" v={minutes(l.week_minutes)} n={`${l.session_count} sessions all time`} />
            <Stat k="Total logged" v={minutes(l.total_minutes)} />
            <Stat k="Topics" v={l.topics.length} n={`${l.topics.filter((t) => t.state === "strong").length} strong`} />
            <Stat k="Needs revision" v={l.topics.filter((t) => t.state === "needs_revision").length}
              tone={l.topics.some((t) => t.state === "needs_revision") ? "red" : undefined} />
          </div>

          <div className="g-2">
            <div className="g-col">
              <div className="card">
                <div className="card-h">
                  <span className="card-t">Topics · {topics.length}</span>
                  <div className="chips">
                    {["All", ...(l.areas || [])].map((a) => (
                      <button key={a} className={"chip" + (a === area ? " on" : "")} onClick={() => setArea(a)}>{a}</button>
                    ))}
                  </div>
                </div>
                {topics.length ? topics.map((t) => (
                  <div className="row" key={t.id}>
                    <div className="ico-box" style={t.state === "needs_revision" ? { color: "var(--red)", borderColor: "var(--red-line)" } : undefined}>
                      <Icon.learning s={18} />
                    </div>
                    <div className="grow">
                      <div className="t">{t.name}</div>
                      <div className="s">
                        {t.area}{t.course ? ` · ${t.course}` : ""} · {minutes(t.minutes)} logged
                        {t.last_reviewed_at ? ` · last ${fmtShort(t.last_reviewed_at)}` : " · never reviewed"}
                        {t.scheduled ? " · scheduled" : ""}
                      </div>
                      <div style={{ marginTop: 8, maxWidth: 300 }}>
                        <Bar pct={t.progress} tone={t.state === "needs_revision" ? "red" : "blue"} />
                      </div>
                    </div>
                    <select className="pill" style={{ background: "transparent" }} value={t.state}
                      onChange={(e) => act(() => api.updateTopic(t.id, { state: e.target.value }))}>
                      {l.states.map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}
                    </select>
                    <div className="row-acts">
                      <button className="btn sm primary" onClick={() => open("log", { minutes: 30, note: "" }, t)}>Log</button>
                      <button className="btn sm" onClick={() => open("schedule", { due_at: toLocalInput(null, 21, 0), minutes: 45 }, t)}>Schedule</button>
                      <IconAction icon={Icon.trash} danger title={`Delete ${t.name}`}
                        onClick={() => confirm(`Delete ${t.name} and its sessions?`, () => act(() => api.deleteTopic(t.id)))} />
                    </div>
                  </div>
                )) : <Empty>{area === "All" ? "No topics yet. Add one to start logging study time." : `Nothing under ${area}.`}</Empty>}
              </div>
            </div>

            <div className="g-col">
              <div className="card">
                <div className="card-h"><span className="card-t">Skills</span><span className="pill">{l.skills.length}</span></div>
                {l.skills.length ? l.skills.map((s) => (
                  <div className="row" key={s.id}>
                    <div className="ico-box"><Icon.dumb s={16} /></div>
                    <div className="grow">
                      <div className="t" style={{ fontSize: 13 }}>{s.name}</div>
                      <div className="s">Level {s.level}</div>
                      <div style={{ marginTop: 7 }}><Bar pct={s.pct} /></div>
                    </div>
                    <div className="pill">{s.pct}%</div>
                    <IconAction icon={Icon.trash} danger title={`Delete ${s.name}`}
                      onClick={() => confirm(`Delete ${s.name}?`, () => act(() => api.deleteSkill(s.id)))} />
                  </div>
                )) : <Empty>No skills tracked.</Empty>}
              </div>

              <div className="card">
                <div className="card-h"><span className="card-t">Recent sessions</span></div>
                {l.recent_sessions.length ? l.recent_sessions.map((s) => (
                  <div className="row" key={s.id}>
                    <div className="ico-box"><Icon.clock s={16} /></div>
                    <div className="grow">
                      <div className="t" style={{ fontSize: 13 }}>{s.topic}</div>
                      <div className="s">{s.note || "No note"} · {fmtShort(s.started_at)}</div>
                    </div>
                    <div className="pill">{minutes(s.minutes)}</div>
                  </div>
                )) : <Empty>No study logged yet.</Empty>}
              </div>
            </div>
          </div>
        </div>
      )}

      {dialog === "topic" && (
        <Modal title="Add topic" onClose={() => setDialog(null)} busy={busy}
          onSubmit={() => submit(() => api.createTopic({ ...f, progress: Number(f.progress) || 0 }))}>
          <Field label="Name"><input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required autoFocus /></Field>
          <div className="field-row">
            <Field label="Area">
              <select value={f.area} onChange={(e) => setF({ ...f, area: e.target.value })}>
                {["DSA", "DataScience", "AI/ML", "Python", "Course"].map((a) => <option key={a}>{a}</option>)}
              </select>
            </Field>
            <Field label="State">
              <select value={f.state} onChange={(e) => setF({ ...f, state: e.target.value })}>
                {(l?.states || []).map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}
              </select>
            </Field>
          </div>
          <Field label="Starting progress %"><input type="number" min={0} max={100} value={f.progress} onChange={(e) => setF({ ...f, progress: e.target.value })} /></Field>
        </Modal>
      )}

      {dialog === "skill" && (
        <Modal title="Add skill" onClose={() => setDialog(null)} busy={busy}
          onSubmit={() => submit(() => api.createSkill({ name: f.name, pct: Number(f.pct) || 0, level: Math.max(1, Math.round((Number(f.pct) || 0) / 20)) }))}>
          <Field label="Name"><input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required autoFocus /></Field>
          <Field label="Confidence %" hint="Level is derived from this."><input type="number" min={0} max={100} value={f.pct} onChange={(e) => setF({ ...f, pct: e.target.value })} /></Field>
        </Modal>
      )}

      {dialog === "log" && target && (
        <Modal title="Log study time" sub={`${target.name} — progress and recency both move.`}
          onClose={() => setDialog(null)} busy={busy} submitLabel="Log"
          onSubmit={() => submit(() => api.logSession(target.id, { minutes: Number(f.minutes) || 25, note: f.note }))}>
          <Field label="Minutes"><input type="number" min={1} value={f.minutes} onChange={(e) => setF({ ...f, minutes: e.target.value })} autoFocus /></Field>
          <Field label="Note"><input value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} placeholder="What did you cover?" /></Field>
        </Modal>
      )}

      {dialog === "schedule" && target && (
        <Modal title="Schedule a study block" sub={`${target.name} — this lands on your Planner.`}
          onClose={() => setDialog(null)} busy={busy} submitLabel="Schedule"
          onSubmit={() => submit(() => api.scheduleStudy(target.id, { due_at: fromLocalInput(f.due_at), minutes: Number(f.minutes) || 45 }))}>
          <Field label="When"><input type="datetime-local" value={f.due_at} onChange={(e) => setF({ ...f, due_at: e.target.value })} autoFocus /></Field>
          <Field label="Minutes"><input type="number" min={5} value={f.minutes} onChange={(e) => setF({ ...f, minutes: e.target.value })} /></Field>
        </Modal>
      )}
    </ModulePage>
  );
}
