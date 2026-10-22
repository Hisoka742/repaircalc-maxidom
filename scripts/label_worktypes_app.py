"""Labeling app for the work-type gold set (target: <= 1.5 h per person for ~258 rows).

    pip install streamlit
    streamlit run scripts/label_worktypes_app.py -- eval/gold/worktype_annotator1.csv

* the sheet is edited in place and saved after EVERY click (atomic write); close the tab any time;
* definitions of all work types stay on screen, grouped by stage, each with a code like `3b`;
* keyboard: type codes into "Быстрый ввод кодов" (`1c 3b`, Enter) or press stage digit + letter (`3b`); `Enter` accepts the system's
  suggestion (only on rows that have one; the 60 shared rows have none), `0` = nothing fits
  ("none"), `→`/`n` next row, `←`/`p` previous, `u` mark unsure, `Esc` cancels a half-typed code;
* the group (stratified / ambiguous / negative) and the dev/test split are NOT shown;
* time spent per row is logged next to the sheet (`*.timing.csv`) so the real hours are known.
"""
import argparse
import csv
import sys
import time
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from make_taxonomy_doc import DEFS  # noqa: E402

DESC_LIMIT = 700
LETTERS = "abcdefghijklmnop"
EXTRA = ["unsure", "comment"]


def taxonomy() -> tuple[list[tuple[str, str, list[tuple[str, str, str, str]]]], dict[str, str]]:
    """[(stage code, stage name, [(code, id, name, definition)])] and id -> code."""
    tax = yaml.safe_load((ROOT / "src/maxicalc/knowledge/taxonomy.yaml").read_text(encoding="utf-8"))
    stages = list(tax["stages"])
    out = []
    codes: dict[str, str] = {}
    for si, stage in enumerate(stages, start=1):
        items = []
        members = [(wid, w) for wid, w in tax["work_types"].items() if w["stage"] == stage]
        for li, (wid, w) in enumerate(members):
            code = f"{si}{LETTERS[li]}"
            codes[wid] = code
            items.append((code, wid, w["ru"], DEFS[wid][0]))
        out.append((str(si), tax["stages"][stage], items))
    return out, codes


def load(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f, delimiter=";")
        fields = list(r.fieldnames or [])
        rows = list(r)
    for c in EXTRA:
        if c not in fields:
            fields.append(c)
            for row in rows:
                row[c] = ""
    return fields, rows


def save(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter=";")
        w.writeheader()
        w.writerows(rows)
    tmp.replace(path)


def selected(row: dict[str, str]) -> set[str]:
    v = row["work_types"].strip()
    return set() if v in ("", "none", "=") else {x for x in v.split(";") if x}


HOTKEYS = """
<script>
const doc = window.parent.document;
if (window.parent.__lbl) doc.removeEventListener('keydown', window.parent.__lbl, true);
let buf = '';
function clickByText(txt) {
  const els = [...doc.querySelectorAll('button')].filter(b => b.innerText.includes(txt));
  if (els.length) els[0].click();
}
function toggleCode(code) {
  const labels = [...doc.querySelectorAll('label')].filter(l => l.innerText.trim().startsWith('[' + code + ']'));
  if (labels.length) labels[0].click();
}
window.parent.__lbl = function (e) {
  const t = e.target.tagName;
  if (t === 'INPUT' && e.target.type === 'text' || t === 'TEXTAREA') return;
  const k = e.key;
  if (k === 'ArrowRight' || k === 'n') { clickByText('Дальше'); e.preventDefault(); buf = ''; return; }
  if (k === 'ArrowLeft' || k === 'p') { clickByText('Назад'); e.preventDefault(); buf = ''; return; }
  if (k === 'Enter') { clickByText('Принять подсказку'); e.preventDefault(); buf = ''; return; }
  if (k === '0') { clickByText('Ничего не подходит'); e.preventDefault(); buf = ''; return; }
  if (k === 'u') { clickByText('Не уверен'); e.preventDefault(); buf = ''; return; }
  if (k === 'Escape') { buf = ''; return; }
  if (/^[1-9]$/.test(k)) { buf = k; return; }
  if (buf && /^[a-p]$/.test(k)) { toggleCode(buf + k); buf = ''; e.preventDefault(); }
};
doc.addEventListener('keydown', window.parent.__lbl, true);
</script>
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    a = ap.parse_args(sys.argv[1:])
    path = Path(a.csv)
    st.set_page_config(page_title="Разметка видов работ", layout="wide")
    if "fields" not in st.session_state:
        st.session_state.fields, st.session_state.rows = load(path)
        first = next((k for k, r in enumerate(st.session_state.rows)
                      if not r["work_types"].strip()), 0)
        st.session_state.i = first
        st.session_state.t0 = time.time()
    rows, fields = st.session_state.rows, st.session_state.fields
    i = st.session_state.i
    stages, _codes = taxonomy()
    done = sum(1 for r in rows if r["work_types"].strip())

    def commit() -> None:
        save(path, fields, rows)

    def goto(k: int) -> None:
        spent = time.time() - st.session_state.t0
        with path.with_suffix(".timing.csv").open("a", encoding="utf-8") as f:
            f.write(f"{rows[st.session_state.i]['sku']};{spent:.1f}\n")
        st.session_state.i = max(0, min(len(rows) - 1, k))
        st.session_state.t0 = time.time()

    row = rows[i]
    sel = selected(row)

    def set_sel(new: set[str]) -> None:
        row["work_types"] = ";".join(sorted(new)) if new else "none"
        commit()

    def toggle(wid: str) -> None:
        cur = selected(row)
        cur.symmetric_difference_update({wid})
        if cur:
            set_sel(cur)
        else:
            row["work_types"] = ""
            commit()

    components.html(HOTKEYS, height=0)
    st.progress(done / len(rows), text=f"Размечено {done} из {len(rows)}; строка {i + 1}")
    left, right = st.columns([5, 7])
    with left:
        st.subheader(row["name"])
        st.caption(row["category"])
        if row["description"]:
            st.write(row["description"][:DESC_LIMIT])
        with st.expander("Параметры карточки", expanded=True):
            st.write(row["params"])
        sugg = row["suggested"].strip()
        if sugg and sugg != "=":
            st.info("Подсказка системы: " + ("нет работ" if sugg == "none" else sugg.replace(";", ", ")))
        elif row.get("overlap") == "1":
            st.caption("Общая строка: подсказки нет, решайте сами.")
        c1, c2, c3 = st.columns(3)
        if sugg:
            c1.button("Принять подсказку (Enter)", on_click=lambda: (
                row.__setitem__("work_types", sugg), commit()))
        c2.button("Ничего не подходит (0)", on_click=lambda: (
            row.__setitem__("work_types", "none"), commit()))
        c3.button("Не уверен (u)", on_click=lambda: (
            row.__setitem__("unsure", "1"), commit()))
        ckey = f"cm_{row['sku']}"

        def set_comment() -> None:
            row["comment"] = st.session_state.get(ckey, "")
            commit()

        st.text_input("Комментарий (необязательно)", value=row.get("comment", ""), key=ckey,
                      on_change=set_comment)
        qkey = f"q_{row['sku']}"

        def quick() -> None:
            """Type codes separated by spaces (`1c 3b 5a`), Enter: toggles them; `0` = none."""
            tokens = st.session_state.get(qkey, "").replace(",", " ").split()
            by_code = {c: w for _, _, items in stages for c, w, _, _ in items}
            cur = selected(row)
            for t in tokens:
                if t == "0":
                    cur = set()
                    row["work_types"] = "none"
                elif t in by_code:
                    cur.symmetric_difference_update({by_code[t]})
            if cur:
                set_sel(cur)
            elif row["work_types"] != "none":
                row["work_types"] = ""
            commit()
            st.session_state[qkey] = ""

        st.text_input("Быстрый ввод кодов (например `1c 3b`, Enter; `0` — ничего)", key=qkey,
                      on_change=quick)
        n1, n2 = st.columns(2)
        n1.button("← Назад", on_click=goto, args=(i - 1,))
        n2.button("Дальше → (n)", on_click=goto, args=(i + 1,), type="primary")
        st.caption("Текущий выбор: " + (", ".join(sorted(sel)) if sel else
                                        ("нет работ" if row["work_types"] == "none" else "—")))
    with right:
        st.caption("Код: цифра этапа + буква, например `3b`. Определения всегда перед глазами.")
        for scode, sname, items in stages:
            with st.expander(f"{scode}. {sname}", expanded=True):
                for code, wid, name, definition in items:
                    st.checkbox(f"[{code}] {name} — {definition}", value=wid in sel,
                                key=f"cb_{row['sku']}_{wid}_{abs(hash(row['work_types']))}",
                                on_change=toggle, args=(wid,))


if __name__ == "__main__":
    main()
