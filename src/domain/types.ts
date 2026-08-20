export const TASK_STATUSES = ["진행중", "완료", "보류", "취소"] as const;
export const STEP_STATUSES = ["대기", "진행중", "완료", "보류", "생략"] as const;
export const PRIORITIES = ["높음", "보통", "낮음"] as const;

export type TaskStatus = (typeof TASK_STATUSES)[number];
export type StepStatus = (typeof STEP_STATUSES)[number];
export type Priority = (typeof PRIORITIES)[number];

export interface FlowTemplate {
  id: number;
  name: string;
  description: string | null;
}

export interface FlowTemplateStep {
  id: number;
  template_id: number;
  seq: number;
  name: string;
  owner_role: string | null;
  sla_days: number | null;
}

export interface Task {
  id: number;
  code: string | null;
  title: string;
  template_id: number | null;
  owner: string | null;
  requester: string | null;
  priority: Priority;
  due_date: string | null;
  status: TaskStatus;
  created_at: string;
  updated_at: string;
}

export interface TaskStep {
  id: number;
  task_id: number;
  seq: number;
  name: string;
  assignee: string | null;
  status: StepStatus;
  due_date: string | null;
  started_at: string | null;
  completed_at: string | null;
  note: string | null;
}

export interface TaskEvent {
  id: number;
  task_id: number;
  step_id: number | null;
  actor: string | null;
  kind: string;
  message: string;
  created_at: string;
}

/** 챗봇이 "어디까지 진행됐는지" 답할 때 쓰는 요약 구조 */
export interface TaskProgress {
  task: Task;
  templateName: string | null;
  steps: TaskStep[];
  currentStep: TaskStep | null;
  doneCount: number;
  totalCount: number;
  percent: number;
  overdue: boolean;
  daysLeft: number | null;
  blockedSteps: TaskStep[];
  recentEvents: TaskEvent[];
}
