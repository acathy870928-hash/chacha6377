/**
 * AI 브리핑 엔드포인트 (선택 기능)
 * ---------------------------------------------------------------
 * 이 함수는 "계산"을 하지 않습니다.
 * 프런트엔드의 룰 엔진이 이미 확정한 숫자를 받아 해석만 시킵니다.
 * ANTHROPIC_API_KEY가 없으면 503을 돌려주고, 프런트엔드는
 * AI 카드만 접은 채 나머지 기능을 그대로 제공합니다.
 */

import Anthropic from '@anthropic-ai/sdk';

const MODEL = 'claude-opus-5';

const SYSTEM = `당신은 한국의 은퇴·연금 설계를 설명하는 조력자입니다.

절대 규칙:
- 사용자가 준 JSON 안의 숫자만 사용하세요. 새로운 금액·세율·비율을 절대 만들어내지 마세요.
- 계산을 다시 하지 마세요. 이미 확정된 결과를 해석하는 것이 당신의 일입니다.
- 확신할 수 없는 제도·세법 내용은 말하지 마세요.
- 특정 금융상품을 추천하지 마세요. 이것은 투자·세무 자문이 아닙니다.

작성 방식:
- 한국어 평문. 마크다운 기호(#, *, -)를 쓰지 마세요.
- 세 문단으로 쓰세요.
  1문단: 이 사람의 노후가 지금 어떤 상태인지 한 문장으로 요약하고, 그 근거가 되는 숫자를 짚습니다.
  2문단: 진단 목록 중 가장 시급한 하나를 골라, 왜 그것이 다른 것보다 먼저인지 설명합니다.
  3문단: 앞으로 12개월 안에 할 수 있는 구체적인 행동 하나를 제시합니다.
- 전체 500자 이내. 위로하거나 겁주지 말고, 담담하게 사실만 전하세요.`;

function bad(res, status, message) {
  res.status(status).json({ error: message });
}

export default async function handler(req, res) {
  if (req.method !== 'POST') return bad(res, 405, 'POST만 허용됩니다.');

  if (!process.env.ANTHROPIC_API_KEY) {
    return bad(res, 503, 'AI 브리핑이 설정되지 않았습니다 (ANTHROPIC_API_KEY 없음).');
  }

  let payload = req.body;
  if (typeof payload === 'string') {
    try { payload = JSON.parse(payload); } catch { return bad(res, 400, '요청 본문을 해석할 수 없습니다.'); }
  }
  if (!payload || typeof payload !== 'object' || !payload.metrics) {
    return bad(res, 400, '진단 결과가 필요합니다.');
  }

  // 전송되는 것은 계산된 지표뿐입니다. 원본 입력값은 브라우저를 떠나지 않습니다.
  const summary = JSON.stringify({
    score: payload.score,
    metrics: payload.metrics,
    profile: payload.profile,
    findings: Array.isArray(payload.findings) ? payload.findings.slice(0, 8) : [],
  });

  try {
    const client = new Anthropic();
    const response = await client.beta.messages.create({
      model: MODEL,
      max_tokens: 2000, // 500자 브리핑이므로 의도적으로 낮게 잡습니다.
      betas: ['server-side-fallback-2026-07-01'],
      fallbacks: 'default',
      output_config: { effort: 'medium' },
      system: SYSTEM,
      messages: [{
        role: 'user',
        content: `아래는 연금설계 계산 엔진이 산출한 결과입니다. 이 숫자만 근거로 브리핑을 작성하세요.\n\n${summary}`,
      }],
    });

    if (response.stop_reason === 'refusal') {
      return bad(res, 422, '이 요청에 대한 브리핑을 생성할 수 없습니다.');
    }

    const text = response.content
      .filter((block) => block.type === 'text')
      .map((block) => block.text)
      .join('\n')
      .trim();

    if (!text) return bad(res, 502, '빈 응답을 받았습니다.');

    res.setHeader('cache-control', 'no-store');
    return res.status(200).json({ text, model: response.model });
  } catch (err) {
    const status = err?.status;
    if (status === 401 || status === 403) return bad(res, 503, 'API 키가 유효하지 않습니다.');
    if (status === 429) return bad(res, 429, '요청이 많습니다. 잠시 후 다시 시도해 주세요.');
    console.error('advisor failed:', err?.message || err);
    return bad(res, 502, '브리핑 생성에 실패했습니다.');
  }
}
