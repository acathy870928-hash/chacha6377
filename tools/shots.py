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
for name, marker in SHOTS:
    frag = head + '<div class="wrap" style="padding:0;max-width:none;">' + block_at(marker) + '</div></body></html>'
    fp = f'{OUT}/app_{name}.html'
    io.open(fp, 'w', encoding='utf-8').write(frag)
    subprocess.run(['/opt/pw-browsers/chromium', '--headless', '--disable-gpu', '--no-sandbox',
                    '--hide-scrollbars', '--force-device-scale-factor=2',
                    '--window-size=1180,1100', f'--screenshot={OUT}/app_{name}.png', f'file://{fp}'],
                   capture_output=True)
    print(f'{name:9s}', trim(f'{OUT}/app_{name}.png'))
