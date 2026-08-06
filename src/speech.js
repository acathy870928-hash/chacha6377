/**
 * 브라우저 내장 음성 인식(Web Speech API) 래퍼.
 * 별도 서버나 API 키 없이 동작하며, 크롬/엣지/삼성인터넷/안드로이드 크롬에서 지원된다.
 * (사파리는 iOS 14.5+ 부분 지원, 파이어폭스는 미지원 → 텍스트 입력으로 대체)
 */

const SpeechRecognitionImpl =
  globalThis.SpeechRecognition || globalThis.webkitSpeechRecognition || null;

export function isSpeechSupported() {
  return Boolean(SpeechRecognitionImpl);
}

const ERROR_MESSAGES = {
  'not-allowed': '마이크 사용 권한이 필요합니다. 브라우저 주소창의 자물쇠 아이콘에서 마이크를 허용해 주세요.',
  'service-not-allowed': '마이크 사용 권한이 차단되어 있습니다. 브라우저 설정에서 허용해 주세요.',
  'no-speech': '음성이 감지되지 않았습니다. 다시 눌러서 말씀해 주세요.',
  'audio-capture': '마이크를 찾을 수 없습니다. 마이크 연결을 확인해 주세요.',
  network: '네트워크 오류로 음성 인식에 실패했습니다. 연결 상태를 확인해 주세요.',
  aborted: '',
};

/**
 * @param {{
 *   lang?: string,
 *   onInterim?: (text: string) => void,
 *   onResult?: (text: string) => void,
 *   onError?: (message: string) => void,
 *   onStateChange?: (listening: boolean) => void,
 * }} handlers
 */
export function createRecorder(handlers = {}) {
  const {
    lang = 'ko-KR',
    onInterim = () => {},
    onResult = () => {},
    onError = () => {},
    onStateChange = () => {},
  } = handlers;

  let recognition = null;
  let listening = false;
  let finalText = '';

  function stop() {
    if (recognition && listening) recognition.stop();
  }

  function start() {
    if (!SpeechRecognitionImpl) {
      onError('이 브라우저는 음성 인식을 지원하지 않습니다. 크롬 또는 엣지를 사용하거나 아래에 직접 입력해 주세요.');
      return;
    }
    if (listening) {
      stop();
      return;
    }

    finalText = '';
    recognition = new SpeechRecognitionImpl();
    recognition.lang = lang;
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      listening = true;
      onStateChange(true);
    };

    recognition.onresult = (event) => {
      let interim = '';
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        const transcript = result[0].transcript;
        if (result.isFinal) finalText += `${transcript} `;
        else interim += transcript;
      }
      const combined = `${finalText}${interim}`.trim();
      if (combined) onInterim(combined);
    };

    recognition.onerror = (event) => {
      const message = ERROR_MESSAGES[event.error] ?? `음성 인식 오류: ${event.error}`;
      if (message) onError(message);
    };

    recognition.onend = () => {
      listening = false;
      onStateChange(false);
      const text = finalText.trim();
      if (text) onResult(text);
    };

    try {
      recognition.start();
    } catch {
      onError('음성 인식을 시작할 수 없습니다. 잠시 후 다시 시도해 주세요.');
    }
  }

  return {
    start,
    stop,
    toggle: start,
    isListening: () => listening,
  };
}
