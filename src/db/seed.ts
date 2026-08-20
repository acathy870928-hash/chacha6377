/**
 * 샘플 플로우 템플릿 + 예시 업무를 넣는다.
 *   npm run db:seed     기존 데이터 유지, 템플릿만 없으면 추가
 *   npm run db:reset    전부 지우고 처음부터
 */
import { getDb, now, resetDb, today } from "./index.js";
import { config } from "../config.js";
import { addDays, createTask, setStepStatus } from "../domain/service.js";

const ME = config.defaultOwner || "나";

const TEMPLATES: Array<{ name: string; description: string; steps: Array<[string, string, number]> }> = [
  {
    name: "신규 계약 검토",
    description: "유관부서 요청부터 날인·보관까지의 계약 검토 플로우",
    steps: [
      ["요청 접수", "담당자", 1],
      ["계약서 초안 검토", "담당자", 2],
      ["법무 검토", "법무팀", 3],
      ["팀장 승인", "팀장", 1],
      ["상대사 회신·조율", "담당자", 3],
      ["날인 및 보관", "담당자", 1],
    ],
  },
  {
    name: "구매 발주",
    description: "구매 요청 접수부터 대금 지급까지",
    steps: [
      ["구매요청 접수", "담당자", 1],
      ["견적 비교", "담당자", 2],
      ["품의 작성", "담당자", 1],
      ["팀장 승인", "팀장", 1],
      ["발주", "구매팀", 1],
      ["입고 확인", "담당자", 5],
      ["대금 지급", "재무팀", 3],
    ],
  },
  {
    name: "월간 정산",
    description: "월 마감 정산 플로우",
    steps: [
      ["자료 수집", "담당자", 2],
      ["데이터 검증", "담당자", 2],
      ["정산서 작성", "담당자", 1],
      ["유관부서 확인", "유관부서", 2],
      ["재무 승인", "재무팀", 2],
      ["마감 처리", "담당자", 1],
    ],
  },
  {
    name: "고객 이슈 대응",
    description: "고객 문의·클레임 처리 플로우",
    steps: [
      ["이슈 접수", "담당자", 1],
      ["원인 파악", "담당자", 2],
      ["대응안 수립", "담당자", 1],
      ["고객 회신", "담당자", 1],
      ["재발방지 등록", "담당자", 2],
    ],
  },
];

function seedTemplates(): void {
  const db = getDb();
  const insertTemplate = db.prepare("INSERT OR IGNORE INTO flow_templates (name, description) VALUES (?, ?)");
  const insertStep = db.prepare(
    "INSERT OR IGNORE INTO flow_template_steps (template_id, seq, name, owner_role, sla_days) VALUES (?, ?, ?, ?, ?)",
  );
  const findId = db.prepare<[string], { id: number }>("SELECT id FROM flow_templates WHERE name = ?");

  const tx = db.transaction(() => {
    for (const t of TEMPLATES) {
      insertTemplate.run(t.name, t.description);
      const id = findId.get(t.name)!.id;
      t.steps.forEach(([name, role, sla], i) => insertStep.run(id, i + 1, name, role, sla));
    }
  });
  tx();
}

function seedTasks(): void {
  const db = getDb();
  const existing = db.prepare<[], { c: number }>("SELECT COUNT(*) AS c FROM tasks").get()!;
  if (existing.c > 0) {
    console.log(`이미 업무 ${existing.c}건이 있어 샘플 업무는 건너뜁니다. (전체 초기화: npm run db:reset)`);
    return;
  }

  // 1) 법무 검토에서 멈춰 있는 계약 건 (마감 임박)
  const a = createTask({
    title: "A사 유지보수 계약 갱신",
    code: "CT-2026-014",
    templateName: "신규 계약 검토",
    owner: ME,
    requester: "영업1팀",
    priority: "높음",
    dueDate: addDays(today(), 3),
    actor: ME,
  });
  setStepStatus({ taskId: a.task.id, step: 1, status: "완료", note: "영업1팀 요청서 접수", actor: ME });
  setStepStatus({ taskId: a.task.id, step: 2, status: "완료", note: "독소조항 2건 표시", actor: ME });
  setStepStatus({ taskId: a.task.id, step: 3, status: "진행중", assignee: "법무팀 박변호사", note: "손해배상 한도 조항 검토 중", actor: "법무팀 박변호사" });

  // 2) 팀장 승인 대기 중인 구매 건
  const b = createTask({
    title: "노트북 15대 교체 발주",
    code: "PO-2026-088",
    templateName: "구매 발주",
    owner: ME,
    requester: "인프라팀",
    priority: "보통",
    dueDate: addDays(today(), 10),
    actor: ME,
  });
  setStepStatus({ taskId: b.task.id, step: 1, status: "완료", actor: ME });
  setStepStatus({ taskId: b.task.id, step: 2, status: "완료", note: "3개 업체 견적 비교 완료", actor: ME });
  setStepStatus({ taskId: b.task.id, step: 3, status: "완료", note: "품의서 상신", actor: ME });
  setStepStatus({ taskId: b.task.id, step: 4, status: "진행중", assignee: "이팀장", actor: ME });

  // 3) 이미 마감이 지난 지연 건
  const c = createTask({
    title: "7월 월간 정산",
    code: "SET-2026-07",
    templateName: "월간 정산",
    owner: ME,
    priority: "높음",
    dueDate: addDays(today(), -2),
    actor: ME,
  });
  setStepStatus({ taskId: c.task.id, step: 1, status: "완료", actor: ME });
  setStepStatus({ taskId: c.task.id, step: 2, status: "완료", note: "매출 데이터 3건 불일치 → 정정", actor: ME });
  setStepStatus({ taskId: c.task.id, step: 3, status: "완료", actor: ME });
  setStepStatus({ taskId: c.task.id, step: 4, status: "보류", assignee: "영업지원팀", note: "영업지원팀 담당자 휴가로 확인 지연", actor: ME });

  // 4) 방금 끝난 건
  const d = createTask({
    title: "B고객 배송지연 클레임",
    code: "CS-2026-231",
    templateName: "고객 이슈 대응",
    owner: ME,
    requester: "CS팀",
    priority: "보통",
    dueDate: addDays(today(), -1),
    actor: ME,
  });
  for (let seq = 1; seq <= 5; seq += 1) {
    setStepStatus({ taskId: d.task.id, step: seq, status: "완료", actor: ME });
  }

  // 5) 이제 막 시작한 건
  const e = createTask({
    title: "C사 NDA 체결",
    code: "CT-2026-015",
    templateName: "신규 계약 검토",
    owner: ME,
    requester: "신사업팀",
    priority: "낮음",
    dueDate: addDays(today(), 14),
    actor: ME,
  });
  setStepStatus({ taskId: e.task.id, step: 1, status: "진행중", actor: ME });

  // 조기 퇴근 이후 다른 사람이 남긴 변경 이력 (get_recent_activity 시연용)
  db.prepare("INSERT INTO task_events (task_id, actor, kind, message, created_at) VALUES (?, ?, ?, ?, ?)").run(
    a.task.id,
    "법무팀 박변호사",
    "note",
    "손해배상 한도 조항 수정안 회신함. 내일 오전까지 담당자 확인 필요.",
    now(),
  );
  db.prepare("INSERT INTO task_events (task_id, actor, kind, message, created_at) VALUES (?, ?, ?, ?, ?)").run(
    b.task.id,
    "이팀장",
    "note",
    "품의 금액 근거 자료 한 장 추가해 주세요.",
    now(),
  );

  console.log("샘플 업무 5건을 등록했습니다.");
}

const shouldReset = process.argv.includes("--reset");
if (shouldReset) {
  resetDb();
  console.log("기존 데이터를 모두 삭제했습니다.");
}
seedTemplates();
seedTasks();
console.log(`완료. DB: ${config.dbPath}`);
