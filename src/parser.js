/**
 * 한국어 음성/텍스트를 법인카드 지출 항목으로 변환하는 파서.
 *
 *   "어제 거래처 미팅 스타벅스에서 3만 2천원 3명"
 *     → { date: '2026-08-05', merchant: '스타벅스', amount: 32000,
 *         category: '접대비', headcount: 3, purpose: '거래처 미팅' }
 *
 * 브라우저(<script type="module">)와 Node 양쪽에서 그대로 쓸 수 있도록
 * DOM 의존성 없이 순수 함수로만 구성한다.
 */

export const CATEGORIES = [
  '식대',
  '접대비',
  '복리후생비',
  '회의비',
  '교통비',
  '숙박비',
  '사무용품비',
  '소모품비',
  '통신비',
  '도서인쇄비',
  '교육훈련비',
  '광고선전비',
  '기타',
];

/** 계정과목 추정 규칙. weight 가 큰 키워드가 우선한다. */
const CATEGORY_RULES = [
  {
    name: '접대비',
    weight: 3,
    keywords: ['접대', '거래처', '고객사', '바이어', '협력사', '클라이언트', '대접', '의전'],
  },
  {
    name: '복리후생비',
    weight: 2,
    keywords: ['회식', '간식', '다과', '경조사', '생일', '워크샵', '워크숍', '야근식대', '팀빌딩', '직원식대'],
  },
  {
    name: '회의비',
    weight: 2,
    keywords: ['회의', '회의실', '미팅룸', '브레인스토밍', '주간회의', '월간회의'],
  },
  {
    name: '교통비',
    weight: 3,
    keywords: [
      '택시', '버스', '지하철', '기차', 'ktx', 'srt', '주차', '주유', '기름', '통행료',
      '톨게이트', '하이패스', '렌터카', '대리운전', '항공', '비행기', '카카오티', '카카오t', '고속버스',
    ],
  },
  {
    name: '숙박비',
    weight: 3,
    keywords: ['숙박', '호텔', '모텔', '펜션', '게스트하우스', '리조트', '에어비앤비', '숙소'],
  },
  {
    name: '사무용품비',
    weight: 3,
    keywords: [
      '사무용품', '문구', '볼펜', '노트', '프린터', '토너', '잉크', '용지', 'a4',
      '키보드', '마우스', '모니터', 'usb', '케이블', '비품', '파일철',
    ],
  },
  {
    name: '소모품비',
    weight: 2,
    keywords: ['소모품', '부품', '공구', '청소', '세제', '휴지', '건전지', '배터리'],
  },
  {
    name: '통신비',
    weight: 3,
    keywords: ['통신', '휴대폰', '핸드폰', '인터넷', '데이터', '요금제', '로밍', '통신비'],
  },
  {
    name: '도서인쇄비',
    weight: 3,
    keywords: ['도서', '책', '서적', '인쇄', '복사', '제본', '명함', '출력'],
  },
  {
    name: '교육훈련비',
    weight: 3,
    keywords: ['교육', '세미나', '강의', '강좌', '컨퍼런스', '학회', '수강', '연수'],
  },
  {
    name: '광고선전비',
    weight: 3,
    keywords: ['광고', '홍보', '마케팅', '판촉', '배너', '전단', '경품'],
  },
  {
    name: '식대',
    weight: 1,
    keywords: [
      '식대', '식사', '점심', '중식', '저녁', '석식', '아침', '조식', '밥', '국밥', '김밥',
      '고기', '삼겹', '치킨', '피자', '분식', '커피', '카페', '음료', '디저트', '한식',
      '중국집', '일식', '짜장', '국수', '비빔밥', '도시락', '배달', '맛집', '식당', '술', '호프',
    ],
  },
];

/** 사용처 사전 — "에서" 조사가 없어도 상호를 잡아내기 위한 보조 목록. */
const KNOWN_MERCHANTS = [
  '스타벅스', '투썸플레이스', '투썸', '이디야', '메가커피', '컴포즈커피', '빽다방', '커피빈',
  '배달의민족', '배민', '쿠팡이츠', '요기요', '쿠팡', '네이버', '카카오T', '카카오택시',
  'GS25', 'CU', '세븐일레븐', '이마트24', '이마트', '홈플러스', '롯데마트', '다이소',
  '맥도날드', '버거킹', '롯데리아', '맘스터치', 'KFC', '서브웨이', '김밥천국', '한솥도시락',
  '올리브영', '교보문고', '영풍문고', '알라딘', 'YES24', '오피스디포', '모나미',
];

const HANGUL_DIGITS = { 영: 0, 공: 0, 일: 1, 이: 2, 삼: 3, 사: 4, 오: 5, 육: 6, 칠: 7, 팔: 8, 구: 9 };
const SMALL_UNITS = { 십: 10, 백: 100, 천: 1000 };
const BIG_UNITS = { 만: 10000, 억: 100000000 };

const NATIVE_COUNTS = {
  한: 1, 두: 2, 세: 3, 네: 4, 다섯: 5, 여섯: 6, 일곱: 7, 여덟: 8, 아홉: 9, 열: 10,
  혼자: 1, 둘: 2, 셋: 3, 넷: 4,
};

const WEEKDAYS = {
  일요일: 0, 일: 0, 월요일: 1, 월: 1, 화요일: 2, 화: 2, 수요일: 3, 수: 3,
  목요일: 4, 목: 4, 금요일: 5, 금: 5, 토요일: 6, 토: 6,
};

/** 한국어 수 표현(혼용 포함)을 정수로 변환한다. "3만2천" → 32000, "십오만" → 150000 */
export function koreanNumberToInt(input) {
  const s = String(input).replace(/[,\s]/g, '');
  if (!s) return null;
  if (/^\d+$/.test(s)) return Number(s);

  let total = 0; // 억/만 단위로 확정된 값
  let section = 0; // 만 미만 구간 누적값
  let current = 0; // 단위를 기다리는 값
  let sawAny = false;

  for (let i = 0; i < s.length; i += 1) {
    const ch = s[i];

    if (/\d/.test(ch)) {
      let num = '';
      while (i < s.length && /\d/.test(s[i])) {
        num += s[i];
        i += 1;
      }
      i -= 1;
      current = current === 0 ? Number(num) : current * 10 ** num.length + Number(num);
      sawAny = true;
      continue;
    }

    if (ch in HANGUL_DIGITS) {
      current = current * 10 + HANGUL_DIGITS[ch];
      sawAny = true;
      continue;
    }

    if (ch in SMALL_UNITS) {
      section += (current || 1) * SMALL_UNITS[ch];
      current = 0;
      sawAny = true;
      continue;
    }

    if (ch in BIG_UNITS) {
      const base = section + current || 1;
      total += base * BIG_UNITS[ch];
      section = 0;
      current = 0;
      sawAny = true;
      continue;
    }

    return null; // 숫자 표현이 아닌 문자가 섞이면 실패로 본다
  }

  return sawAny ? total + section + current : null;
}

// 금액 표기에 쓰이는 문자. '일'은 "6일"(날짜)과 충돌하므로 일부러 제외한다.
const NUM_CHARS = '0-9,\\s이삼사오육칠팔구십백천만억';
const NUM_TOKEN = '(?:\\d[\\d,]*|[이삼사오육칠팔구])';

/** 금액을 추출한다. 실패하면 null. */
export function extractAmount(text) {
  const t = text.replace(/원정/g, '원');

  // 1) "…원"으로 끝나는 표현이 가장 신뢰도가 높다.
  const withWon = [...t.matchAll(new RegExp(`([${NUM_CHARS}]+?)\\s*원`, 'g'))];
  for (let i = withWon.length - 1; i >= 0; i -= 1) {
    const value = koreanNumberToInt(withWon[i][1]);
    if (value) return { amount: value, match: withWon[i][0] };
  }

  // 2) "원" 없이 단위만 붙은 표현. "3만2천", "십오만"
  const unitRe = new RegExp(
    `(?:${NUM_TOKEN}|십)\\s*(?:억|만)(?:\\s*${NUM_TOKEN}\\s*(?:천|백|십)?)?|${NUM_TOKEN}\\s*천`,
  );
  const withUnit = t.match(unitRe);
  if (withUnit) {
    const value = koreanNumberToInt(withUnit[0]);
    if (value) return { amount: value, match: withUnit[0].trim() };
  }

  // 3) 단위가 없는 순수 숫자. 단위 명사(명/일/개…)가 뒤따르면 금액이 아니다.
  const plain = [...t.matchAll(/(\d[\d,]{2,})(?!\s*(?:명|인|일|월|년|시|분|초|개|층|번|%|퍼센트|호))/g)];
  for (const m of plain) {
    const value = koreanNumberToInt(m[1]);
    if (value) return { amount: value, match: m[1] };
  }

  return null;
}

function toISODate(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function addDays(date, days) {
  const next = new Date(date.getTime());
  next.setDate(next.getDate() + days);
  return next;
}

/**
 * 날짜를 추출한다. 표현이 없으면 오늘(now)로 자동 설정한다.
 * 반환: { date: 'YYYY-MM-DD', match: string|null, explicit: boolean }
 */
export function extractDate(text, now = new Date()) {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const t = text.replace(/\s+/g, ' ');

  const relative = [
    { re: /그저께|그제|엊그제/, days: -2 },
    { re: /어제|어저께/, days: -1 },
    { re: /오늘|금일/, days: 0 },
    { re: /내일/, days: 1 },
  ];
  for (const { re, days } of relative) {
    const m = t.match(re);
    if (m) return { date: toISODate(addDays(today, days)), match: m[0], explicit: true };
  }

  // "지난주 금요일", "저번주 화요일", "이번주 월요일", "금요일"
  const weekday = t.match(/(지난\s?주|저번\s?주|이번\s?주)?\s*([월화수목금토일]요일)/);
  if (weekday) {
    const target = WEEKDAYS[weekday[2]];
    const mondayIndex = (day) => (day + 6) % 7; // 월요일 시작 주차 기준
    let diff = (today.getDay() - target + 7) % 7;
    if (diff === 0) diff = 7; // 오늘과 같은 요일이면 지난 주 그 요일
    if (weekday[1] && /지난|저번/.test(weekday[1]) && mondayIndex(target) <= mondayIndex(today.getDay())) {
      diff += 7; // 이번 주에 이미 지나간 요일이면 한 주 더 뒤로
    }
    const candidate = addDays(today, -diff);
    return { date: toISODate(candidate), match: weekday[0].trim(), explicit: true };
  }

  // "3월 5일", "3/5", "3.5" (단, "3.5만원" 같은 금액은 제외)
  const md = t.match(/(\d{1,2})\s*[월/.\-]\s*(\d{1,2})\s*일?(?!\s*[만천억원])/);
  if (md) {
    const month = Number(md[1]);
    const day = Number(md[2]);
    if (month >= 1 && month <= 12 && day >= 1 && day <= 31) {
      let candidate = new Date(today.getFullYear(), month - 1, day);
      if (candidate.getTime() - today.getTime() > 45 * 86400000) {
        candidate = new Date(today.getFullYear() - 1, month - 1, day);
      }
      return { date: toISODate(candidate), match: md[0].trim(), explicit: true };
    }
  }

  // "12일" — 이번 달 기준, 미래면 지난달로 본다.
  const dayOnly = t.match(/(?:^|\s)(\d{1,2})\s*일(?!\s*간)/);
  if (dayOnly) {
    const day = Number(dayOnly[1]);
    if (day >= 1 && day <= 31) {
      let candidate = new Date(today.getFullYear(), today.getMonth(), day);
      if (candidate > today) candidate = new Date(today.getFullYear(), today.getMonth() - 1, day);
      return { date: toISODate(candidate), match: dayOnly[0].trim(), explicit: true };
    }
  }

  return { date: toISODate(today), match: null, explicit: false };
}

const TIME_WORDS = /^(오늘|어제|그제|그저께|엊그제|내일|금일|아침|점심|중식|저녁|석식|조식|오전|오후|[월화수목금토일]요일)$/;
const PARTICLE_TAIL = /(으로|로|에게|한테|와|과|이랑|랑|하고|은|는|이|가|을|를|도|에|의|건)$/;

/** "미팅으로 스타벅스에서" 처럼 앞에 붙은 수식어를 떼어낸다. */
function dropLeadingNonMerchantWord(phrase) {
  const words = phrase.split(/\s+/);
  if (words.length < 2) return phrase;
  const [first, ...rest] = words;
  if (TIME_WORDS.test(first) || PARTICLE_TAIL.test(first)) return rest.join(' ');
  return phrase;
}

/** 사용처(가맹점)를 추출한다. */
export function extractMerchant(text) {
  // "상호는 X", "가맹점 X", "X 에서"
  const labeled = text.match(
    /(?:상호|가맹점|사용처|업체)(?:\s*(?:는|은|이|가|:)\s+|\s+)([가-힣A-Za-z0-9&'".\-]{2,20})/,
  );
  if (labeled) return labeled[1].trim();

  const at = [...text.matchAll(/([가-힣A-Za-z0-9&'".\-]+(?:\s[가-힣A-Za-z0-9&'".\-]+)?)\s*에서/g)];
  if (at.length) {
    const cleaned = dropLeadingNonMerchantWord(at[0][1].trim());
    if (cleaned.length >= 2) return cleaned;
  }

  const lower = text.toLowerCase();
  for (const name of KNOWN_MERCHANTS) {
    if (lower.includes(name.toLowerCase())) return name;
  }

  // "○○점", "○○식당" 같은 상호형 명사
  const shop = text.match(/([가-힣A-Za-z0-9]{2,10}(?:식당|카페|마트|편의점|주유소|호텔|서점|약국|치킨|피자))/);
  if (shop) return shop[1];

  return '';
}

/** 계정과목을 추정한다. */
export function extractCategory(text) {
  const lower = text.toLowerCase();
  let best = { name: '기타', score: 0 };

  for (const rule of CATEGORY_RULES) {
    let score = 0;
    for (const kw of rule.keywords) {
      if (lower.includes(kw.toLowerCase())) score += rule.weight;
    }
    if (score > best.score) best = { name: rule.name, score };
  }

  return best.name;
}

/** 인원수를 추출한다. */
export function extractHeadcount(text) {
  const digit = text.match(/(\d{1,3})\s*(?:명|인)(?!\s*분의)/);
  if (digit) return Number(digit[1]);

  const native = text.match(/(혼자|한|두|세|네|다섯|여섯|일곱|여덟|아홉|열)\s*(?:명|사람|분)/);
  if (native) return NATIVE_COUNTS[native[1]] ?? null;

  return null;
}

const NOISE_WORDS = [
  '법인카드', '법인 카드', '카드로', '카드', '결제', '결재', '썼어', '썼습니다', '사용', '했어', '했습니다',
  '입력', '등록', '해줘', '해주세요', '이야', '이에요', '예요', '입니다', '건으로', '으로', '에서',
];

/** 사용목적(적요)을 만든다. 금액·날짜·인원 표현을 걷어낸 나머지 문장. */
export function extractPurpose(text, { amountMatch, dateMatch, merchant } = {}) {
  const explicit = text.match(/(?:목적|용도|사유|적요)\s*(?:는|은|이|가)?\s*([^,.]{2,40})/);
  if (explicit) return explicit[1].trim();

  let rest = text;
  if (amountMatch) rest = rest.replace(amountMatch, ' ');
  if (dateMatch) rest = rest.replace(dateMatch, ' ');
  if (merchant) rest = rest.split(merchant).join(' ');

  rest = rest
    .replace(/\d{1,3}\s*(?:명|인)/g, ' ')
    .replace(/원(?:정)?/g, ' ');

  for (const word of NOISE_WORDS) {
    rest = rest.split(word).join(' ');
  }

  rest = rest.replace(/[,.]/g, ' ').replace(/\s+/g, ' ').trim();

  // "…건" 으로 끝나면 그대로 살린다.
  const asItem = rest.match(/(.{2,30}?)\s*건$/);
  if (asItem) return `${asItem[1].trim()} 건`;

  return rest;
}

/**
 * 문장 하나를 지출 항목으로 파싱한다.
 * @param {string} text 음성 인식 결과 또는 직접 입력한 문장
 * @param {{ now?: Date }} [options]
 */
export function parseExpense(text, options = {}) {
  const now = options.now ?? new Date();
  const raw = String(text ?? '').trim();

  const amountInfo = extractAmount(raw);
  const dateInfo = extractDate(raw, now);
  const merchant = extractMerchant(raw);
  const category = extractCategory(raw);
  const headcount = extractHeadcount(raw);
  const purpose = extractPurpose(raw, {
    amountMatch: amountInfo?.match,
    dateMatch: dateInfo.match,
    merchant,
  });

  const filled = [amountInfo, merchant, purpose, category !== '기타'].filter(Boolean).length;

  return {
    raw,
    date: dateInfo.date,
    dateExplicit: dateInfo.explicit,
    merchant,
    amount: amountInfo ? amountInfo.amount : null,
    category,
    headcount,
    purpose,
    confidence: filled / 4,
  };
}

/** 한 번의 발화에 여러 건이 섞여 있을 때 문장 단위로 나눈다. */
export function splitUtterances(text) {
  return String(text ?? '')
    .split(/(?:[.!?\n]|\s그리고\s|\s또\s|\s다음\s?건\s)/)
    .map((s) => s.trim())
    .filter((s) => s.length > 1);
}

export function formatCurrency(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return '';
  return `${Number(value).toLocaleString('ko-KR')}원`;
}
