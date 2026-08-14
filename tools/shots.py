"""목업의 화면 블록을 표식으로 찾아 PNG로 뽑고 여백을 잘라낸다."""
import io, re, subprocess, os
from PIL import Image, ImageChops, ImageOps

SRC = '/home/user/chacha6377/docs/mockups/insurance-ai.html'
OUT = os.path.dirname(os.path.abspath(__file__))
s = io.open(SRC, encoding='utf-8').read()
head = s[:s.index('<div class="wrap">')]

def block_at(marker: str) -> str:
    """표식을 품은 .app 블록을 통째로 잘라낸다."""
    k = s.index(marker)
    i = s.rindex('<div class="app">', 0, k)
    depth, j = 0, i
    while True:
        o, c = s.find('<div', j + 1), s.find('</div>', j + 1)
        if c == -1:
            raise ValueError(marker)
        if o != -1 and o < c:
            depth += 1; j = o
        else:
            if depth == 0:
                return s[i:c + 6]
            depth -= 1; j = c

def trim(path):
    """그려진 영역만 남긴다. 캔버스 여백(검정)까지 물면 이미지에 검은 띠가 생긴다."""
    im = Image.open(path).convert('RGB')
    bg = Image.new('RGB', im.size, im.getpixel((im.width - 3, im.height - 3)))
    box = ImageChops.difference(im, bg).getbbox()
    if box:
        im = im.crop((0, 0, box[2], box[3]))
        im = ImageOps.expand(im, border=10, fill=(255, 255, 255))
        im.save(path)
    return Image.open(path).size

SHOTS = [
    ('entry',    '고객 폴더'),
    ('branch',   '가입한 상품 기준으로 확인할까요?'),
    ('scope',    '검색해서 고릅니다'),
    ('register', 'My Data 가져오기'),
    ('coverage', '보장맵</span> 계약 2건'),
    ('ask',      '음주운전 사고인데 보험금 나오나요?'),
]
# 슬라이드에서 글자가 읽히려면 사이드바를 빼고 본문만 크게 실어야 한다.
MAIN_ONLY = '<style>.side{display:none!important}.app{grid-template-columns:1fr!important}</style>'

for name, marker in SHOTS:
    body = block_at(marker)
    for suffix, extra, width in (('', '', 1180), ('_main', MAIN_ONLY, 950)):
        frag = (head + extra + '<div class="wrap" style="padding:0;max-width:none;">'
                + body + '</div></body></html>')
        fp = f'{OUT}/app_{name}{suffix}.html'
        io.open(fp, 'w', encoding='utf-8').write(frag)
        subprocess.run(['/opt/pw-browsers/chromium', '--headless', '--disable-gpu', '--no-sandbox',
                        '--hide-scrollbars', '--force-device-scale-factor=2',
                        f'--window-size={width},1100',
                        f'--screenshot={OUT}/app_{name}{suffix}.png', f'file://{fp}'],
                       capture_output=True)
        print(f'{name+suffix:16s}', trim(f'{OUT}/app_{name}{suffix}.png'))

# ── 가로 크롭 ──────────────────────────────────────────
# 슬라이드 이미지 상자는 12.1 × 4.9인치, 즉 가로:세로 2.47이다.
# 화면 전체를 넣으면 높이에 걸려 글자가 작아지므로, 각 화면에서 결정적인
# 구간만 그 비율로 잘라 슬라이드 폭을 전부 쓰게 한다.
TARGET = 2.47
STARTS = {          # 어디서부터 자를지 — 전체 높이 대비
    'branch':   0.10,   # 담보 목록 + 분기 카드
    'scope':    0.14,   # 상품 검색 결과 + 가입 시점 + 스코프 바
    'ask':      0.42,   # 판정 카드 + 근거 조항
    'entry':    0.02,   # 고객 폴더 목록
    'register': 0.03,   # 등록 경로 세 갈래
    'coverage': 0.05,   # 계약별 담보
}

for name, a in STARTS.items():
    src = Image.open(f'{OUT}/app_{name}_main.png').convert('RGB')
    need = int(src.width / TARGET)
    top = min(int(src.height * a), max(0, src.height - need))
    src.crop((0, top, src.width, min(src.height, top + need))).save(f'{OUT}/app_{name}_wide.png')
    im = Image.open(f'{OUT}/app_{name}_wide.png')
    print(f'{name:9s} {im.size}  aspect {im.width/im.height:.2f}')
