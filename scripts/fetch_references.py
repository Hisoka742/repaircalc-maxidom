"""Download manufacturer technical data sheets and print their consumption sections.

    PYTHONPATH=<dir with pypdf> uv run python scripts/fetch_references.py [--out data/references]

The sheets are public documents of the manufacturers (URLs below). They are kept in
`data/references` (not committed) and read with pypdf; `tests/golden/golden_manufacturer.yaml`
quotes the specific figure, the sheet URL and the inputs of every case taken from them, so a
reviewer can open the same page and compare. Requires `pypdf` (`pip install pypdf`).
"""
import argparse
import re
import sys
import time
from pathlib import Path

import httpx

SHEETS = {
    "ceresit-cm11-plus": "https://datasheets.tdx.henkel.com/CERESIT-CM-11-ru_KZ.pdf",
    "ceresit-ce40": "https://datasheets.tdx.henkel.com/CERESIT-CE-40-ru_KZ.pdf",
    "ceresit-cn68": "https://datasheets.tdx.henkel.com/CERESIT-CN-68-ru_BY.pdf",
    "ceresit-cr65": "https://datasheets.tdx.henkel.com/CERESIT-CR-65-ru_KZ.pdf",
    "ceresit-cl51": "https://datasheets.tdx.henkel.com/CERESIT-CL-51-ru_KZ.pdf",
    "ceresit-ct17": "https://datasheets.tdx.henkel.com/CERESIT-CT-17-ru_KZ.pdf",
    "tikkurila-prof-euro-7": "https://tikkurila.com/sites/default/files/prof-euro-7-en-pds-tikkurila-1655905744.pdf",
    "knauf-rotband": "https://knauf.by/upload/iblock/dac/Knauf_IL_Rotband_07_06_19_preview_v4.pdf",
}
UA = "Mozilla/5.0 (compatible; MaxicalcResearchBot/0.1; contact: team@example.org)"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data/references")
    ap.add_argument("--only", nargs="*", default=None)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    try:
        from pypdf import PdfReader
    except ImportError:
        print("Нужен pypdf: pip install pypdf")
        return 2
    for name, url in SHEETS.items():
        if a.only and name not in a.only:
            continue
        f = out / f"{name}.pdf"
        if not f.exists():
            try:
                r = httpx.get(url, headers={"User-Agent": UA}, timeout=60, follow_redirects=True)
                r.raise_for_status()
                f.write_bytes(r.content)
            except httpx.HTTPError as e:
                print(f"== {name}: не скачан ({e})")
                continue
            time.sleep(2)
        text = "\n".join((p.extract_text() or "") for p in PdfReader(f).pages)
        text = re.sub(r"[ \t]+", " ", text)
        print(f"== {name} ({len(text)} символов) {url}")
        for m in re.finditer(r"(?i)(расход|coverage|consumption)", text):
            print("   ", text[max(0, m.start() - 60): m.start() + 500].replace("\n", " | "))
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())
