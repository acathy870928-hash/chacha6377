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
    ('scope',    '세 건이 잡힙니다'),
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

# ── UI 전면 배치용 밴드 ──────────────────────────────
# 슬라이드에서 UI가 주인공이 되려면 화면이 폭 12.7인치를 다 써야 한다.
# 이미지 영역은 12.3 × 5.35인치(비율 2.3). 화면이 그보다 길면 잘라내는 대신
# 위 · 아래 여러 장으로 나눈다 — 내용을 버리지 않고 전부 크게 보여준다.
import math

BAND = 2.35
for name in ('branch', 'scope', 'ask', 'entry', 'register', 'coverage'):
    src = Image.open(f'{OUT}/app_{name}_main.png').convert('RGB')
    band_h = int(src.width / BAND)
    n = 1 if src.height <= band_h * 1.3 else math.ceil(src.height / band_h)
    for k in range(n):
        if n == 1:
            crop = src
        else:
            # 밴드 시작점을 고르게 분배해 이음매 없이 전체를 덮는다
            top = round(k * (src.height - band_h) / (n - 1))
            crop = src.crop((0, top, src.width, top + band_h))
        crop.save(f'{OUT}/app_{name}_p{k+1}.png')
    print(f'{name:9s} {src.height}px → {n}장')
