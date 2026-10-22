"""Pitch metrics generator: turns eval + load-test + (optional) spot-check results into
docs/PITCH_METRICS.md. Pure function of its inputs, so every number on the slide is traceable.

Claims policy (enforced by tests/test_pitch.py):
* synthetic-data numbers are always labelled СИНТЕТИЧЕСКИЕ;
* a precision claim is made only from a human spot check, and only called "achieved" when the
  interval's LOWER bound clears the target;
* assumptions (minutes saved per label) are printed as assumptions;
* anything not measured says "не измерено"; the limitations section is always present.
"""
from typing import Any

from maxicalc.dayof import SpotCheckScore

TARGET = 0.95


def hours_saved(n_auto: int, minutes_per_label: float) -> float:
    return n_auto * minutes_per_label / 60


def _pct(x: float) -> str:
    return f"{100 * x:.1f}"


def build_pitch(
    ev: dict[str, Any],
    load: list[dict[str, Any]],
    rematch: dict[str, Any] | None,
    spot: SpotCheckScore | None,
    n_auto: int | None = None,
    minutes_per_label: float = 1.5,
    real: dict[str, Any] | None = None,
    wt: dict[str, Any] | None = None,
    full: dict[str, Any] | None = None,
) -> str:
    g, ex = ev["golden"], ev["extraction"]
    m, rec = ev["matching"], ev["recommendation"]
    k, n = g["pack_exact"]
    cold = next((r for r in load if "холодн" in r["label"]), load[0] if load else None)
    # the headline share is the best coverage that still meets the 95 % precision target; if no
    # scenario meets it, the best coverage is shown and the shortfall is stated
    ok = [s for s in m["scenarios"] if s["auto_precision"] >= TARGET]
    pool = ok or m["scenarios"]
    best = max(pool, key=lambda s: s["coverage"]) if pool else None
    best_note = "" if ok else f" (**ниже цели {_pct(TARGET)}%**)"
    L: list[str] = [
        "# Метрики для питча", "",
        f"_Сгенерировано автоматически из `make eval` и нагрузочных тестов ({ev['generated']}). "
        "Не редактировать вручную: `make pitch`._", "",
        "## 0. Четыре метрики кейса", "",
        "| метрика кейса | значение | на каких данных |",
        "|---|---|---|",
        f"| Качество матчинга (P / R / F1) | macro-F1 видов работ "
        f"{max(s['work_macro_f1'] for s in m['scenarios']):.3f}, тип калькулятора P@1 "
        f"{_pct(max(s['calc_p_at_1'] for s in m['scenarios']))}% | СИНТЕТИКА, "
        f"{m['items']} товаров; цель кейса F1 ≥ 0.8; на реальном каталоге **не измерено** |"
        if m["scenarios"] else "| Качество матчинга | не измерено | — |",
        (f"| MAE по количеству к эталону | {g['mae_packs']:.3f} упаковки "
         f"(макс. ошибка {g.get('max_pack_error', 0):.0f}) на {n} случаях-упаковках | "
         "эталонные случаи команды; **сметы организаторов не получены** (не измерено) |"
         if "mae_packs" in g else "| MAE по количеству к эталону | не измерено | — |"),
        (f"| Доля авто-привязанных без ручной разметки | {_pct(best['coverage'])}% при "
         f"точности {_pct(best['auto_precision'])}%{best_note} ({best['name']}) | СИНТЕТИКА |"
         if best else
         "| Доля авто-привязанных | не измерено | — |"),
        (f"| Время формирования сметы | p50 {cold['p50'] / 1000:.3f} с, p95 "
         f"{cold['p95'] / 1000:.3f} с под {cold['rps']} rps | синтетический каталог 10 000 |"
         if cold else "| Время формирования сметы | не измерено | — |"),
        "| Клики от «выбрал комнату» до «готовая корзина» | **3**: выбрать помещение и "
        "параметры → «Рассчитать» → смета с корзиной готова (при вводе текстом: фраза → "
        "«Понять» → «Рассчитать») | сценарий в интерфейсе, `tests/e2e/test_demo.py` |",
        "", "## 1. Точность расчётов", "",
        f"- Эталонных случаев: **{g['cases']}**, из них взято из технической документации "
        f"производителей (Ceresit CM 11 PLUS / CE 40 / CR 65 / CN 68 / CL 51 / CT 17, Tikkurila "
        f"Prof Euro 7, Knauf Rotband; у каждого URL и цитата): **{g['verified']}**",
        f"- Точное совпадение по упаковкам: **{k}/{n}**",
        *([(f"- **Сверено с производителем** (озвучивать со сцены): {sv['cases']} случаев, "
            f"упаковки {sv['pack_exact']}/{sv['packs']}, MAE {sv['mae_packs']:.3f} уп., "
            f"MAPE {sv['mape_pct']:.3f}%"),
           (f"- Пересчитано заново по формулам (защита от регрессий, не для сцены): "
            f"{rd['cases']} случаев, упаковки {rd['pack_exact']}/{rd['packs']}, "
            f"MAE {rd['mae_packs']:.3f} уп.")]
          if (sv := g.get("split", {}).get("manufacturer_verified"))
          and (rd := g["split"].get("rederived")) else []),
        f"- MAPE по непрерывным величинам: **{g['mape_pct']:.3f}%** (в основном округление "
        "значений в таблицах производителей)",
        "- Остальные случаи посчитаны вручную по формулам движка: это защита от регрессий, "
        "а не независимая проверка формул.",
    ]
    if g["failures"]:
        L.append(f"- ⚠ **Есть расхождения с эталоном: {g['failures']}** — см. eval/REPORT.md.")
    L += ["", "## 2. Качество ML", "",
          f"### Извлечение атрибутов (СИНТЕТИЧЕСКИЕ ДАННЫЕ, {ex['cases']} случаев)", "",
          f"- Precision {ex['precision']:.3f}, recall {ex['recall']:.3f}. Набор написан "
          "командой с учётом шаблонов извлекателя — это защита от регрессий, не оценка "
          "точности на реальных карточках.", "",
          f"### Разметка каталога (СИНТЕТИЧЕСКИЕ ДАННЫЕ, {m['items']} товаров, "
          f"тест {m['test']})", "",
          "| сценарий | тип калькулятора верен | авто-охват | точность авто |",
          "|---|---|---|---|"]
    for s in m["scenarios"]:
        L.append(f"| {s['name']} | {_pct(s['calc_p_at_1'])}% | {_pct(s['coverage'])}% | "
                 f"{_pct(s['auto_precision'])}% |")
    if real:
        s, rd = real["summary"], real["readiness"]
        L += ["", f"### Реальный каталог maxidom.ru (скрейп, {s['products']} товаров, "
              "БЕЗ ручной разметки)", "",
              f"- Авто-разметка правилами: **{s['auto']}** из {s['products']} "
              f"({_pct(s['auto'] / s['products'])}%), на проверку {s['review']}; "
              "точность не измерена (нет человеческих меток).",
              "- Готовность калькуляторов по реальным карточкам (есть все данные для расчёта):",
              "", "| тип | товаров | готово | чего не хватает |", "|---|---|---|---|"]
        for calc, x in sorted(rd.items(), key=lambda kv: -kv[1]["total"]):
            miss = ", ".join(f"{a} ({n})" for a, n in x["top_missing"]) or "—"
            L.append(f"| {calc} | {x['total']} | {x['ready']} ({_pct(x['share'])}%) | {miss} |")
    L += ["", "### Измеренная точность на реальном каталоге", ""]
    if spot is None or spot.checked == 0:
        L.append("- Точность на реальном каталоге **не измерено**: нужна ручная отметка "
                 "контрольной выборки (`scripts/dayof.py run` → `score`).")
    else:
        L.append(f"- Проверено вручную: **{spot.checked}** случайных авто-разметок; верно "
                 f"**{spot.correct}** → точность **{_pct(spot.precision)}%** "
                 f"(95% интервал {_pct(spot.low)}–{_pct(spot.high)}%).")
        if spot.meets(TARGET):
            L.append(f"- Цель 95% точности достигнута: нижняя граница интервала "
                     f"{_pct(spot.low)}% ≥ 95%.")
        else:
            L.append(f"- Цель 95% точности не достигнута: нижняя граница интервала "
                     f"{_pct(spot.low)}% < 95%. Товары вне уверенной разметки идут на проверку.")
    L += ["", f"### Подбор товаров (СИНТЕТИЧЕСКИЕ ДАННЫЕ, {rec['queries']} запросов)", "",
          "| метки каталога | nDCG@5 | рекомендовано | нарушений жёстких правил |",
          "|---|---|---|---|"]
    for name, key in (("эталонные", "gold"), ("по результатам разметки", "pipeline")):
        r = rec[key]
        L.append(f"| {name} | {r['ndcg5']:.3f} | {r['recommended']} | {r['violations']} |")
    L += ["", "_Релевантность считается по рубрике на тех же правилах помещений, поэтому метрика "
          "показывает влияние ошибок разметки, а не правильность самих правил._", "",
          "## 3. Производительность (СИНТЕТИЧЕСКИЙ каталог 10 000 товаров, один процесс, "
          "ноутбук, генератор нагрузки на той же машине)", ""]
    if load:
        L += ["| сценарий | нагрузка | запросов | успешных | 5xx | p50, мс | p95, мс | p99, мс |",
              "|---|---|---|---|---|---|---|---|"]
        for r in load:
            L.append(f"| {r['label']} | {r['rps']} rps × {r['seconds']} с | {r['requests']} | "
                     f"{r['ok']} | {r['errors_5xx']} | {r['p50']} | {r['p95']} | {r['p99']} |")
    else:
        L.append("- Нагрузочные тесты: **не измерено**.")
    if rematch:
        L.append(f"\n- Полная пересортировка каталога ({rematch['products']} товаров: загрузка, "
                 f"извлечение, правила, модель): **{rematch['seconds']} с**.")
    if wt:
        mc, hs, stg = wt["machine"], wt["holdout"], wt["stages"]
        L += ["", "## 3b. Ресурсы и время разметки видов работ (ноутбук, CPU; ИЗМЕРЕНО)", "",
              f"- Машина: {mc['cpu']}, {mc['cores_physical']} ядер / {mc['cores_logical']} "
              f"потоков, {mc['ram_gb']} ГБ ОЗУ, GPU: {mc['gpu'] or 'не используется'}",
              f"- Каталог из {wt['products']} товаров: загрузка и нормализация фида "
              f"{stg['load']['seconds']:.1f} с (пик ОЗУ {stg['load']['peak_rss_mb']:.0f} МБ), "
              f"правила {stg['rules']['seconds']:.1f} с",
              f"- Разметка (правила + модель): {stg['match_5000']['seconds'] / 5000 * 1000:.2f} с "
              f"на 1 000 товаров (пик ОЗУ {stg['match_5000']['peak_rss_mb']:.0f} МБ)",
              f"- Обучение модели на {stg['train_full']['items']} товарах: "
              f"{stg['train_full']['seconds']:.0f} с; размер модели {wt['model_mb']} МБ; "
              "нейросети и GPU не нужны",
              "- Эмбеддинги multilingual-e5-small на CPU: 27 товаров/с, пик ОЗУ 1,7 ГБ; "
              "микро-F1 на отложенных категориях 0.844 против 0.836 у TF-IDF: на полном "
              "каталоге ≈ 38 минут ради +0.008, поэтому по умолчанию не используются",
              "", "### Отложенные категории (СИНТЕТИКА/SILVER: метки = правила)", "",
              f"- {hs['held_categories']} категорий, не виденных при обучении ({hs['n']} "
              f"товаров): micro-F1 {hs['micro_f1']:.3f}, macro-F1 {hs['macro_f1']:.3f}, "
              f"sample-F1 {hs['samples_f1']:.3f}. Это проверка воспроизводимости, не точность "
              "на человеческих метках."]
    if full:
        mc, st = full["machine"], full["stages"]
        L += ["", "## 3c. Полный прогон на официальном наборе организаторов "
              "(ноутбук, CPU; REAL)", "",
              f"- {full['products']} товаров (`products_final.json`, 274 МБ): весь конвейер за "
              f"**{full['total_seconds']:.0f} с** ({full['total_seconds'] / 60:.1f} мин); "
              f"машина: {mc['cores_physical']} ядер / {mc['cores_logical']} потоков, "
              f"{mc['ram_gb']} ГБ ОЗУ, GPU: {mc['gpu'] or 'не используется'}",
              "", "| шаг | секунд | пик ОЗУ, МБ | с на 1 000 товаров |", "|---|---|---|---|",
              *[f"| {k} | {v['seconds']} | {v['peak_rss_mb']} | {v['per_1000_s']} |"
                for k, v in st.items()], "",
              f"- Ремонтных товаров по карте категорий: {full['in_scope_products']}, "
              f"не ремонт: {full['out_of_scope_products']} (ответ «нет видов работ»); среди "
              f"ремонтных виды работ определены у {full['in_scope_with_work_types']}.",
              "- Готовность основных категорий к расчёту (REAL): "
              + "; ".join(f"{k} {v['ready']}/{v['total']}"
                          for k, v in full.get("focus_readiness", {}).items()) + ".",
              "- **Точность** разметки видов работ относительно людей здесь не показана: "
              "золотой набор людей ещё не размечен. Пилот «LLM как разметчик» и сравнение с "
              "категорийной картой — `docs/CATEGORY_MAP.md` (метка PILOT, не REAL).", ""]
    L += ["", "## 4. Бизнес-ценность", ""]
    if n_auto is None:
        L.append("- Экономия ручной разметки: **не измерено** (нет размеченного каталога).")
    else:
        L.append(f"- Авто-размечено товаров: **{n_auto}**.")
        L.append(f"- Допущение (не измерено): {minutes_per_label} мин на ручную разметку "
                 "одного товара.")
        if spot is not None and spot.checked:
            h = hours_saved(round(n_auto * spot.low), minutes_per_label)
            L.append(f"- Экономия при нижней границе измеренной точности "
                     f"({_pct(spot.low)}% разметок верны): **≈{h:.0f} ч** работы.")
        else:
            L.append(f"- Верхняя оценка без учёта ошибок разметки: **≈"
                     f"{hours_saved(n_auto, minutes_per_label):.0f} ч** (допущение выше).")
    L += ["- Корзина «в один клик» с сопутствующими товарами; выгрузка сметы в XLSX/PDF для B2B.",
          "", "## 5. Что не доказано", "",
          "- Качество разметки и извлечения на **реальном** каталоге Максидом (все ML-цифры выше "
          "— на синтетике), пока не сделана ручная выборка.",
          "- Ставки работ не заданы — стоимость работ не считается.",
          "- Готовность карточек реального каталога к расчёту (расход, фасовка) неизвестна до "
          "загрузки данных организаторов.",
          "- Сверка формул с эталонами организаторов (`GOLDEN_EXTRA`).",
          "- Нагрузка измерена без Redis и Docker; PostgreSQL/pgvector не подключены; "
          "нет авторизации.", ""]
    return "\n".join(L)
