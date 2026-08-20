/**
 * Claude API 키 없이 도구 계층(DB 조회·변경)이 제대로 도는지 확인하는 자체 점검.
 *   npm run selftest
 * 별도 임시 DB(./data/selftest.db)를 쓰므로 실제 업무 데이터는 건드리지 않는다.
 */
import fs from "node:fs";

process.env.BOT_DB_PATH = process.env.BOT_DB_PATH ?? "./data/selftest.db";
process.env.BOT_DEFAULT_OWNER = process.env.BOT_DEFAULT_OWNER ?? "나";
for (const suffix of ["", "-wal", "-shm"]) fs.rmSync(`${process.env.BOT_DB_PATH}${suffix}`, { force: true });

await import("./db/seed.js"); // 임시 DB에 템플릿 + 샘플 업무 생성
const { executeTool, TOOL_SPECS } = await import("./chat/tools.js");

const ctx = { user: "점검", owner: "나" };
let failures = 0;

function check(label: string, tool: string, input: unknown, expect: (parsed: any, raw: string) => boolean): void {
  const { content, isError } = executeTool(tool, input, ctx);
  let ok = !isError;
  let parsed: any = null;
  if (ok) {
    try {
      parsed = JSON.parse(content);
      ok = expect(parsed, content);
    } catch {
      ok = false;
    }
  }
  if (!ok) failures += 1;
  console.log(`${ok ? "✅" : "❌"} ${label}`);
  if (!ok) console.log(`   → ${content.slice(0, 300)}`);
}

console.log(`\n도구 ${TOOL_SPECS.length}개 점검\n`);

check("현황 요약", "get_work_summary", {}, (r) => r.진행중 >= 1 && r.지연 >= 1);
check("업무 목록", "list_tasks", { limit: 10 }, (r) => r.건수 >= 5);
check("지연 업무만", "list_tasks", { overdue_only: true }, (r) => r.목록.every((x: any) => x.지연여부 === true));
check("코드로 상세 조회", "get_task_progress", { task_query: "CT-2026-014" }, (r) => r.현재단계.includes("법무 검토"));
check("제목 일부로 조회", "get_task_progress", { task_query: "노트북" }, (r) => r.현재단계.includes("팀장 승인"));
check("보류 단계가 현재 단계로 잡힘", "get_task_progress", { task_query: "7월 월간 정산" }, (r) => r.현재단계.includes("유관부서 확인"));
check("모호한 이름 → 후보 반환", "get_task_progress", { task_query: "CT-2026" }, (r) => Array.isArray(r.후보) && r.후보.length > 1);
check("없는 업무 → 안내", "get_task_progress", { task_query: "존재하지않는업무" }, (r) => r.후보.length === 0);
check("최근 변경 이력", "get_recent_activity", { since_hours: 24 }, (r) => r.건수 >= 2);
check("플로우 템플릿 목록", "list_flow_templates", {}, (r) => Array.isArray(r) && r.length === 4);

check(
  "단계 완료 → 다음 단계 자동 착수",
  "update_step_status",
  { task_query: "CT-2026-014", step: "법무 검토", status: "완료", note: "점검" },
  (r) => r.현재단계.includes("팀장 승인") && r.단계[2].상태 === "완료",
);
check("업무 생성", "create_task", { title: "점검용 업무", template_name: "고객 이슈 대응", due_date: "2026-12-31" }, (r) => r.단계.length === 5 && r.단계[0].상태 === "진행중");
check("메모 추가", "add_note", { task_query: "점검용 업무", message: "메모 테스트" }, (r) => r.결과 === "메모 등록됨");
check("업무 상태 변경", "update_task_status", { task_query: "점검용 업무", status: "취소" }, (r) => r.업무상태 === "취소");
// 잘못된 입력은 예외 대신 오류 문자열로 돌아와야 한다 (대화가 끊기지 않도록).
{
  const bad = executeTool("update_step_status", { task_query: "노트북", step: 1, status: "이상한상태" }, ctx);
  const ok = bad.isError && bad.content.includes("입력값 오류");
  if (!ok) failures += 1;
  console.log(`${ok ? "✅" : "❌"} 잘못된 상태값 거부`);
}
console.log("");

console.log(failures === 0 ? "모든 점검 통과 ✨" : `실패 ${failures}건`);
process.exit(failures === 0 ? 0 : 1);
