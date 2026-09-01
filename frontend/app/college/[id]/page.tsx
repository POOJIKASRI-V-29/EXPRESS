"use client";
import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Icon } from "@/components/icons";
import { Empty } from "@/components/states";
import { ModulePage, Modal, Field, Bar, useModule, useConfirm } from "@/components/ui";
import { api } from "@/lib/api";
import type { CourseClass, CourseWorkspace } from "@/lib/types";

type Dialog = null | "module" | "topic" | "attendance" | "drive"
  | "course" | "class";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export default function CoursePage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { user, ready, data, state, error, reload, act } =
    useModule<CourseWorkspace>(() => api.course(id), [id]);

  const [dialog, setDialog] = useState<Dialog>(null);
  const [targetModule, setTargetModule] = useState<string>("");
  const [f, setF] = useState<any>({});
  const [busy, setBusy] = useState(false);
  const confirm = useConfirm();

  async function submit(fn: () => Promise<any>) {
    setBusy(true); await act(fn); setBusy(false); setDialog(null);
  }

  /** Ask with the real numbers, not a generic "are you sure?". */
  async function askDeleteCourse() {
    let detail = "This removes the course and everything inside it.";
    try {
      const i = await api.courseImpact(id);
      const parts = [
        i.modules ? `${i.modules} module(s)` : "",
        i.concepts ? `${i.concepts} concept(s)` : "",
        i.classes ? `${i.classes} timetable slot(s)` : "",
        i.exams ? `${i.exams} exam(s)` : "",
      ].filter(Boolean);
      detail = parts.length
        ? `Deletes ${i.course} and ${parts.join(", ")}.`
        : `Deletes ${i.course}.`;
      if (i.assignments_kept) {
        detail += ` ${i.assignments_kept} assignment(s) are kept — they stop naming the course.`;
      }
    } catch { /* fall back to the generic wording rather than blocking */ }
    confirm(detail, async () => {
      await act(() => api.deleteCourse(id));
      router.push("/college");
    });
  }

  if (!ready || !user) return null;
  const c = data;
  const hasData = !!c?.has_attendance_data;

  return (
    <ModulePage
      eyebrow={c?.code || "COURSE"}
      title={c?.name || "Course"}
      sub={c?.faculty || undefined}
      state={state} error={error} onRetry={reload}
      actions={<>
        <button className="btn sm" onClick={() => {
          setF({
            name: c?.name ?? "", code: c?.code ?? "", faculty: c?.faculty ?? "",
            room: c?.room ?? "", credits: c?.credits ?? 0,
          });
          setDialog("course");
        }}>Edit</button>
        <button className="btn sm ghost-red" onClick={askDeleteCourse}>Delete</button>
        <button className="btn sm" onClick={() => router.push("/college")}>All courses</button>
      </>}
    >
      {c && (
        <div className="stack">
          {/* ── Attendance ─────────────────────────────────────────────── */}
          <div className="card">
            <div className="card-h">
              <span className="card-t">Attendance</span>
              <button className="link" onClick={() => {
                setF({ attended_classes: c.attended_classes, total_classes: c.total_classes });
                setDialog("attendance");
              }}>Correct the figures</button>
            </div>

            <div className="att">
              <div className="att-figure">
                <div className={"att-pct num" + (hasData && c.attendance < 75 ? " risk" : "")}>
                  {hasData ? `${c.attendance}%` : "—"}
                </div>
                <div className="att-counts">
                  {hasData
                    ? `${c.attended_classes} attended of ${c.total_classes} held`
                    : "No classes recorded yet"}
                </div>
              </div>

              {/* Each control records a real class — that is why missing one
                  lowers the percentage rather than nudging a number. */}
              <div className="att-controls">
                <button className="btn ghost-red" onClick={() => act(() => api.markAttendance(c.id, false))}>
                  <Icon.x s={14} /> Missed a class
                </button>
                <button className="btn primary" onClick={() => act(() => api.markAttendance(c.id, true))}>
                  <Icon.check s={14} /> Attended a class
                </button>
              </div>
            </div>

            {hasData && (
              <>
                <div style={{ marginTop: 16 }}>
                  <Bar pct={c.attendance} tone={c.attendance < 75 ? "red" : "blue"} />
                </div>
                <div className="att-undo">
                  <span className="mini">Mis-tapped?</span>
                  <button className="link" onClick={() => act(() => api.undoAttendance(c.id, true))}>
                    Undo an attended
                  </button>
                  <button className="link" onClick={() => act(() => api.undoAttendance(c.id, false))}>
                    Undo a missed
                  </button>
                </div>
              </>
            )}
          </div>

          {/* ── Modules and concepts ───────────────────────────────────── */}
          <div className="card">
            <div className="card-h">
              <span className="card-t">
                Modules{c.topics_total ? ` · ${c.topics_done}/${c.topics_total} concepts` : ""}
              </span>
              <button className="link" onClick={() => { setF({ name: "" }); setDialog("module"); }}>
                + Add module
              </button>
            </div>

            {c.module_list.length === 0 ? (
              <Empty>
                No modules yet. Add them here, or ask JOCasta to build them from your syllabus.
              </Empty>
            ) : (
              c.module_list.map((m) => (
                <div className="mod" key={m.id}>
                  <div className="mod-h">
                    <div className="mod-name">{m.name}</div>
                    <div className="mod-count mini">
                      {m.total ? `${m.done}/${m.total}` : "no concepts"}
                    </div>
                    <button className="link" onClick={() => {
                      setTargetModule(m.id); setF({ name: "" }); setDialog("topic");
                    }}>+ Concept</button>
                    <button className="iconbtn sm danger" aria-label={`Delete ${m.name}`}
                      onClick={() => confirm(`Delete "${m.name}" and its concepts?`,
                        () => act(() => api.deleteModule(m.id)))}>
                      <Icon.trash s={13} />
                    </button>
                  </div>

                  {m.topics.length === 0 ? (
                    <div className="mini" style={{ padding: "6px 0 10px" }}>
                      No concepts in this module yet.
                    </div>
                  ) : (
                    <ul className="topics">
                      {m.topics.map((t) => (
                        <li key={t.id}>
                          <button className={"topic" + (t.done ? " done" : "")}
                            aria-pressed={t.done}
                            onClick={() => act(() => api.toggleCourseTopic(t.id))}>
                            <span className="tick">{t.done && <Icon.check s={12} />}</span>
                            <span className="topic-name">{t.name}</span>
                          </button>
                          <button className="iconbtn sm danger" aria-label={`Delete ${t.name}`}
                            onClick={() => act(() => api.deleteCourseTopic(t.id))}>
                            <Icon.trash s={12} />
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ))
            )}
          </div>

          {/* ── Timetable ──────────────────────────────────────────────
              Slots here are what Planner renders as classes on the day. */}
          <div className="card">
            <div className="card-h">
              <span className="card-t">Weekly classes</span>
              <button className="link" onClick={() => {
                setF({ day_of_week: 0, start_time: "09:00", end_time: "10:30",
                       room: c.room || "", editing: "" });
                setDialog("class");
              }}>Add a class</button>
            </div>

            {(c.classes ?? []).length === 0 ? (
              <Empty>
                No class scheduled yet. Add the weekly slot and it appears on your
                Planner every week on that day.
              </Empty>
            ) : (
              (c.classes ?? []).map((cl: CourseClass) => (
                <div className="row" key={cl.id}>
                  <div className="ico-box"><Icon.college s={17} /></div>
                  <div className="grow">
                    <div className="t">{cl.day_label} · {cl.start_time}–{cl.end_time}</div>
                    <div className="s">{cl.room || "No room set"}</div>
                  </div>
                  <button className="iconbtn sm" aria-label={`Edit ${cl.day_label} class`}
                    onClick={() => {
                      setF({ day_of_week: cl.day_of_week, start_time: cl.start_time,
                             end_time: cl.end_time, room: cl.room, editing: cl.id });
                      setDialog("class");
                    }}>
                    <Icon.edit s={15} />
                  </button>
                  <button className="iconbtn sm danger" aria-label={`Remove ${cl.day_label} class`}
                    onClick={() => confirm(
                      `Remove the ${cl.day_label} ${cl.start_time} class from your timetable?`,
                      () => act(() => api.deleteClass(cl.id)))}>
                    <Icon.trash s={15} />
                  </button>
                </div>
              ))
            )}
          </div>

          {/* ── Materials ──────────────────────────────────────────────── */}
          <div className="card">
            <div className="card-h">
              <span className="card-t">Materials</span>
              <button className="link" onClick={() => {
                setF({ drive_url: c.drive_url }); setDialog("drive");
              }}>{c.drive_url ? "Change link" : "Add link"}</button>
            </div>
            {c.drive_url ? (
              <div className="row">
                <div className="ico-box"><Icon.learning s={17} /></div>
                <div className="grow">
                  <div className="t">Google Drive</div>
                  <div className="s" style={{ wordBreak: "break-all" }}>{c.drive_url}</div>
                </div>
                <a className="btn sm" href={c.drive_url} target="_blank" rel="noreferrer">
                  Open Drive
                </a>
              </div>
            ) : (
              <Empty>
                No materials link yet. Paste a Drive folder or file URL — EXPRESS saves the
                link and opens it; it does not sync your Drive.
              </Empty>
            )}
          </div>
        </div>
      )}

      {dialog === "course" && (
        <Modal title="Edit course"
          sub="Attendance is corrected separately, so a typo here can never change your record."
          onClose={() => setDialog(null)} busy={busy}
          onSubmit={() => submit(() => api.updateCourse(id, {
            name: f.name, code: f.code, faculty: f.faculty, room: f.room,
            credits: Number(f.credits) || 0,
          }))}>
          <Field label="Course name">
            <input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })}
              required autoFocus />
          </Field>
          <div className="field-row">
            <Field label="Short code" hint="What you call it — JOCasta matches on this">
              <input value={f.code} onChange={(e) => setF({ ...f, code: e.target.value })} />
            </Field>
            <Field label="Credits" hint="Optional">
              <input type="number" min={0} max={20} inputMode="numeric" value={f.credits}
                onChange={(e) => setF({ ...f, credits: e.target.value })} placeholder="—" />
            </Field>
          </div>
          <div className="field-row">
            <Field label="Faculty">
              <input value={f.faculty} onChange={(e) => setF({ ...f, faculty: e.target.value })} />
            </Field>
            <Field label="Default room">
              <input value={f.room} onChange={(e) => setF({ ...f, room: e.target.value })}
                placeholder="AB-201" />
            </Field>
          </div>
        </Modal>
      )}

      {dialog === "class" && (
        <Modal title={f.editing ? "Edit class" : "Add a class"}
          sub="A weekly slot. It shows on your Planner on that day, every week."
          onClose={() => setDialog(null)} busy={busy}
          onSubmit={() => submit(() => {
            const body = {
              day_of_week: Number(f.day_of_week), start_time: f.start_time,
              end_time: f.end_time, room: f.room || "",
            };
            return f.editing
              ? api.updateClass(f.editing, body)
              : api.createClass({ course_id: id, ...body });
          })}>
          <Field label="Day">
            <select value={f.day_of_week}
              onChange={(e) => setF({ ...f, day_of_week: e.target.value })}>
              {DAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}
            </select>
          </Field>
          <div className="field-row">
            <Field label="Starts">
              <input type="time" value={f.start_time}
                onChange={(e) => setF({ ...f, start_time: e.target.value })} required />
            </Field>
            <Field label="Ends">
              <input type="time" value={f.end_time}
                onChange={(e) => setF({ ...f, end_time: e.target.value })} required />
            </Field>
          </div>
          <Field label="Room" hint="Optional">
            <input value={f.room} onChange={(e) => setF({ ...f, room: e.target.value })}
              placeholder="AB-201" />
          </Field>
        </Modal>
      )}

      {dialog === "module" && (
        <Modal title="Add module" onClose={() => setDialog(null)} busy={busy}
          onSubmit={() => submit(() => api.addModule(id, f.name))}>
          <Field label="Module name">
            <input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })}
              required autoFocus placeholder="Module 1 — Database Fundamentals" />
          </Field>
        </Modal>
      )}

      {dialog === "topic" && (
        <Modal title="Add concept" onClose={() => setDialog(null)} busy={busy}
          onSubmit={() => submit(() => api.addCourseTopic(targetModule, f.name))}>
          <Field label="Concept" hint="Course progress is counted from these.">
            <input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })}
              required autoFocus placeholder="Normalization" />
          </Field>
        </Modal>
      )}

      {dialog === "attendance" && (
        <Modal title="Correct attendance"
          sub="Set the real figures. Attended can never exceed classes held."
          onClose={() => setDialog(null)} busy={busy}
          onSubmit={() => submit(() => api.setAttendance(
            id, Number(f.attended_classes) || 0, Number(f.total_classes) || 0))}>
          <div className="field-row">
            <Field label="Classes attended">
              <input type="number" min={0} value={f.attended_classes} autoFocus
                onChange={(e) => setF({ ...f, attended_classes: e.target.value })} />
            </Field>
            <Field label="Classes held">
              <input type="number" min={0} value={f.total_classes}
                onChange={(e) => setF({ ...f, total_classes: e.target.value })} />
            </Field>
          </div>
          <div className="mini" style={{ marginTop: 10 }}>
            That works out to{" "}
            <strong>
              {Number(f.total_classes) > 0
                ? `${Math.round((Math.min(Number(f.attended_classes) || 0, Number(f.total_classes)) / Number(f.total_classes)) * 100)}%`
                : "—"}
            </strong>
          </div>
        </Modal>
      )}

      {dialog === "drive" && (
        <Modal title="Course materials"
          sub="EXPRESS stores the link and opens it. It does not read or sync your Drive."
          onClose={() => setDialog(null)} busy={busy}
          onSubmit={() => submit(() => api.updateCourse(id, { drive_url: f.drive_url }))}>
          <Field label="Google Drive URL">
            <input value={f.drive_url} autoFocus
              onChange={(e) => setF({ ...f, drive_url: e.target.value })}
              placeholder="https://drive.google.com/drive/folders/…" />
          </Field>
        </Modal>
      )}
    </ModulePage>
  );
}
