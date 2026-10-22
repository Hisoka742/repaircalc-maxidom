"""Streamlit labeling app for the team (about 1 hour per person).

    pip install streamlit
    streamlit run scripts/label_app.py -- data/gold_todo.csv      # SKU -> calculator type
    streamlit run scripts/label_app.py -- data/rec_grading.csv    # query result -> grade 0-3

The CSV is edited in place (saved after every answer), so several people can each take a slice:
pass --from N --to M row indexes. Pre-filled predictions are shown, a human confirms or fixes.
"""
import argparse
import csv
import sys
from pathlib import Path

import streamlit as st

CALCS = ["none", "paint", "wallpaper", "tile", "tile_adhesive", "grout", "laminate", "drywall",
         "primer", "putty", "electrical", "plumbing", "waterproofing", "skirting"]


def load(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f, delimiter=";")
        return list(r.fieldnames or []), list(r)


def save(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter=";")
        w.writeheader()
        w.writerows(rows)
    tmp.replace(path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--from", dest="lo", type=int, default=0)
    ap.add_argument("--to", dest="hi", type=int, default=10**9)
    a = ap.parse_args(sys.argv[1:])
    path = Path(a.csv)
    fields, rows = load(path)
    key = "grade" if "grade" in fields else "verified_calc"
    idx = [i for i in range(len(rows)) if a.lo <= i < a.hi]
    todo = [i for i in idx if not rows[i].get(key, "").strip()]
    st.title("Разметка")
    st.progress(1 - len(todo) / max(1, len(idx)), text=f"Осталось {len(todo)} из {len(idx)}")
    if not todo:
        st.success("Всё размечено")
        return
    i = todo[0]
    r = rows[i]
    if key == "grade":
        st.subheader(f"Запрос: {r['room']} / {r['calc']} — место {r['rank']}")
        st.write(f"**{r['name']}**  ·  {r['price']} ₽  ·  SKU {r['sku']}")
        cols = st.columns(4)
        for g, label in enumerate(["0 не подходит", "1 приемлемо", "2 хорошо", "3 лучший выбор"]):
            if cols[g].button(label, key=f"g{g}"):
                rows[i]["grade"] = str(g)
                save(path, fields, rows)
                st.rerun()
    else:
        st.subheader(r["name"])
        st.write(f"Категория: {r['category']}  ·  SKU {r['sku']}  ·  предсказано: "
                 f"**{r['predicted_calc']}**")
        if st.button("Верно", key="ok"):
            rows[i]["verified_calc"] = r["predicted_calc"]
            save(path, fields, rows)
            st.rerun()
        choice = st.selectbox("Исправить на", CALCS)
        if st.button("Сохранить исправление", key="fix"):
            rows[i]["verified_calc"] = choice
            save(path, fields, rows)
            st.rerun()


main()
