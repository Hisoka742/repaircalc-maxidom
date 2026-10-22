"""The organisers' Yandex YML feed: fetch a dated snapshot, scope it, report on it.

    fetch_snapshot(url, dir)  -> dir/export_yandex_spb_<feed date>.xml.gz   (+ latest.xml.gz copy)
    is_repair(category_path)  -> bool   (knowledge/feed_scope.yaml)
    feed_report(products)     -> FeedReport (offers, repair share, parameter coverage per category)
"""
import gzip
import shutil
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

import httpx
import yaml

from maxicalc.catalog.adapters.yml_feed import feed_date
from maxicalc.catalog.schema import Product

FEED_URL = "https://fidsout.maxidom.ru/fids/export_yandex_spb.xml"
UA = "Mozilla/5.0 (compatible; MaxicalcResearchBot/0.1; contact: team@example.org)"
SCOPE_FILE = Path(__file__).resolve().parents[1] / "knowledge" / "feed_scope.yaml"
# keys of Product.characteristics that come from the feed envelope, not from <param>
NON_PARAM = {"Вес, кг", "Страна производства", "Артикул"}


def fetch_snapshot(url: str = FEED_URL, out_dir: Path = Path("data/feed"),
                   timeout_s: float = 1800.0) -> Path:
    """Download (streamed, ~95 MB), name by the feed's own date, gzip, refresh `latest.xml.gz`."""
    out_dir.mkdir(parents=True, exist_ok=True)
    part = out_dir / "download.part"
    with httpx.stream("GET", url, headers={"User-Agent": UA}, timeout=timeout_s,
                      follow_redirects=True) as r:
        r.raise_for_status()
        with part.open("wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
    date = feed_date(part) or time.strftime("%Y-%m-%d")
    final = out_dir / f"export_yandex_spb_{date}.xml.gz"
    with part.open("rb") as src, gzip.open(final, "wb", compresslevel=6) as dst:
        shutil.copyfileobj(src, dst)
    part.unlink()
    shutil.copyfile(final, out_dir / "latest.xml.gz")
    return final


@cache
def _scope() -> tuple[frozenset[str], dict[str, frozenset[str]], dict[str, frozenset[str]]]:
    raw = yaml.safe_load(SCOPE_FILE.read_text(encoding="utf-8"))
    return (frozenset(raw["repair_roots"]),
            {k: frozenset(v) for k, v in raw.get("exclude", {}).items()},
            {k: frozenset(v) for k, v in raw.get("repair_subcategories", {}).items()})


def is_repair(category_path: list[str]) -> bool:
    roots, exclude, include = _scope()
    if not category_path:
        return False
    root = category_path[0]
    sub = category_path[1] if len(category_path) > 1 else ""
    if root in roots:
        return sub not in exclude.get(root, frozenset())
    return sub in include.get(root, frozenset())


@dataclass
class CategoryCoverage:
    name: str
    offers: int = 0
    with_params: int = 0
    params_total: int = 0
    with_description: int = 0

    @property
    def param_share(self) -> float:
        return self.with_params / self.offers if self.offers else 0.0

    @property
    def mean_params(self) -> float:
        return self.params_total / self.offers if self.offers else 0.0


@dataclass
class FeedReport:
    offers: int = 0
    repair: int = 0
    in_stock: int = 0
    priced: int = 0
    seconds: float = 0.0
    feed_date: str | None = None
    by_category: dict[str, CategoryCoverage] = field(default_factory=dict)
    top_params: dict[str, list[tuple[str, int]]] = field(default_factory=dict)

    @property
    def repair_share(self) -> float:
        return self.repair / self.offers if self.offers else 0.0


def feed_report(products: list[Product], seconds: float = 0.0,
                date: str | None = None, level: int = 2) -> FeedReport:
    rep = FeedReport(offers=len(products), seconds=seconds, feed_date=date)
    names: dict[str, Counter[str]] = defaultdict(Counter)
    for p in products:
        rep.repair += is_repair(p.category_path)
        rep.in_stock += bool(p.in_stock)
        rep.priced += p.price is not None
        key = " > ".join(p.category_path[:level]) or "(без категории)"
        cov = rep.by_category.setdefault(key, CategoryCoverage(key))
        params = [k for k in p.characteristics if k not in NON_PARAM]
        cov.offers += 1
        cov.with_params += bool(params)
        cov.params_total += len(params)
        cov.with_description += bool(p.description)
        names[key].update(params)
    rep.top_params = {k: v.most_common(6) for k, v in names.items()}
    return rep


def report_markdown(rep: FeedReport, repair_only: bool = True) -> str:
    L = ["# Отчёт по фиду Максидом (Yandex YML)", "",
         f"- Дата фида: {rep.feed_date or 'неизвестна'}",
         f"- Предложений (offers): **{rep.offers}**; с ценой {rep.priced}; "
         f"в наличии {rep.in_stock}",
         f"- Относится к ремонту (`knowledge/feed_scope.yaml`): **{rep.repair}** "
         f"({100 * rep.repair_share:.1f}%)",
         f"- Время разбора и нормализации: **{rep.seconds:.1f} с**", "",
         "## Покрытие параметрами по категориям (уровень 2)", "",
         "| категория | товаров | с параметрами | параметров на товар | с описанием "
         "| частые параметры |",
         "|---|---|---|---|---|---|"]
    cats: list[Any] = sorted(rep.by_category.values(), key=lambda c: -c.offers)
    roots_ok = {c.name for c in cats if is_repair(c.name.split(" > "))}
    for c in cats:
        if repair_only and c.name not in roots_ok:
            continue
        top = ", ".join(f"{k} ({n})" for k, n in rep.top_params.get(c.name, [])[:4])
        L.append(f"| {c.name} | {c.offers} | {100 * c.param_share:.0f}% | {c.mean_params:.1f} | "
                 f"{100 * c.with_description / c.offers:.0f}% | {top} |")
    return "\n".join(L) + "\n"
