import {
  CloudAdapter,
  ConfigurationServiceClientCredentialFactory,
  MessageFactory,
  TeamsActivityHandler,
  TurnContext,
  createBotFrameworkAuthenticationFromConfiguration,
} from "botbuilder";
import { config } from "../config.js";
import { chat } from "../chat/agent.js";
import { clearHistory } from "../chat/session.js";

const WELCOME = [
  "안녕하세요. 업무 진행 상황을 확인해 드리는 비서입니다.",
  "",
  "이렇게 물어보세요.",
  "• 오늘 현황 알려줘",
  "• A사 계약 건 어디까지 갔어?",
  "• 내가 퇴근한 뒤에 바뀐 거 있어?",
  "• 노트북 발주 건 팀장 승인 단계 완료로 바꿔줘",
  "",
  "`초기화` 라고 보내면 대화 맥락을 비웁니다.",
].join("\n");

export class WorkFlowBot extends TeamsActivityHandler {
  constructor() {
    super();

    this.onMessage(async (context, next) => {
      const raw = TurnContext.removeRecipientMention(context.activity) ?? context.activity.text ?? "";
      const text = raw.trim();
      const conversationId = context.activity.conversation?.id ?? "teams";
      const user = context.activity.from?.name ?? "사용자";

      if (!text) {
        await context.sendActivity(MessageFactory.text(WELCOME));
        return next();
      }
      if (["초기화", "reset", "/reset"].includes(text.toLowerCase())) {
        clearHistory(conversationId);
        await context.sendActivity(MessageFactory.text("대화 맥락을 비웠습니다."));
        return next();
      }
      if (["도움말", "help", "/help"].includes(text.toLowerCase())) {
        await context.sendActivity(MessageFactory.text(WELCOME));
        return next();
      }

      await context.sendActivity({ type: "typing" });
      try {
        const result = await chat({ conversationId, message: text, user });
        await context.sendActivity(MessageFactory.text(result.reply, result.reply));
      } catch (err) {
        console.error("[teams] chat 실패:", err);
        await context.sendActivity(
          MessageFactory.text("업무 정보를 불러오는 중 오류가 났습니다. 잠시 후 다시 시도해 주세요."),
        );
      }
      return next();
    });

    this.onMembersAdded(async (context, next) => {
      const botId = context.activity.recipient?.id;
      for (const member of context.activity.membersAdded ?? []) {
        if (member.id !== botId) await context.sendActivity(MessageFactory.text(WELCOME));
      }
      return next();
    });
  }
}

/** Teams(Bot Framework) 인증이 붙은 어댑터. 앱 ID/비밀번호가 없으면 null. */
export function createTeamsAdapter(): CloudAdapter | null {
  if (!config.teams.appId || !config.teams.appPassword) return null;

  const credentialsFactory = new ConfigurationServiceClientCredentialFactory({
    MicrosoftAppId: config.teams.appId,
    MicrosoftAppPassword: config.teams.appPassword,
    MicrosoftAppTenantId: config.teams.appTenantId,
    MicrosoftAppType: config.teams.appType,
  });

  const auth = createBotFrameworkAuthenticationFromConfiguration(null, credentialsFactory);
  const adapter = new CloudAdapter(auth);

  adapter.onTurnError = async (context, error) => {
    console.error("[teams] 처리 중 오류:", error);
    await context.sendActivity("처리 중 오류가 발생했습니다. 다시 시도해 주세요.");
  };

  return adapter;
}
