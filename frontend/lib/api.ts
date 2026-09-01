import type * as T from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const KEY = "express_access_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(KEY);
}
export function setToken(t: string | null) {
  if (typeof window === "undefined") return;
  if (t) localStorage.setItem(KEY, t);
  else localStorage.removeItem(KEY);
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

async function request<R>(path: string, opts: RequestInit = {}, retry = true): Promise<R> {
  const headers: Record<string, string> = { "Content-Type": "application/json", ...(opts.headers as any) };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, { ...opts, headers, credentials: "include" });

  if (res.status === 401 && retry) {
    // try refresh via httpOnly cookie, then retry once
    const r = await fetch(`${BASE}/auth/refresh`, { method: "POST", credentials: "include" });
    if (r.ok) {
      const { access_token } = await r.json();
      setToken(access_token);
      return request<R>(path, opts, false);
    }
    setToken(null);
    if (typeof window !== "undefined" && !path.startsWith("/auth")) window.location.href = "/login";
    throw new ApiError(401, "Not authenticated");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch {}
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as R;
  return res.json();
}

const post = <R,>(p: string, body?: any) =>
  request<R>(p, { method: "POST", ...(body !== undefined ? { body: JSON.stringify(body) } : {}) });
const patch = <R,>(p: string, body: any) => request<R>(p, { method: "PATCH", body: JSON.stringify(body) });
const del = (p: string) => request<void>(p, { method: "DELETE" });

export const api = {
  // ---- auth ----
  register: (email: string, password: string, name: string) =>
    post<{ access_token: string }>("/auth/register", { email, password, name }),
  login: (email: string, password: string) => post<{ access_token: string }>("/auth/login", { email, password }),
  me: () => request<{ id: string; email: string; name: string }>("/auth/me"),
  // The refresh cookie is httpOnly — only the server can clear it, so logging
  // out has to be a request, not just dropping the local token.
  logout: () => post<void>("/auth/logout"),

  // ---- home / tasks / signals ----
  home: () => request<T.HomePayload>("/home"),
  tasks: () => request<T.Task[]>("/tasks"),
  createTask: (body: any) => post<T.Task>("/tasks", body),
  completeTask: (id: string) => post<T.Task>(`/tasks/${id}/complete`),
  reschedule: (id: string, due_at: string) => post<T.Task>(`/tasks/${id}/reschedule`, { due_at }),
  updateTask: (id: string, body: any) => patch<T.Task>(`/tasks/${id}`, body),
  deleteTask: (id: string) => del(`/tasks/${id}`),

  spiderSense: () => request<T.Notification[]>("/spider-sense"),
  ackSpider: (id: string) => post<T.Notification>(`/spider-sense/${id}/acknowledge`),
  ackAllSpider: () => post<{ acknowledged: number }>("/spider-sense/acknowledge-all"),

  jocasta: (text: string, attachment_token?: string | null) =>
    post<T.JocastaResult>("/jocasta/message",
      attachment_token ? { text, attachment_token } : { text }),

  /** Uploads a file and returns what was read. Decides nothing; writes nothing. */
  uploadAttachment: async (file: File): Promise<T.AttachmentInfo> => {
    const form = new FormData();
    form.append("file", file);
    const token = getToken();
    const res = await fetch(`${BASE}/jocasta/attachments`, {
      method: "POST",
      credentials: "include",
      // No Content-Type: the browser must set the multipart boundary itself.
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    });
    if (!res.ok) {
      let detail = res.statusText;
      try { detail = (await res.json()).detail || detail; } catch {}
      throw new Error(detail);
    }
    return res.json();
  },
  // Runs a plan the user approved. The token is re-verified server-side.
  jocastaConfirm: (confirm_token: string) =>
    post<T.JocastaResult>("/jocasta/confirm", { confirm_token }),
  jocastaContext: (q = "") =>
    request<T.JocastaContext>(`/jocasta/context${q ? `?q=${encodeURIComponent(q)}` : ""}`),

  // ---- college ----
  college: () => request<T.CollegePayload>("/college"),
  createCourse: (body: any) => post("/college/courses", body),
  updateCourse: (id: string, body: any) => patch(`/college/courses/${id}`, body),
  deleteCourse: (id: string) => del(`/college/courses/${id}`),
  // Attendance is counted: both outcomes record a class as held.
  markAttendance: (id: string, attended: boolean) =>
    post<T.Course>(`/college/courses/${id}/attendance`, { attended }),
  undoAttendance: (id: string, attended: boolean) =>
    post<T.Course>(`/college/courses/${id}/attendance/undo`, { attended }),
  setAttendance: (id: string, attended_classes: number, total_classes: number) =>
    patch<T.Course>(`/college/courses/${id}/attendance`, { attended_classes, total_classes }),

  // Course workspace
  course: (id: string) => request<T.CourseWorkspace>(`/college/courses/${id}`),
  addModule: (id: string, name: string) =>
    post<T.CourseWorkspace>(`/college/courses/${id}/modules`, { name }),
  deleteModule: (moduleId: string) => del(`/college/modules/${moduleId}`),
  // Namespaced: a course concept is a different thing from a learning topic.
  addCourseTopic: (moduleId: string, name: string) =>
    post<T.CourseWorkspace>(`/college/modules/${moduleId}/topics`, { name }),
  toggleCourseTopic: (topicId: string) =>
    post<T.CourseWorkspace>(`/college/topics/${topicId}/toggle`),
  deleteCourseTopic: (topicId: string) => del(`/college/topics/${topicId}`),
  createStructure: (id: string, modules: { name: string; topics: string[] }[], replace = false) =>
    post<T.CourseWorkspace>(`/college/courses/${id}/structure`, { modules, replace }),
  createClass: (body: any) => post("/college/classes", body),
  updateClass: (id: string, body: any) => patch(`/college/classes/${id}`, body),
  deleteClass: (id: string) => del(`/college/classes/${id}`),
  // What a course delete would take with it — shown before asking.
  courseImpact: (id: string) => request<T.CourseImpact>(`/college/courses/${id}/impact`),
  createExam: (body: any) => post("/college/exams", body),
  updateExam: (id: string, body: any) => patch(`/college/exams/${id}`, body),
  deleteExam: (id: string) => del(`/college/exams/${id}`),
  createEvent: (body: any) => post("/college/events", body),
  updateEvent: (id: string, body: any) => patch(`/college/events/${id}`, body),
  deleteEvent: (id: string) => del(`/college/events/${id}`),
  createSemester: (body: any) => post("/college/semesters", body),
  createAssignment: (body: any) => post("/assignments", body),
  completeAssignment: (id: string) => post(`/assignments/${id}/complete`),

  // ---- planner ----
  planner: (days = 7) => request<T.PlannerPayload>(`/planner?days=${days}`),
  schedule: (taskId: string, due_at: string) => post(`/planner/schedule/${taskId}`, { due_at }),

  // ---- learning ----
  learning: () => request<T.LearningPayload>("/learning"),
  createTopic: (body: any) => post("/learning/topics", body),
  updateTopic: (id: string, body: any) => patch(`/learning/topics/${id}`, body),
  deleteTopic: (id: string) => del(`/learning/topics/${id}`),
  logSession: (id: string, body: any) => post(`/learning/topics/${id}/sessions`, body),
  scheduleStudy: (id: string, body: any) => post(`/learning/topics/${id}/schedule`, body),
  createSkill: (body: any) => post("/learning/skills", body),
  updateSkill: (id: string, body: any) => patch(`/learning/skills/${id}`, body),
  deleteSkill: (id: string) => del(`/learning/skills/${id}`),

  // ---- projects ----
  projects: () => request<{ projects: T.Project[] }>("/projects"),
  createProject: (body: any) => post<T.Project>("/projects", body),
  updateProject: (id: string, body: any) => patch<T.Project>(`/projects/${id}`, body),
  deleteProject: (id: string) => del(`/projects/${id}`),
  addPhase: (id: string, body: any) => post<T.Project>(`/projects/${id}/phases`, body),
  togglePhase: (id: string, phaseId: string) => post<T.Project>(`/projects/${id}/phases/${phaseId}/toggle`),
  deletePhase: (id: string, phaseId: string) => del(`/projects/${id}/phases/${phaseId}`),
  addProjectTask: (id: string, body: any) => post<T.Project>(`/projects/${id}/tasks`, body),
  toggleProjectTask: (id: string, taskId: string) => post<T.Project>(`/projects/${id}/tasks/${taskId}/toggle`),

  // ---- career ----
  career: () => request<T.CareerPayload>("/career"),
  createInternship: (body: any) => post("/career/internships", body),
  updateInternship: (id: string, body: any) => patch(`/career/internships/${id}`, body),
  deleteInternship: (id: string) => del(`/career/internships/${id}`),
  createApplication: (body: any) => post("/career/applications", body),
  updateApplication: (id: string, body: any) => patch(`/career/applications/${id}`, body),
  deleteApplication: (id: string) => del(`/career/applications/${id}`),

  // ---- personal ----
  personal: () => request<T.PersonalPayload>("/personal"),
  createNote: (body: any) => post<T.Note>("/personal/notes", body),
  updateNote: (id: string, body: any) => patch<T.Note>(`/personal/notes/${id}`, body),
  deleteNote: (id: string) => del(`/personal/notes/${id}`),
  createHabit: (body: any) => post<T.Habit[]>("/personal/habits", body),
  updateHabit: (id: string, body: any) => patch<T.Habit[]>(`/personal/habits/${id}`, body),
  toggleHabit: (id: string) => post<T.Habit[]>(`/personal/habits/${id}/toggle`),
  deleteHabit: (id: string) => del(`/personal/habits/${id}`),

  // ---- goals ----
  goals: () => request<T.GoalsPayload>("/goals"),
  createGoal: (body: any) => post<T.Goal>("/goals", body),
  updateGoal: (id: string, body: any) => patch<T.Goal>(`/goals/${id}`, body),
  deleteGoal: (id: string) => del(`/goals/${id}`),
  linkGoal: (id: string, body: any) => post<T.Goal>(`/goals/${id}/links`, body),
  unlinkGoal: (id: string, linkId: string) => del(`/goals/${id}/links/${linkId}`),

  // ---- memory ----
  memory: (q = "", category = "All") => {
    const p = new URLSearchParams();
    if (q) p.set("q", q);
    if (category && category !== "All") p.set("category", category);
    const qs = p.toString();
    return request<T.MemoryPayload>(`/memory${qs ? `?${qs}` : ""}`);
  },
  createMemory: (body: any) => post<T.MemoryItem>("/memory", body),
  updateMemory: (id: string, body: any) => patch<T.MemoryItem>(`/memory/${id}`, body),
  deleteMemory: (id: string) => del(`/memory/${id}`),
  conversations: () => request<{ id: string; role: string; content: string; tool_name: string | null; created_at: string }[]>("/memory/conversations"),

  // ---- finance ----
  finance: () => request<T.FinancePayload>("/finance"),
  createEntry: (body: any) => post<T.FinancePayload>("/finance/entries", body),
  deleteEntry: (id: string) => del(`/finance/entries/${id}`),
  createBudget: (body: any) => post<T.FinancePayload>("/finance/budgets", body),
  updateBudget: (id: string, body: any) => patch<T.FinancePayload>(`/finance/budgets/${id}`, body),
  deleteBudget: (id: string) => del(`/finance/budgets/${id}`),

  // ---- integrations ----
  integrations: () => request<T.IntegrationsPayload>("/integrations"),
  // Starts a real OAuth flow: returns the provider's consent URL to visit.
  authorizeIntegration: (provider: string) =>
    post<{ authorize_url: string; provider: string; redirect_uri: string }>(
      `/integrations/${provider}/authorize`),
  refreshIntegration: (provider: string) => post<T.IntegrationRow>(`/integrations/${provider}/refresh`),
  disconnectIntegration: (provider: string) => post<void>(`/integrations/${provider}/disconnect`),

  // ---- progress ----
  progress: () => request<{ tasks_total: number; tasks_done: number; attendance: number; memories: number }>("/progress"),
  progressReport: () => request<T.ProgressReport>("/progress/report"),
};
