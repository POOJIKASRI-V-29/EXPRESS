export interface Task {
  id: string; title: string; category: string; due_at: string | null;
  est_minutes: number; priority: string; status: string; icon: string;
  meta: string; source: string; postpone_count: number;
}
export interface Notification {
  id: string; level: string; title: string; kind: string; module: string;
  /** 1 info .. 5 critical — the API already returns these ordered by it. */
  severity: number;
  explanation: string;
  action_label: string;
  action_href: string;
  source: string;
  acknowledged: boolean; resolved: boolean; created_at: string; ref_id: string | null;
}
export interface HomePayload {
  time_context: string; greeting: string; user_name: string; semester: string;
  focus: { id: string; title: string; est_minutes: number; course: string } | null;
  up_next: { id: string; title: string; meta: string; due_at: string | null; icon: string }[];
  attendance: number;
  /** 0 means there are no courses yet, not that attendance is bad. */
  course_count: number;
  banner: { level: string; title: string; id: string } | null;
}
export interface PendingAction { tool: string; risk: string; summary: string; }
export interface Verification {
  attempted: number; succeeded: number; failed: number;
  failures: { tool: string; error: string }[];
}
export interface JocastaResult {
  reply: string; planner: string; modules: string[];
  calls: { tool: string; ok: boolean; result: any; error: string | null }[];
  verification?: Verification | null;
  /** Set when the plan needs approval before it runs. */
  pending?: { actions: PendingAction[]; reason: string; risk: string } | null;
  confirm_token?: string | null;
  /** Which context slices informed the answer — shown so replies are explainable. */
  context_used?: string[];
}
export interface AttachmentInfo {
  filename: string;
  kind: string;
  pages: number;
  chars: number;
  preview: string;
  /** What the server recognised in the file — used to hint at what's possible. */
  found: { classes: number; modules: number; concepts: number };
  attachment_token: string;
}
export interface JocastaContext {
  included_slices: string[];
  brief: string;
  context: Record<string, any>;
}

/* ---- College ---- */
export interface Course {
  id: string; code: string; name: string; faculty: string; room: string;
  /** Derived from attended/total; 0 also means "no classes held yet". */
  attendance: number;
  attended_classes: number;
  total_classes: number;
  /** False when no classes have been held — render "—", not 0%. */
  has_attendance_data: boolean;
  /** 0 means "not recorded" — simply not shown, never rendered as zero credits. */
  credits: number;
  drive_url: string;
  modules: number;
  topics_done: number;
  topics_total: number;
  progress: number;
  next_module: string;
  at_risk: boolean;
  assignments_open: number;
}
export interface CourseImpact {
  course: string; modules: number; concepts: number; classes: number;
  assignments_kept: number; exams: number;
}
export interface CourseTopic { id: string; name: string; done: boolean; }
export interface CourseModule {
  id: string; name: string; order: number;
  topics: CourseTopic[]; done: number; total: number;
}
export interface CourseClass {
  id: string; day_of_week: number; day_label: string;
  start_time: string; end_time: string; room: string;
}
export interface CourseWorkspace extends Omit<Course, "at_risk" | "assignments_open"> {
  module_list: CourseModule[];
  /** This course's recurring weekly slots — what Planner renders as classes. */
  classes: CourseClass[];
}
export interface TimetableSlot {
  id: string; day: number; day_label: string; start: string; end: string;
  room: string; course_id: string | null; course: string; today: boolean;
}
export interface CollegeAssignment {
  id: string; title: string; desc: string; due_at: string; status: string;
  priority: string; est_minutes: number; course_id: string | null; course: string;
}
export interface CollegePayload {
  semester: { id: string; label: string; tagline: string; start_date: string | null; end_date: string | null } | null;
  attendance: number; attendance_floor: number;
  courses: Course[]; timetable: TimetableSlot[];
  today: { id: string; start: string; end: string; name: string; room: string; course_id: string | null }[];
  assignments: CollegeAssignment[];
  exams: { id: string; title: string; type: string; date: string; room: string; course: string }[];
  events: { id: string; title: string; type: string; date: string; end_date: string | null }[];
}

/* ---- Planner ---- */
/** Task · Study · Project · Personal · Class (Class comes from the timetable). */
export type PlannerCategory = "Task" | "Study" | "Project" | "Personal" | "Class";
export interface PlannerItem {
  id: string; kind: string; time: string; end: string | null; title: string;
  meta: string; icon: string; status: string; movable: boolean;
  category: PlannerCategory;
  /** Tasks, exams and events can be corrected here. Classes cannot: they
   *  belong to the timetable and are managed on their course. */
  editable?: boolean;
  can_complete?: boolean;
  priority?: string; source?: string; est_minutes?: number;
  due_at?: string | null; stored_category?: string; course_id?: string | null;
  /** Exams and events carry their own date so the edit dialog can prefill it. */
  date?: string | null; end_date?: string | null;
  exam_type?: string; event_type?: string; room?: string;
}
export interface PlannerDay {
  offset: number; date: string; day_label: string; is_today: boolean;
  items: PlannerItem[]; open_count: number; booked_minutes: number;
}
export interface PlannerPayload {
  now: string; today: PlannerDay; days: PlannerDay[];
  conflicts: { key: string; title: string }[];
  unscheduled: {
    id: string; title: string; meta: string; icon: string; priority: string;
    est_minutes: number; category: PlannerCategory; source: string;
  }[];
  categories: PlannerCategory[];
}

/* ---- Learning ---- */
export interface Topic {
  id: string; name: string; area: string; state: string; progress: number;
  minutes: number; course: string; scheduled: boolean; last_reviewed_at: string | null;
}
export interface LearningPayload {
  areas: string[]; states: string[]; week_minutes: number; total_minutes: number;
  session_count: number; topics: Topic[];
  skills: { id: string; name: string; level: number; pct: number }[];
  recent_sessions: { id: string; topic_id: string; topic: string; minutes: number; note: string; started_at: string }[];
}

/* ---- Projects ---- */
export interface Project {
  id: string; name: string; description: string; phase: string; commits: number;
  stack: string; status: string; completion: number; priority: number;
  repo_url: string; due_at: string | null; note_count: number;
  phases: { id: string; name: string; order: number; done: boolean }[];
  tasks: { id: string; title: string; status: string; due_at: string | null }[];
  open_tasks: number;
}

/* ---- Career ---- */
export interface Internship {
  id: string; company: string; role: string; status: string; location: string; link: string;
  applications: { id: string; stage: string; notes: string; deadline: string | null }[];
}
export interface CareerPayload {
  stages: string[]; pipeline: Record<string, number>; internships: Internship[];
}

/* ---- Personal ---- */
export interface Note {
  id: string; title: string; body: string; tags: string; pinned: boolean;
  ref_type: string; ref_id: string | null; ref_label: string; updated_at: string;
}
export interface Habit {
  id: string; title: string; cadence: string; icon: string; streak: number;
  target_per_week: number; done_today: boolean; week: boolean[]; done_this_week: number;
}
export interface PersonalPayload {
  notes: Note[]; tags: string[]; habits: Habit[]; habits_done_today: number; today: string;
}

/* ---- Goals ---- */
export interface Goal {
  id: string; title: string; detail: string; horizon: string; category: string;
  status: string; target_date: string | null; progress: number; progress_source: string;
  links: { id: string; ref_type: string; ref_id: string; label: string; progress: number }[];
}
export interface GoalsPayload {
  goals: Goal[];
  linkable: Record<string, { id: string; label: string }[]>;
}

/* ---- Memory ---- */
export interface MemoryItem {
  id: string; text: string; category: string; source: string; pinned: boolean;
  created_at: string; updated_at: string;
}
export interface MemoryPayload {
  categories: string[]; counts: Record<string, number>; total: number;
  from_jocasta: number; pinned: number; query: string; filter: string;
  memories: MemoryItem[];
}

/* ---- Finance ---- */
export interface BudgetRow {
  id: string; category: string; limit: number; spent: number; pct: number; state: string;
}
export interface FinancePayload {
  month_spent: number; month_income: number; net: number; entry_count: number;
  by_category: { category: string; amount: number }[];
  budgets: BudgetRow[];
  recent: { id: string; amount: number; category: string; kind: string; note: string; date: string }[];
}

/* ---- Integrations ---- */
export interface IntegrationRow {
  provider: string; label: string; icon: string; blurb: string; scopes: string;
  id: string | null;
  /** unconfigured | disconnected | pending | connected | error */
  status: string;
  connectable: boolean;
  account_label: string;
  last_sync_at: string | null;
  last_error: string;
  token_expires_at: string | null;
  token_expired: boolean;
  requires: string | null;
  redirect_uri: string | null;
}
export interface IntegrationsPayload {
  integrations: IntegrationRow[]; connected: number; note: string;
}

/* ---- Progress ---- */
export interface ProgressReport {
  generated_at: string;
  tasks: { total: number; done: number; open: number; overdue: number; completion_pct: number;
           series: { date: string; count: number }[] };
  college: { courses: number; attendance: number; at_risk: { name: string; attendance: number }[];
             assignments_total: number; assignments_done: number };
  learning: { topics: number; strong: number; needs_revision: number; avg_progress: number;
              skills: number; avg_skill: number; total_minutes: number; session_count: number;
              series: { date: string; minutes: number }[] };
  projects: { total: number; active: number; avg_completion: number };
  career: { applications: number; interviewing: number; by_stage: Record<string, number> };
  goals: { total: number; active: number; achieved: number; avg_progress: number };
  habits: { total: number; done_today: number; best_streak: number };
  personal: { notes: number; memories: number };
  finance: FinancePayload;
  signals: { active: number };
}
