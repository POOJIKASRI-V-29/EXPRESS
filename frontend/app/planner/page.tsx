"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Icon, IconName } from "@/components/icons";
import { Empty } from "@/components/states";
import { ModulePage, Modal, Field, Stat, useModule, useConfirm } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtShort, fromLocalInput, minutes, toLocalInput } from "@/lib/format";
import type { PlannerCategory, PlannerItem, PlannerPayload } from "@/lib/types";

const CAT_ICON: Record<string, IconName> = {
  Task: "tasks", Study: "learning", Project: "projects",
  Personal: "note", Class: "college",
};

export default function PlannerPage() {
  const { user, ready, data, state, error, reload, act } =
    useModule<PlannerPayload>(() => api.planner(7));
  const router = useRouter();
  const confirm = useConfirm();

  const [sel, setSel] = useState(0);
  const [dialog, setDialog] = useState<null | "add" | "edit">(null);
  const [editing, setEditing] = useState<PlannerItem | null>(null);
  const [f, setF] = useState<any>({});
  const [busy, setBusy] = useState(false);

  if (!ready || !user) return null;
  const p = data;
  const day = p?.days.find((d) => d.offset === sel) ?? p?.today;
  const cats = p?.categories ?? ["Task", "Study", "Project", "Goal", "Personal"];
  // Exams and calendar entries are fixed commitments: correctable, but they
  // have no category, duration or note of their own.
  const isExam = dialog === "edit" && editing?.kind === "exam";
  const isEvent = dialog === "edit" && editing?.kind === "event";
  const isFixed = isExam || isEvent;

  function openAdd() {
    setF({ title: "", category: "Task", due_at: toLocalInput(null, 9, sel),
           est_minutes: 30, meta: "" });
    setDialog("add");
  }

  function openEdit(it: PlannerItem) {
    setEditing(it);
    setF({
      title: it.title,
      category: it.category === "Class" ? "Task" : it.category,
      // Tasks carry due_at; exams and events carry their own date.
      due_at: toLocalInput(it.due_at || it.date || null),
      est_minutes: it.est_minutes ?? 30,
      meta: it.meta || "",
      room: it.room || "",
      exam_type: it.exam_type || "cat",
      event_type: it.event_type || "holiday",
    });
    setDialog("edit");
  }

  /** Planner shows three editable kinds; each has its own endpoint. Sending an
   *  exam id to the task endpoint would 404 at best and hit an unrelated row at
   *  worst, so the kind decides the call. */
  function saveEdit(it: PlannerItem) {
    const when = f.due_at ? fromLocalInput(f.due_at) : null;
    if (it.kind === "exam") {
      return api.updateExam(it.id, {
        title: f.title, room: f.room, type: f.exam_type,
        ...(when ? { date: when } : {}),
      });
    }
    if (it.kind === "event") {
      return api.updateEvent(it.id, {
        title: f.title, type: f.event_type,
        ...(when ? { date: when } : {}),
      });
    }
    return api.updateTask(it.id, {
      title: f.title, category: f.category,
      est_minutes: Number(f.est_minutes) || 30,
      meta: f.meta, due_at: when,
    });
  }

  function deleteItem(it: PlannerItem) {
    if (it.kind === "exam") return api.deleteExam(it.id);
    if (it.kind === "event") return api.deleteEvent(it.id);
    return api.deleteTask(it.id);
  }

  async function submit(fn: () => Promise<any>) {
    setBusy(true); await act(fn); setBusy(false); setDialog(null); setEditing(null);
  }

  return (
    <ModulePage
      eyebrow={p ? `LOCAL TIME ${p.now}` : "PLANNER"}
      title="Planner"
      sub="Everything with a time on it — classes, coursework, study, project work and personal things."
      state={state} error={error} onRetry={reload}
      red={!!p?.conflicts.length}
      actions={<button className="btn primary" onClick={openAdd}><Icon.plus s={14} /> Add</button>}
    >
      {p && (
        <div className="stack">
          {p.conflicts.length > 0 && (
            <div className="ss-banner">
              <div className="lbl"><Icon.spider s={14} /> SPIDER SENSE</div>
              <div className="msg">{p.conflicts[0].title}</div>
              {p.conflicts.length > 1 && (
                <div className="mini">+{p.conflicts.length - 1} more clash(es) today</div>
              )}
            </div>
          )}

          {/* ── Date selector ─────────────────────────────────────────── */}
          <div className="tabs" style={{ overflowX: "auto", maxWidth: "100%" }}>
            {p.days.map((d) => (
              <button key={d.offset} className={"tab" + (d.offset === sel ? " on" : "")}
                onClick={() => setSel(d.offset)}>
                {d.is_today ? "Today" : `${d.day_label} ${fmtShort(d.date)}`}
                {d.open_count > 0 && <span style={{ opacity: .6 }}> · {d.open_count}</span>}
              </button>
            ))}
          </div>

          <div className="g-2">
            <div className="g-col">
              <div className="card">
                <div className="card-h">
                  <span className="card-t">
                    {day?.is_today ? "Today" : `${day?.day_label}, ${fmtShort(day?.date || "")}`}
                    {day?.items.length ? ` · ${day.items.length}` : ""}
                  </span>
                  {!!day?.booked_minutes && (
                    <span className="mini">{minutes(day.booked_minutes)} booked</span>
                  )}
                </div>

                {day?.items.length ? (
                  <div className="day">
                    {day.items.map((it) => {
                      const I = Icon[(it.icon as IconName)] || Icon[CAT_ICON[it.category]] || Icon.tasks;
                      const done = it.status === "done";
                      return (
                        <div className={"day-row cat" + (done ? " done" : "")}
                          data-cat={it.category} key={`${it.kind}-${it.id}`}>
                          <div className="day-when num">{it.time}</div>
                          <div className="day-rail"><span className="day-node" /></div>

                          <div className="day-body">
                            <div className="day-title">{it.title}</div>
                            <div className="day-sub">
                              <span className="cat-chip cat" data-cat={it.category}>
                                <I s={10} /> {it.category}
                              </span>
                              {it.meta && <span>{it.meta}</span>}
                              {it.end && <span>until {it.end}</span>}
                              {!!it.est_minutes && <span>{minutes(it.est_minutes)}</span>}
                            </div>
                          </div>

                          <div className="day-acts">
                            {/* Completion semantics differ by kind: a task is
                                finished, a class is attended, and a fixed event
                                is neither. */}
                            {it.kind === "task" && !done && (
                              <button className="iconbtn sm" title="Mark done"
                                aria-label={`Mark ${it.title} done`}
                                onClick={() => act(() => api.completeTask(it.id))}>
                                <Icon.check s={14} />
                              </button>
                            )}
                            {it.kind === "class" && it.course_id && (
                              <>
                                <button className="btn sm" title="Attended this class"
                                  onClick={() => act(() => api.markAttendance(it.course_id!, true))}>
                                  Attended
                                </button>
                                <button className="btn sm ghost-red" title="Missed this class"
                                  onClick={() => act(() => api.markAttendance(it.course_id!, false))}>
                                  Missed
                                </button>
                              </>
                            )}
                            {it.editable && (
                              <>
                                <button className="iconbtn sm" title="Edit"
                                  aria-label={`Edit ${it.title}`} onClick={() => openEdit(it)}>
                                  <Icon.edit s={14} />
                                </button>
                                <button className="iconbtn sm danger" title="Delete"
                                  aria-label={`Delete ${it.title}`}
                                  onClick={() => confirm(`Delete “${it.title}”?`,
                                    () => act(() => deleteItem(it)))}>
                                  <Icon.trash s={14} />
                                </button>
                              </>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <Empty>Nothing on this day. The web is quiet.</Empty>
                )}
              </div>
            </div>

            <div className="g-col">
              <div className="stats">
                <Stat k="On this day" v={day?.items.length ?? 0}
                  n={day?.open_count ? `${day.open_count} still open` : "all clear"} />
                <Stat k="Unscheduled" v={p.unscheduled.length} n="need a time" />
              </div>

              {/* Secondary by design — a holding area, not the main event. */}
              <div className="card unscheduled">
                <div className="card-h">
                  <span className="card-t">Unscheduled</span>
                  <span className="mini">give them a time</span>
                </div>
                {p.unscheduled.length ? p.unscheduled.map((u) => {
                  const I = Icon[CAT_ICON[u.category]] || Icon.tasks;
                  return (
                    <div className="row cat" data-cat={u.category} key={u.id}>
                      <div className="ico-box" style={{ color: "var(--c)" }}><I s={16} /></div>
                      <div className="grow">
                        <div className="t" style={{ fontSize: 13 }}>{u.title}</div>
                        <div className="s">
                          <span className="cat-chip cat" data-cat={u.category}>{u.category}</span>
                        </div>
                      </div>
                      <div className="row-acts">
                        <button className="btn sm" onClick={() => {
                          const d = new Date();
                          d.setDate(d.getDate() + sel);
                          d.setHours(9, 0, 0, 0);
                          act(() => api.schedule(u.id, d.toISOString()));
                        }}>
                          {sel === 0 ? "Today" : `Move to ${day?.day_label}`}
                        </button>
                        <button className="iconbtn sm danger" aria-label={`Delete ${u.title}`}
                          onClick={() => confirm(`Delete “${u.title}”?`,
                            () => act(() => api.deleteTask(u.id)))}>
                          <Icon.trash s={13} />
                        </button>
                      </div>
                    </div>
                  );
                }) : <Empty>Everything has a time.</Empty>}
              </div>

              <div className="card">
                <div className="card-h"><span className="card-t">Week</span></div>
                {p.days.map((d) => (
                  <button className="kv" key={d.offset} style={{ width: "100%" }}
                    onClick={() => setSel(d.offset)}>
                    <span className="k">{d.is_today ? "Today" : `${d.day_label} ${fmtShort(d.date)}`}</span>
                    <span className="v">{d.items.length} · {minutes(d.booked_minutes)}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {(dialog === "add" || dialog === "edit") && (
        <Modal
          title={dialog === "add" ? "Add to planner"
                 : editing?.kind === "exam" ? "Edit exam"
                 : editing?.kind === "event" ? "Edit calendar entry"
                 : "Edit item"}
          onClose={() => { setDialog(null); setEditing(null); }}
          busy={busy}
          onSubmit={() => submit(() =>
            dialog === "add"
              ? api.createTask({
                  title: f.title, category: f.category,
                  est_minutes: Number(f.est_minutes) || 30, meta: f.meta,
                  due_at: f.due_at ? fromLocalInput(f.due_at) : null,
                })
              : saveEdit(editing!))}>
          <Field label="Title">
            <input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })}
              required autoFocus placeholder="DSA practice" />
          </Field>
          {isExam ? (
            <div className="field-row">
              <Field label="Kind">
                <select value={f.exam_type}
                  onChange={(e) => setF({ ...f, exam_type: e.target.value })}>
                  <option value="cat">CAT</option>
                  <option value="fat">FAT</option>
                  <option value="internal">Internal</option>
                </select>
              </Field>
              <Field label="Room" hint="Optional">
                <input value={f.room}
                  onChange={(e) => setF({ ...f, room: e.target.value })} placeholder="AB-201" />
              </Field>
            </div>
          ) : isEvent ? (
            <Field label="Kind">
              <select value={f.event_type}
                onChange={(e) => setF({ ...f, event_type: e.target.value })}>
                <option value="holiday">Holiday</option>
                <option value="break">Break</option>
                <option value="exam_window">Exam window</option>
                <option value="event">Event</option>
              </select>
            </Field>
          ) : (
            <Field label="Category">
              <select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>
                {cats.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </Field>
          )}
          <div className="field-row">
            <Field label="When"
              hint={isFixed ? "Date and time" : "Clear it to leave this unscheduled"}>
              <input type="datetime-local" value={f.due_at}
                onChange={(e) => setF({ ...f, due_at: e.target.value })} />
            </Field>
            {!isFixed && (
              <Field label="Duration (min)">
                <input type="number" min={5} step={5} value={f.est_minutes}
                  onChange={(e) => setF({ ...f, est_minutes: e.target.value })} />
              </Field>
            )}
          </div>
          {!isFixed && (
            <Field label="Note" hint="Optional">
              <input value={f.meta} onChange={(e) => setF({ ...f, meta: e.target.value })} />
            </Field>
          )}
        </Modal>
      )}
    </ModulePage>
  );
}
