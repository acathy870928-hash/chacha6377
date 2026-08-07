(() => {
  "use strict";

  const messagesEl = document.getElementById("messages");
  const formEl = document.getElementById("composer");
  const inputEl = document.getElementById("input");
  const sendBtn = document.getElementById("send-btn");
  const resetBtn = document.getElementById("reset-btn");
  const modeBadge = document.getElementById("mode-badge");
  const suggestionsEl = document.getElementById("suggestions");

  const TOOL_LABELS = {
    search_policy: "약관·FAQ 검색 중",
    list_products: "상품 목록 조회 중",
    calculate_premium: "보험료 계산 중",
    get_claim_guide: "청구 안내 조회 중",
    lookup_contract: "계약 조회 중",
    escalate_to_agent: "상담원 연결 접수 중",
  };

  const sessionId = getSessionId();
  let busy = false;

  function getSessionId() {
    let id = localStorage.getItem("insurance-chat-session");
    if (!id) {
      id =
        typeof crypto !== "undefined" && crypto.randomUUID
          ? crypto.randomUUID()
          : String(Date.now()) + Math.random().toString(16).slice(2);
      localStorage.setItem("insurance-chat-session", id);
    }
    return id;
  }

  function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function addMessage(role, text) {
    const wrap = document.createElement("div");
    wrap.className = `msg ${role}`;
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = text;
    wrap.appendChild(bubble);
    messagesEl.appendChild(wrap);
    scrollToBottom();
    return bubble;
  }

  function addToolLog(name) {
    const el = document.createElement("div");
    el.className = "tool-log";
    el.textContent = `⚙ ${TOOL_LABELS[name] || name}…`;
    messagesEl.appendChild(el);
    scrollToBottom();
    return el;
  }

  function addTypingIndicator() {
    const wrap = document.createElement("div");
    wrap.className = "msg bot";
    const bubble = document.createElement("div");
    bubble.className = "bubble typing";
    bubble.innerHTML = "<span></span><span></span><span></span>";
    wrap.appendChild(bubble);
    messagesEl.appendChild(wrap);
    scrollToBottom();
    return wrap;
  }

  function setBusy(value) {
    busy = value;
    sendBtn.disabled = value;
    inputEl.disabled = value;
    if (!value) inputEl.focus();
  }

  async function send(text) {
    if (busy || !text.trim()) return;

    suggestionsEl.classList.add("hidden");
    addMessage("user", text);
    setBusy(true);

    const typing = addTypingIndicator();
    let bubble = null;
    let buffered = "";

    const finishTyping = () => {
      if (typing.parentNode) typing.remove();
    };

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, message: text }),
      });

      if (!response.ok || !response.body) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let carry = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        carry += decoder.decode(value, { stream: true });
        const frames = carry.split("\n\n");
        carry = frames.pop() ?? "";

        for (const frame of frames) {
          const line = frame.split("\n").find((l) => l.startsWith("data: "));
          if (!line) continue;

          let event;
          try {
            event = JSON.parse(line.slice(6));
          } catch {
            continue;
          }

          if (event.type === "text") {
            finishTyping();
            if (!bubble) bubble = addMessage("bot", "");
            buffered += event.text;
            bubble.textContent = buffered;
            scrollToBottom();
          } else if (event.type === "tool_use") {
            finishTyping();
            addToolLog(event.name);
            // 툴 호출 이후 텍스트는 새 말풍선으로 분리한다.
            bubble = null;
            buffered = "";
          } else if (event.type === "error") {
            finishTyping();
            addMessage("error", event.message);
            bubble = null;
            buffered = "";
          }
        }
      }
    } catch (err) {
      addMessage("error", "서버와 통신하지 못했습니다. 잠시 후 다시 시도해 주세요.");
    } finally {
      finishTyping();
      setBusy(false);
    }
  }

  formEl.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = inputEl.value;
    inputEl.value = "";
    inputEl.style.height = "auto";
    send(text);
  });

  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      formEl.requestSubmit();
    }
  });

  inputEl.addEventListener("input", () => {
    inputEl.style.height = "auto";
    inputEl.style.height = `${Math.min(inputEl.scrollHeight, 140)}px`;
  });

  suggestionsEl.addEventListener("click", (e) => {
    const target = e.target;
    if (target instanceof HTMLButtonElement) send(target.textContent.trim());
  });

  resetBtn.addEventListener("click", async () => {
    if (busy) return;
    await fetch("/api/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId }),
    });
    messagesEl.innerHTML = "";
    addMessage("bot", "대화를 초기화했습니다. 무엇을 도와드릴까요?");
    suggestionsEl.classList.remove("hidden");
  });

  fetch("/api/health")
    .then((r) => r.json())
    .then((data) => {
      modeBadge.textContent =
        data.mode === "claude"
          ? `Claude 연결됨 · ${data.model}`
          : "규칙 기반 모드 (ANTHROPIC_API_KEY 미설정)";
    })
    .catch(() => {
      modeBadge.textContent = "서버에 연결하지 못했습니다";
    });

  inputEl.focus();
})();
