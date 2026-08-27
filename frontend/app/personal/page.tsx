"use client";
import { useState } from "react";
import { Icon, IconName } from "@/components/icons";
import { Empty } from "@/components/states";
import { ModulePage, Modal, Field, Stat, AddButton, IconAction, useModule, useConfirm } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtShort } from "@/lib/format";
import type { PersonalPayload, Note } from "@/lib/types";

const DAY_INITIALS = ["M", "T", "W", "T", "F", "S", "S"];
type Dialog = null | "note" | "habit" | "edit";

export default function PersonalPage() {
  const { user, ready, data, state, error, reload, act } = useModule<PersonalPayload>(() => api.personal());
  const [q, setQ] = useState("");
  const [tag, setTag] = useState("All");
  const [dialog, setDialog] = useState<Dialog>(null);
  const [editing, setEditing] = useState<Note | null>(null);
  const [f, setF] = useState<any>({});
  const [busy, setBusy] = useState(false);
  const confirm = useConfirm();

  const open = (d: Dialog, init: any = {}) => { setF(init); setDialog(d); };
  async function submit(fn: () => Promise<any>) { setBusy(true); await act(fn); setBusy(false); setDialog(null); setEditing(null); }

  if (!ready || !user) return null;
  const p = data;
  const notes = (p?.notes || []).filter((n) => {
    const matchesTag = tag === "All" || (n.tags || "").split(",").map((t) => t.trim()).includes(tag);
    const needle = q.trim().toLowerCase();
    const matchesQ = !needle ||
      n.title.toLowerCase().includes(needle) || n.body.toLowerCase().includes(needle);
    return matchesTag && matchesQ;
  });

  return (
    <ModulePage
      eyebrow="PERSONAL"
      title="Personal"
      sub="Notes that can anchor to a course or project, and habits whose streaks are counted from what you actually logged."
      state={state} error={error} onRetry={reload}
      actions={<>
        <AddButton label="Note" onClick={() => open("note", { title: "", body: "", tags: "", pinned: false })} />
        <AddButton label="Habit" onClick={() => open("habit", { title: "", cadence: "daily", target_per_week: 7, icon: "check" })} />
      </>}
    >
      {p && (
        <div className="g-2">
          <div className="g-col">
            <div className="card">
              <div className="card-h">
                <span className="card-t">Notes · {notes.length}</span>
                <span className="mini">{p.notes.filter((n) => n.pinned).length} pinned</span>
              </div>

              <div className="capture" style={{ marginBottom: 14 }}>
                <Icon.search s={16} />
                <input placeholder="Trace a thread…" value={q} onChange={(e) => setQ(e.target.value)} />
                {q && <button className="iconbtn sm" aria-label="Clear" onClick={() => setQ("")}><Icon.x s={13} /></button>}
              </div>

              {p.tags.length > 0 && (
                <div className="chips" style={{ marginBottom: 14 }}>
                  {["All", ...p.tags].map((t) => (
                    <button key={t} className={"chip" + (t === tag ? " on" : "")} onClick={() => setTag(t)}>{t}</button>
                  ))}
                </div>
              )}

              {notes.length ? notes.map((n) => (
                <div className="row" key={n.id} style={{ alignItems: "flex-start" }}>
                  <button className="ico-box" title={n.pinned ? "Unpin" : "Pin"}
                    style={n.pinned ? { color: "var(--blue-soft)", borderColor: "rgba(124,156,242,.4)" } : undefined}
                    onClick={() => act(() => api.updateNote(n.id, { pinned: !n.pinned }))}>
                    <Icon.pin s={16} />
                  </button>
                  <div className="grow">
                    <div className="t">{n.title || "Untitled"}</div>
                    <div className="note-body" style={{ marginTop: 5 }}>{n.body}</div>
                    <div style={{ marginTop: 9 }}>
                      {(n.tags || "").split(",").filter(Boolean).map((t) => <span className="tag" key={t}>{t.trim()}</span>)}
                      {n.ref_label && <span className="tag">{n.ref_type}: {n.ref_label}</span>}
                      <span className="tag">{fmtShort(n.updated_at)}</span>
                    </div>
                  </div>
                  <div className="row-acts">
                    <IconAction icon={Icon.edit} title="Edit note"
                      onClick={() => { setEditing(n); setF({ title: n.title, body: n.body, tags: n.tags }); setDialog("edit"); }} />
                    <IconAction icon={Icon.trash} danger title="Delete note"
                      onClick={() => confirm("Delete this note?", () => act(() => api.deleteNote(n.id)))} />
                  </div>
                </div>
              )) : <Empty>{q || tag !== "All" ? "No notes match that." : "No notes yet."}</Empty>}
            </div>
          </div>

          <div className="g-col">
            <div className="stats">
              <Stat k="Habits today" v={`${p.habits_done_today}/${p.habits.length}`} />
              <Stat k="Best streak" v={Math.max(0, ...p.habits.map((h) => h.streak))} n="days" />
            </div>

            <div className="card">
              <div className="card-h"><span className="card-t">Habits</span><span className="pill">{p.habits.length}</span></div>
              {p.habits.length ? p.habits.map((h) => {
                const I = (Icon[h.icon as IconName] || Icon.check);
                return (
                  <div className="row" key={h.id}>
                    <button className="ico-box" title={h.done_today ? "Undo today" : "Mark done today"}
                      style={h.done_today ? { color: "var(--green)", borderColor: "rgba(75,192,140,.45)" } : undefined}
                      onClick={() => act(() => api.toggleHabit(h.id))}>
                      {h.done_today ? <Icon.check s={17} /> : <I s={17} />}
                    </button>
                    <div className="grow">
                      <div className="t" style={{ fontSize: 13 }}>{h.title}</div>
                      <div className="s">{h.done_this_week}/{h.target_per_week} this week · {h.cadence}</div>
                      <div className="dots" style={{ marginTop: 8 }} title="Last 7 days">
                        {h.week.map((on, i) => <i key={i} className={on ? "on" : ""} />)}
                      </div>
                    </div>
                    <div className={"pill " + (h.streak > 0 ? "blue" : "")}>{h.streak}d</div>
                    <IconAction icon={Icon.trash} danger title={`Delete ${h.title}`}
                      onClick={() => confirm(`Delete "${h.title}" and its history?`, () => act(() => api.deleteHabit(h.id)))} />
                  </div>
                );
              }) : <Empty>No habits tracked yet.</Empty>}
              {p.habits.length > 0 && (
                <div className="mini" style={{ marginTop: 12, display: "flex", gap: 6 }}>
                  {DAY_INITIALS.map((d, i) => <span key={i} style={{ width: 9, textAlign: "center" }}>{d}</span>)}
                  <span style={{ marginLeft: 6 }}>last 7 days, oldest first</span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {dialog === "note" && (
        <Modal title="Add note" onClose={() => setDialog(null)} busy={busy}
          onSubmit={() => submit(() => api.createNote(f))}>
          <Field label="Title"><input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} autoFocus placeholder="Optional" /></Field>
          <Field label="Body"><textarea value={f.body} onChange={(e) => setF({ ...f, body: e.target.value })} required /></Field>
          <Field label="Tags" hint="Comma separated"><input value={f.tags} onChange={(e) => setF({ ...f, tags: e.target.value })} placeholder="career, dsa" /></Field>
        </Modal>
      )}

      {dialog === "edit" && editing && (
        <Modal title="Edit note" onClose={() => { setDialog(null); setEditing(null); }} busy={busy}
          onSubmit={() => submit(() => api.updateNote(editing.id, f))}>
          <Field label="Title"><input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} autoFocus /></Field>
          <Field label="Body"><textarea value={f.body} onChange={(e) => setF({ ...f, body: e.target.value })} required /></Field>
          <Field label="Tags"><input value={f.tags} onChange={(e) => setF({ ...f, tags: e.target.value })} /></Field>
        </Modal>
      )}

      {dialog === "habit" && (
        <Modal title="Add habit" onClose={() => setDialog(null)} busy={busy}
          onSubmit={() => submit(() => api.createHabit({ ...f, target_per_week: Number(f.target_per_week) || 7 }))}>
          <Field label="Title"><input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} required autoFocus /></Field>
          <div className="field-row">
            <Field label="Cadence">
              <select value={f.cadence} onChange={(e) => setF({ ...f, cadence: e.target.value })}>
                {["daily", "weekdays", "weekly"].map((c) => <option key={c}>{c}</option>)}
              </select>
            </Field>
            <Field label="Target per week"><input type="number" min={1} max={7} value={f.target_per_week} onChange={(e) => setF({ ...f, target_per_week: e.target.value })} /></Field>
          </div>
          <Field label="Icon">
            <select value={f.icon} onChange={(e) => setF({ ...f, icon: e.target.value })}>
              {["check", "dumb", "learning", "note", "clock", "mail"].map((i) => <option key={i}>{i}</option>)}
            </select>
          </Field>
        </Modal>
      )}
    </ModulePage>
  );
}
