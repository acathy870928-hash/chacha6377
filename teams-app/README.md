# Teams 등록 절차

봇 코드는 이미 준비돼 있고, 아래는 **Azure/Teams 쪽 등록 작업**입니다. 회사 정책에 따라 관리자 승인이 필요할 수 있습니다.

1. **Azure Bot 리소스 생성**
   - Azure Portal → `Azure Bot` 생성 → 형식은 `Multi Tenant` (또는 사내 정책에 맞게 `Single Tenant`)
   - 생성된 **Microsoft App ID** 와 새로 만든 **client secret** 을 `.env` 의
     `MICROSOFT_APP_ID` / `MICROSOFT_APP_PASSWORD` 에 넣습니다. (Single Tenant 면 `MICROSOFT_APP_TENANT_ID` 도)

2. **메시징 엔드포인트 등록**
   - Azure Bot → Configuration → Messaging endpoint 에 `https://<서버주소>/api/messages` 입력
   - **HTTPS 로 외부에서 접근 가능해야 합니다.** 로컬 테스트는 [dev tunnels](https://learn.microsoft.com/azure/developer/dev-tunnels/) 나 ngrok 으로 터널을 뚫고 그 주소를 넣습니다.
     ```bash
     ngrok http 3978          # → https://xxxx.ngrok-free.app/api/messages
     ```

3. **Teams 채널 추가**
   - Azure Bot → Channels → Microsoft Teams 추가

4. **앱 패키지 업로드**
   - `manifest.json` 의 `id` 와 `bots[0].botId` 를 발급받은 App ID 로 바꿉니다.
   - 192×192 `color.png`, 32×32 투명 `outline.png` 를 같은 폴더에 넣습니다.
   - 세 파일을 zip 으로 묶어 Teams → 앱 → `앱 관리` → `앱 업로드` (사내 배포는 관리자 센터에서 조직 앱으로 게시)

5. **확인**
   - Teams 개인 채팅에서 봇에게 `오늘 현황` 이라고 보내보세요.
   - 채널에서는 `@업무 플로우 봇 A사 계약 건 어디까지 갔어?` 처럼 멘션해야 반응합니다.

승인이 오래 걸리면 그동안 웹 UI(`http://127.0.0.1:3978`)로 동일한 기능을 쓸 수 있습니다.
