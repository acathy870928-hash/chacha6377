# chacha6377

Insurance AI 보험상품 운영 규칙 문서 저장소.

| 경로 | 설명 |
| --- | --- |
| `docs/insurance_ai_product_rules.md` | 운영 규칙 원본 (Markdown, source of truth) |
| `data/current_sales_products.csv` | 현재 판매 상품 데이터 (월 1회 정기 업데이트) |
| `scripts/build_pdf.py` | Markdown + CSV → PDF 생성 스크립트 |
| `build/` | 생성된 PDF 산출물 |

## PDF 생성

```
pip install reportlab
apt-get install -y fonts-nanum
python3 scripts/build_pdf.py
```
