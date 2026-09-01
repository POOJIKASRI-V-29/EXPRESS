"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Icon } from "@/components/icons";
import { ModulePage, Modal, Field, Bar, Stat, AddButton, useModule } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDue } from "@/lib/format";
import type { CollegePayload } from "@/lib/types";

export default function CollegePage() {
  const { user, ready, data, state, error, reload, act } =
    useModule<CollegePayload>(() => api.college());
  const router = useRouter();
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [f, setF] = useState<any>({});

  if (!ready || !user) return null;
  const c = data;
  const courses = c?.courses ?? [];
  const openWork = (c?.assignments ?? []).filter((a) => a.status === "open");

  return (
    <ModulePage
      eyebrow={c?.semester?.label || "COLLEGE"}
      title="College"
      sub="Your courses. Open one to track attendance, modules and concepts."
      state={state} error={error} onRetry={reload}
      actions={<AddButton label="Course" onClick={() => {
        setF({ name: "", code: "", faculty: "", attended_classes: "", total_classes: "" });
        setAdding(true);
      }} />}
    >
      <div className="stack">
        {courses.length === 0 ? (
          <div className="empty" style={{ padding: 44 }}>
            <div style={{ fontSize: 15, color: "var(--text-2)", marginBottom: 6 }}>
              No courses yet.
            </div>
            <div style={{ marginBottom: 18 }}>
              Add your first course — you can enter its current attendance as you go.
            </div>
            <button className="btn primary" onClick={() => {
              setF({ name: "", code: "", faculty: "", attended_classes: "", total_classes: "" });
              setAdding(true);
            }}>
              <Icon.plus s={14} /> Add a course
            </button>
          </div>
        ) : (
          <>
            <div className="stats">
              <Stat k="Courses" v={courses.length}
                n={courses.filter((x) => x.at_risk).length
                  ? `${courses.filter((x) => x.at_risk).length} below the floor` : "all above the floor"} />
              <Stat k="Open coursework" v={openWork.length} n={`${(c?.assignments ?? []).length} total`} />
              <Stat k="Classes today" v={(c?.today ?? []).length}
                n={c?.today?.[0] ? `next ${c.today[0].start}` : "none scheduled"} />
            </div>

            <div className="g-auto">
              {courses.map((co) => (
                <button className="card course-card" key={co.id}
                  onClick={() => router.push(`/college/${co.id}`)}>
                  <div className="card-h">
                    <span className="card-t">{co.code || "Course"}</span>
                    {co.at_risk && <span className="pill red">At risk</span>}
                  </div>

                  <div className="course-name">{co.name}</div>
                  {(co.faculty || co.credits > 0) && (
                    <div className="mini" style={{ marginTop: 4 }}>
                      {[co.faculty, co.credits > 0 ? `${co.credits} credits` : ""]
                        .filter(Boolean).join(" · ")}
                    </div>
                  )}

                  <div className="course-figures">
                    <div>
                      <div className="k">Attendance</div>
                      <div className={"v num" + (co.at_risk ? " risk" : "")}>
                        {co.has_attendance_data ? `${co.attendance}%` : "—"}
                      </div>
                      <div className="n">
                        {co.has_attendance_data
                          ? `${co.attended_classes} of ${co.total_classes} classes`
                          : "no classes recorded"}
                      </div>
                    </div>
                    <div>
                      <div className="k">Concepts</div>
                      <div className="v num">
                        {co.topics_total ? `${co.progress}%` : "—"}
                      </div>
                      <div className="n">
                        {co.topics_total
                          ? `${co.topics_done} of ${co.topics_total} covered`
                          : `${co.modules} module(s), no concepts yet`}
                      </div>
                    </div>
                  </div>

                  {co.topics_total > 0 && (
                    <div style={{ marginTop: 12 }}><Bar pct={co.progress} /></div>
                  )}
                  {co.next_module && (
                    <div className="mini" style={{ marginTop: 12 }}>Next: {co.next_module}</div>
                  )}
                </button>
              ))}
            </div>

            {openWork.length > 0 && (
              <section className="section">
                <div className="section-h">
                  <span className="section-t">Coursework due</span>
                  <button className="link" onClick={() => router.push("/planner")}>Open planner</button>
                </div>
                {openWork.slice(0, 6).map((a) => (
                  <div className="row" key={a.id}>
                    <div className="ico-box"><Icon.note s={17} /></div>
                    <div className="grow">
                      <div className="t">{a.title}</div>
                      <div className="s">{a.course || "No course"}</div>
                    </div>
                    <div className={"pill " + (new Date(a.due_at) < new Date() ? "red" : "")}>
                      {fmtDue(a.due_at)}
                    </div>
                  </div>
                ))}
              </section>
            )}
          </>
        )}
      </div>

      {adding && (
        <Modal title="Add course"
          sub="Attendance is counted, not guessed. Enter the real figures if you have them, or leave them blank and record classes as they happen."
          onClose={() => setAdding(false)} busy={busy}
          onSubmit={async () => {
            setBusy(true);
            await act(() => api.createCourse({
              name: f.name, code: f.code, faculty: f.faculty,
              credits: Number(f.credits) || 0,
              drive_url: f.drive_url || "",
              attended_classes: Number(f.attended_classes) || 0,
              total_classes: Number(f.total_classes) || 0,
            }));
            setBusy(false); setAdding(false);
          }}>
          <Field label="Course name">
            <input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })}
              required autoFocus placeholder="Database Management Systems" />
          </Field>
          <div className="field-row">
            <Field label="Short code" hint="What you actually call it — JOCasta matches on this">
              <input value={f.code} onChange={(e) => setF({ ...f, code: e.target.value })} placeholder="DBMS" />
            </Field>
            <Field label="Faculty">
              <input value={f.faculty} onChange={(e) => setF({ ...f, faculty: e.target.value })} />
            </Field>
          </div>
          <div className="field-row">
            <Field label="Classes attended">
              <input type="number" min={0} inputMode="numeric" value={f.attended_classes}
                onChange={(e) => setF({ ...f, attended_classes: e.target.value })} placeholder="0" />
            </Field>
            <Field label="Classes held" hint="Leave both blank to start from zero">
              <input type="number" min={0} inputMode="numeric" value={f.total_classes}
                onChange={(e) => setF({ ...f, total_classes: e.target.value })} placeholder="0" />
            </Field>
          </div>
          <div className="field-row">
            <Field label="Credits" hint="Optional">
              <input type="number" min={0} max={20} inputMode="numeric" value={f.credits}
                onChange={(e) => setF({ ...f, credits: e.target.value })} placeholder="—" />
            </Field>
            <Field label="Drive link" hint="Optional — opened, never synced">
              <input type="url" inputMode="url" value={f.drive_url}
                onChange={(e) => setF({ ...f, drive_url: e.target.value })}
                placeholder="https://drive.google.com/…" />
            </Field>
          </div>
        </Modal>
      )}
    </ModulePage>
  );
}
