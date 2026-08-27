"use client";
import { useState } from "react";
import { Icon } from "@/components/icons";
import { Empty } from "@/components/states";
import { ModulePage, Modal, Field, Bar, Stat, AddButton, IconAction, useModule, useConfirm } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDue, fmtDate, fromLocalInput, toLocalInput, daysUntil } from "@/lib/format";
import type { CollegePayload } from "@/lib/types";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"];
type Dialog = null | "course" | "class" | "assignment" | "exam" | "event";

export default function CollegePage() {
  const { user, ready, data, state, error, reload, act } = useModule<CollegePayload>(() => api.college());
  const [dialog, setDialog] = useState<Dialog>(null);
  const [busy, setBusy] = useState(false);
  const confirm = useConfirm();

  // form state, reset each time a dialog opens
  const [f, setF] = useState<any>({});
  const open = (d: Dialog, init: any = {}) => { setF(init); setDialog(d); };
  const set = (k: string, v: any) => setF((p: any) => ({ ...p, [k]: v }));

  async function submit(fn: () => Promise<any>) {
    setBusy(true);
    await act(fn);
    setBusy(false);
    setDialog(null);
  }

  if (!ready || !user) return null;
  const c = data;

  return (
    <ModulePage
      eyebrow={c?.semester ? c.semester.label : "COLLEGE"}
      title="College"
      sub={c?.semester?.tagline || "Courses, timetable, attendance, coursework and the academic calendar."}
      state={state} error={error} onRetry={reload}
      actions={<>
        <AddButton label="Course" onClick={() => open("course", { name: "", code: "", faculty: "", room: "", attendance: 100 })} />
        <AddButton label="Assignment" onClick={() => open("assignment", { title: "", course_id: "", description: "", due_at: toLocalInput(null, 23, 1), est_minutes: 60, priority: "med" })} />
      </>}
    >
      {c && (
        <div className="stack">
          <div className="stats">
            <Stat k="Avg. Attendance" v={`${c.attendance}%`} n={`floor ${c.attendance_floor}%`}
              tone={c.attendance < c.attendance_floor ? "red" : undefined} />
            <Stat k="Courses" v={c.courses.length} n={`${c.courses.filter((x) => x.at_risk).length} at risk`} />
            <Stat k="Open coursework" v={c.assignments.filter((a) => a.status === "open").length}
              n={`${c.assignments.length} total`} />
            <Stat k="Classes today" v={c.today.length} n={c.today[0] ? `next ${c.today[0].start}` : "none scheduled"} />
          </div>

          <div className="g-2">
            <div className="g-col">
              {/* ---- Courses ---- */}
              <div className="card">
                <div className="card-h">
                  <span className="card-t">Courses · {c.courses.length}</span>
                  <span className="mini">Mark each class as attended or missed</span>
                </div>
                {c.courses.length ? c.courses.map((co) => (
                  <div className="row" key={co.id}>
                    <div className="ico-box" style={co.at_risk ? { color: "var(--red)", borderColor: "var(--red-line)" } : undefined}>
                      <Icon.college s={18} />
                    </div>
                    <div className="grow">
                      <div className="t">{co.name} {co.code && <span className="mini">· {co.code}</span>}</div>
                      <div className="s">{co.faculty || "No faculty set"}{co.room ? ` · ${co.room}` : ""}
                        {co.assignments_open ? ` · ${co.assignments_open} open` : ""}</div>
                      <div style={{ marginTop: 8, maxWidth: 260 }}>
                        <Bar pct={co.attendance} tone={co.at_risk ? "red" : "blue"} />
                      </div>
                    </div>
                    <div className={"pill " + (co.at_risk ? "red" : "")}>{co.attendance}%</div>
                    <div className="row-acts">
                      <button className="btn sm" onClick={() => act(() => api.markAttendance(co.id, true))}>Present</button>
                      <button className="btn sm ghost-red" onClick={() => act(() => api.markAttendance(co.id, false))}>Miss</button>
                      <IconAction icon={Icon.trash} danger title={`Delete ${co.name}`}
                        onClick={() => confirm(`Delete ${co.name} and everything attached to it?`, () => act(() => api.deleteCourse(co.id)))} />
                    </div>
                  </div>
                )) : <Empty>No courses yet. Add one to start tracking attendance and coursework.</Empty>}
              </div>

              {/* ---- Timetable ---- */}
              <div className="card">
                <div className="card-h">
                  <span className="card-t">Weekly Timetable</span>
                  <button className="link" onClick={() => open("class", { course_id: c.courses[0]?.id || "", day_of_week: 0, start_time: "09:00", end_time: "10:30", room: "" })}>
                    + Add slot
                  </button>
                </div>
                {c.timetable.length ? (
                  <div className="tt">
                    {DAYS.map((d, i) => {
                      const slots = c.timetable.filter((s) => s.day === i);
                      const isToday = slots.some((s) => s.today);
                      return (
                        <div className="col" key={d}>
                          <div className={"day" + (isToday ? " now" : "")}>{d}{isToday ? " · today" : ""}</div>
                          {slots.length ? slots.map((s) => (
                            <div className="slot" key={s.id}>
                              <div className="n">{s.course}</div>
                              <div className="t">{s.start}–{s.end}{s.room ? ` · ${s.room}` : ""}</div>
                              <button className="link" style={{ fontSize: 10, marginTop: 6 }}
                                onClick={() => confirm("Remove this slot?", () => act(() => api.deleteClass(s.id)))}>Remove</button>
                            </div>
                          )) : <div className="mini" style={{ padding: "6px 2px" }}>—</div>}
                        </div>
                      );
                    })}
                  </div>
                ) : <Empty>No timetable yet. Add a course, then add its weekly slots.</Empty>}
              </div>

              {/* ---- Assignments ---- */}
              <div className="card">
                <div className="card-h">
                  <span className="card-t">Coursework · {c.assignments.filter((a) => a.status === "open").length} open</span>
                  <span className="mini">Each one also appears on your Planner</span>
                </div>
                {c.assignments.length ? c.assignments.map((a) => {
                  const late = a.status === "open" && new Date(a.due_at) < new Date();
                  return (
                    <div className="row" key={a.id} style={a.status === "done" ? { opacity: 0.5 } : undefined}>
                      <button className="ico-box" title="Mark complete"
                        onClick={() => a.status === "open" && act(() => api.completeAssignment(a.id))}>
                        {a.status === "done" ? <Icon.check s={18} /> : <Icon.note s={18} />}
                      </button>
                      <div className="grow">
                        <div className="t" style={a.status === "done" ? { textDecoration: "line-through" } : undefined}>{a.title}</div>
                        <div className="s">{a.course || "No course"}{a.desc ? ` · ${a.desc}` : ""}</div>
                      </div>
                      <div className={"pill " + (late ? "red" : a.priority === "high" ? "blue" : "")}>{fmtDue(a.due_at)}</div>
                    </div>
                  );
                }) : <Empty>No coursework tracked yet.</Empty>}
              </div>
            </div>

            <div className="g-col">
              {/* ---- Today ---- */}
              <div className="card">
                <div className="card-h"><span className="card-t">Today</span><span className="pill">{c.today.length}</span></div>
                {c.today.length ? c.today.map((t) => (
                  <div className="row" key={t.id}>
                    <div className="ico-box"><Icon.clock s={16} /></div>
                    <div className="grow"><div className="t">{t.name}</div><div className="s">{t.start}–{t.end}{t.room ? ` · ${t.room}` : ""}</div></div>
                  </div>
                )) : <Empty>No classes today.</Empty>}
              </div>

              {/* ---- Exams ---- */}
              <div className="card">
                <div className="card-h">
                  <span className="card-t">Exams</span>
                  <button className="link" onClick={() => open("exam", { title: "", course_id: "", type: "cat", date: toLocalInput(null, 10, 7), room: "" })}>+ Add</button>
                </div>
                {c.exams.length ? c.exams.map((e) => {
                  const d = daysUntil(e.date);
                  return (
                    <div className="row" key={e.id}>
                      <div className="ico-box"><Icon.college s={16} /></div>
                      <div className="grow">
                        <div className="t">{e.title}</div>
                        <div className="s">{e.course || e.type.toUpperCase()}{e.room ? ` · ${e.room}` : ""}</div>
                      </div>
                      <div className={"pill " + (d !== null && d <= 5 ? "red" : "")}>{fmtDate(e.date)}</div>
                      <IconAction icon={Icon.trash} danger title="Delete exam"
                        onClick={() => confirm(`Delete ${e.title}?`, () => act(() => api.deleteExam(e.id)))} />
                    </div>
                  );
                }) : <Empty>No exams scheduled.</Empty>}
              </div>

              {/* ---- Academic calendar ---- */}
              <div className="card">
                <div className="card-h">
                  <span className="card-t">Academic Calendar</span>
                  <button className="link" onClick={() => open("event", { title: "", type: "holiday", date: toLocalInput(null, 9, 7) })}>+ Add</button>
                </div>
                {c.events.length ? c.events.map((e) => (
                  <div className="row" key={e.id}>
                    <div className="ico-box"><Icon.cal s={16} /></div>
                    <div className="grow"><div className="t" style={{ fontSize: 13 }}>{e.title}</div>
                      <div className="s">{e.type.replace("_", " ")}</div></div>
                    <div className="pill">{fmtDate(e.date)}</div>
                    <IconAction icon={Icon.trash} danger title="Delete event"
                      onClick={() => confirm(`Delete ${e.title}?`, () => act(() => api.deleteEvent(e.id)))} />
                  </div>
                )) : <Empty>Nothing on the calendar.</Empty>}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ------------------------------- dialogs ------------------------------- */}
      {dialog === "course" && (
        <Modal title="Add course" onClose={() => setDialog(null)} busy={busy}
          onSubmit={() => submit(() => api.createCourse({ ...f, attendance: Number(f.attendance) || 0 }))}>
          <Field label="Name"><input value={f.name} onChange={(e) => set("name", e.target.value)} required autoFocus /></Field>
          <div className="field-row">
            <Field label="Code"><input value={f.code} onChange={(e) => set("code", e.target.value)} placeholder="CS303" /></Field>
            <Field label="Attendance %"><input type="number" min={0} max={100} value={f.attendance} onChange={(e) => set("attendance", e.target.value)} /></Field>
          </div>
          <div className="field-row">
            <Field label="Faculty"><input value={f.faculty} onChange={(e) => set("faculty", e.target.value)} /></Field>
            <Field label="Room"><input value={f.room} onChange={(e) => set("room", e.target.value)} /></Field>
          </div>
        </Modal>
      )}

      {dialog === "class" && (
        <Modal title="Add timetable slot" onClose={() => setDialog(null)} busy={busy}
          onSubmit={() => submit(() => api.createClass({ ...f, day_of_week: Number(f.day_of_week) }))}>
          <Field label="Course">
            <select value={f.course_id} onChange={(e) => set("course_id", e.target.value)} required>
              {c?.courses.map((co) => <option key={co.id} value={co.id}>{co.name}</option>)}
            </select>
          </Field>
          <Field label="Day">
            <select value={f.day_of_week} onChange={(e) => set("day_of_week", e.target.value)}>
              {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d, i) => <option key={d} value={i}>{d}</option>)}
            </select>
          </Field>
          <div className="field-row">
            <Field label="Start"><input type="time" value={f.start_time} onChange={(e) => set("start_time", e.target.value)} /></Field>
            <Field label="End"><input type="time" value={f.end_time} onChange={(e) => set("end_time", e.target.value)} /></Field>
          </div>
          <Field label="Room" hint="Leave blank to use the course's room"><input value={f.room} onChange={(e) => set("room", e.target.value)} /></Field>
        </Modal>
      )}

      {dialog === "assignment" && (
        <Modal title="Add assignment" sub="It becomes a task on your Planner and Spider Sense starts watching the deadline."
          onClose={() => setDialog(null)} busy={busy}
          onSubmit={() => submit(() => api.createAssignment({
            title: f.title, description: f.description, priority: f.priority,
            est_minutes: Number(f.est_minutes) || 60,
            due_at: fromLocalInput(f.due_at),
            ...(f.course_id ? { course_id: f.course_id } : {}),
          }))}>
          <Field label="Title"><input value={f.title} onChange={(e) => set("title", e.target.value)} required autoFocus /></Field>
          <Field label="Course">
            <select value={f.course_id} onChange={(e) => set("course_id", e.target.value)}>
              <option value="">No course</option>
              {c?.courses.map((co) => <option key={co.id} value={co.id}>{co.name}</option>)}
            </select>
          </Field>
          <Field label="Description"><textarea value={f.description} onChange={(e) => set("description", e.target.value)} /></Field>
          <div className="field-row">
            <Field label="Due"><input type="datetime-local" value={f.due_at} onChange={(e) => set("due_at", e.target.value)} required /></Field>
            <Field label="Est. minutes"><input type="number" min={5} value={f.est_minutes} onChange={(e) => set("est_minutes", e.target.value)} /></Field>
          </div>
          <Field label="Priority">
            <select value={f.priority} onChange={(e) => set("priority", e.target.value)}>
              {["low", "med", "high"].map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </Field>
        </Modal>
      )}

      {dialog === "exam" && (
        <Modal title="Add exam" onClose={() => setDialog(null)} busy={busy}
          onSubmit={() => submit(() => api.createExam({
            title: f.title, type: f.type, room: f.room, date: fromLocalInput(f.date),
            ...(f.course_id ? { course_id: f.course_id } : {}),
          }))}>
          <Field label="Title"><input value={f.title} onChange={(e) => set("title", e.target.value)} required autoFocus /></Field>
          <Field label="Course">
            <select value={f.course_id} onChange={(e) => set("course_id", e.target.value)}>
              <option value="">No course</option>
              {c?.courses.map((co) => <option key={co.id} value={co.id}>{co.name}</option>)}
            </select>
          </Field>
          <div className="field-row">
            <Field label="Type">
              <select value={f.type} onChange={(e) => set("type", e.target.value)}>
                {["cat", "fat", "internal"].map((t) => <option key={t} value={t}>{t.toUpperCase()}</option>)}
              </select>
            </Field>
            <Field label="Room"><input value={f.room} onChange={(e) => set("room", e.target.value)} /></Field>
          </div>
          <Field label="Date"><input type="datetime-local" value={f.date} onChange={(e) => set("date", e.target.value)} required /></Field>
        </Modal>
      )}

      {dialog === "event" && (
        <Modal title="Add calendar entry" onClose={() => setDialog(null)} busy={busy}
          onSubmit={() => submit(() => api.createEvent({ title: f.title, type: f.type, date: fromLocalInput(f.date) }))}>
          <Field label="Title"><input value={f.title} onChange={(e) => set("title", e.target.value)} required autoFocus /></Field>
          <Field label="Type">
            <select value={f.type} onChange={(e) => set("type", e.target.value)}>
              {["holiday", "break", "exam_window", "event"].map((t) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}
            </select>
          </Field>
          <Field label="Date"><input type="datetime-local" value={f.date} onChange={(e) => set("date", e.target.value)} required /></Field>
        </Modal>
      )}
    </ModulePage>
  );
}
