"""Collect repair-category products from maxidom.ru and emit them in the stand's Bagisto schema.

Rules of engagement (checked at runtime, not assumed):
  * robots.txt is fetched and honoured: disallowed URLs are never requested, and the delay between
    requests is at least the `Crawl-delay` it declares (3 s at the time of writing) and at least
    the configured minimum;
  * raw pages are cached (gzip) so a re-run, or a parser fix, costs no requests;
  * a descriptive User-Agent with a contact address.

The output is a JSONL of items in the case's `/api/catalog/products/{id}` shape (so
`load_catalog` reads it and `stand_mock` can serve it). Fields the site does not publish are left
out, never invented (no `ratings`, no `stocks`).
"""
import gzip
import html
import re
import time
import urllib.robotparser
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

BASE = "https://www.maxidom.ru"
UA = "Mozilla/5.0 (compatible; MaxicalcResearchBot/0.1; contact: team@example.org)"
PRODUCT_URL = re.compile(r"^https://www\.maxidom\.ru/catalog/([^/]+)/(\d+)/$")

# Category slugs that matter for repair calculators, by material group. A slug is taken when it
# contains one of the group's fragments; EXCLUDE removes look-alikes (garden, furniture, decor).
GROUPS: dict[str, tuple[str, ...]] = {
    "tile": ("plitka-nastennaya", "keramogranit", "napolnaya-plitka", "plitka-spc", "mozaika",
             "klinkern", "zatirki", "klei-dlya-plitki", "sistemy-vyravnivaniya", "krestiki",
             "zakladki-dlya-plitki", "ugolki-i-bordyury"),
    "flooring": ("laminat", "parket", "linoleum", "kovrolin", "podlozh", "plintus",
                 "komplektuyuschie-k-plintusam", "plintusy"),
    "wallpaper": ("oboi", "kley-sredstva-dlya-oboev", "fotooboi"),
    "paint": ("kraski", "emal", "gruntovk", "lak", "propitk", "antiseptik", "shpatlev",
              "kolery"),
    "mixes": ("styazhk", "nalivn", "shtukaturk", "smesi-", "suhie-stroitelnye", "cement",
              "gidroizol", "kley-montazhnyy", "pena-montazhnaya", "germetik"),
    "drywall": ("gipsokarton", "gkl", "profil-dlya-gkl", "profili-dlya-gipsokartona"),
    "electrical": ("rozetki", "vyklyuchateli", "kabel", "provod", "avtomat", "schetchik",
                   "svetilniki", "lampy"),
    "plumbing": ("smesiteli", "unitaz", "vanny", "dushevye", "rakoviny", "sifon", "trubi",
                 "truby", "santeh"),
    "glue": ("kley-", "klei-"),
}
EXCLUDE = ("sad", "teplits", "pochvogrunt", "udobren", "kashpo", "podushki", "zerkala",
           "nakleyki", "plenka-samokley", "ruchki-nazhimnye", "ramki-dlya-rozetok", "mebel",
           "shkafy", "tumby", "trotuarnaya", "basseyn", "rasteni")


def group_of(slug: str) -> str | None:
    if any(x in slug for x in EXCLUDE):
        return None
    for g, frags in GROUPS.items():
        if any(f in slug for f in frags):
            return g
    return None


def strip_html(raw: str) -> str:
    """Drop scripts, styles and comments (what remains is the content we parse and cache)."""
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", raw, flags=re.S | re.I)
    return re.sub(r"<!--.*?-->", "", s, flags=re.S)


def _text(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


_NUM = r"(\d+(?:[.,]\d+)?)"


def _num(s: str) -> float | None:
    m = re.search(_NUM, s)
    return float(m.group(1).replace(",", ".")) if m else None


def parse_product(page: str, url: str) -> dict[str, Any] | None:
    """One product page -> a Bagisto-style item, or None if the page is not a product card."""
    m = PRODUCT_URL.match(url)
    if not m:
        return None
    slug, pid = m.group(1), m.group(2)
    body = strip_html(page)
    pairs = re.findall(
        r'flypage__product-essence-character-name">(.*?)</span>.*?'
        r'flypage__product-essence-character-data">(.*?)</span>', body, flags=re.S)
    chars: dict[str, str] = {}
    for n, v in pairs:
        k, val = _text(n), _text(v)
        if k and val and k not in chars:
            chars[k] = val
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", body, flags=re.S)
    name = _text(h1.group(1)) if h1 else chars.get("Наименование", "")
    if not name:
        return None
    price_m = re.search(r'itemprop="price"[^>]*>\s*([\d\s.,]+)\s*<', body)
    price = _num(price_m.group(1).replace(" ", "")) if price_m else None
    avail = re.search(r'itemprop="availability"[^>]*href="[^"]*/(\w+)"', body)
    in_stock = None if not avail else avail.group(1).lower() == "instock"
    # section name: the link to /catalog/<slug>/ (the product's own category)
    sec = re.search(rf'<a[^>]*href="/catalog/{re.escape(slug)}/"[^>]*>(.*?)</a>', body, flags=re.S)
    section = _text(sec.group(1)) if sec else slug
    pack_area = None
    pack_qty = None
    for key in ("Площадь покрытия упаковкой", "В упаковке", "Площадь упаковки"):
        if key in chars and pack_area is None:
            mm = re.search(_NUM + r"\s*м[2²]", chars[key])
            if mm:
                pack_area = float(mm.group(1).replace(",", "."))
    for key in ("Количество в упаковке", "В упаковке"):
        if key in chars and pack_qty is None:
            mm = re.search(_NUM + r"\s*шт", chars[key])
            if mm:
                pack_qty = int(float(mm.group(1).replace(",", ".")))
    desc = re.search(r'itemprop="description"[^>]*>(.*?)</div>', body, flags=re.S)
    brand = chars.get("Бренд")
    item: dict[str, Any] = {
        "id": int(pid), "sku": chars.get("Артикул") or pid,
        "cod_good": chars.get("Код товара") or pid, "name": name,
        "marketing_description": _text(desc.group(1)) if desc else "",
        "type": "simple", "url_key": f"/catalog/{slug}/{pid}/",
        "price": price, "result_price": price, "currency": "RUB",
        "quantity_in_package": pack_qty, "package_area": pack_area,
        "in_stock": in_stock, "status": True,
        "brand": {"id": None, "name": brand} if brand else None,
        "categories": {slug: section},
        "categories_tree": [{"id": slug, "name": section, "depth": 1}],
        "characteristics": [{"code": k, "name": k, "value": v} for k, v in chars.items()
                            if k not in ("Код товара", "Наименование", "Артикул", "Бренд")],
        "description": _text(desc.group(1)) if desc else "",
    }
    return item


@dataclass
class Plan:
    urls: list[str] = field(default_factory=list)
    by_group: dict[str, int] = field(default_factory=dict)
    by_slug: dict[str, int] = field(default_factory=dict)


def plan_urls(sitemap_xml_texts: list[str], per_slug_cap: int | None = None) -> Plan:
    """Select repair product URLs from sitemap parts and interleave them across slugs, so any
    prefix of the crawl covers every material type instead of one huge category first."""
    seen: set[str] = set()
    by_slug: dict[str, list[str]] = {}
    for xml in sitemap_xml_texts:
        for u in re.findall(r"<loc>([^<]+)</loc>", xml):
            m = PRODUCT_URL.match(u)
            if not m or u in seen:
                continue
            seen.add(u)
            if group_of(m.group(1)):
                by_slug.setdefault(m.group(1), []).append(u)
    plan = Plan()
    queues = {s: (v[:per_slug_cap] if per_slug_cap else v) for s, v in sorted(by_slug.items())}
    plan.by_slug = {s: len(v) for s, v in queues.items()}
    for s, v in queues.items():
        g = group_of(s) or "other"
        plan.by_group[g] = plan.by_group.get(g, 0) + len(v)
    i = 0
    while any(i < len(v) for v in queues.values()):
        for s in queues:
            if i < len(queues[s]):
                plan.urls.append(queues[s][i])
        i += 1
    return plan


class Crawler:
    def __init__(self, cache: Path, min_delay_s: float = 3.0, client: httpx.Client | None = None,
                 sleep: Any = time.sleep, clock: Any = time.monotonic) -> None:
        self.cache = cache
        self.cache.mkdir(parents=True, exist_ok=True)
        self.http = client or httpx.Client(headers={"User-Agent": UA}, timeout=40.0,
                                           follow_redirects=True)
        self.min_delay = min_delay_s
        self._sleep, self._clock = sleep, clock
        self._last = 0.0
        self.robots = urllib.robotparser.RobotFileParser()
        self.requests = 0
        self.cache_hits = 0
        self.crawl_delay = min_delay_s

    def load_robots(self) -> None:
        r = self.http.get(f"{BASE}/robots.txt")
        r.raise_for_status()
        self.robots.parse(r.text.splitlines())
        d = self.robots.crawl_delay("*") or self.robots.crawl_delay(UA)
        self.crawl_delay = max(self.min_delay, float(d or 0))

    def allowed(self, url: str) -> bool:
        return self.robots.can_fetch("*", url)

    def _cache_file(self, url: str) -> Path:
        key = re.sub(r"[^A-Za-z0-9_-]+", "_", url.removeprefix(BASE))[:150] or "root"
        return self.cache / f"{key}.html.gz"

    def get(self, url: str) -> str | None:
        """Cached text of `url`, or fetched (politely). None for disallowed / non-200."""
        f = self._cache_file(url)
        if f.exists():
            self.cache_hits += 1
            return gzip.decompress(f.read_bytes()).decode("utf-8", errors="replace")
        if not self.allowed(url):
            return None
        wait = self._last + self.crawl_delay - self._clock()
        if wait > 0:
            self._sleep(wait)
        self._last = self._clock()
        self.requests += 1
        try:
            r = self.http.get(url)
        except httpx.HTTPError:
            return None
        if r.status_code != 200:
            return None
        text = strip_html(r.text) if PRODUCT_URL.match(url) else r.text
        f.write_bytes(gzip.compress(text.encode("utf-8"), 6))
        return text


def iter_products(crawler: Crawler, urls: list[str], limit: int | None = None
                  ) -> Iterator[dict[str, Any]]:
    n = 0
    for u in urls:
        if limit is not None and n >= limit:
            return
        page = crawler.get(u)
        if page is None:
            continue
        item = parse_product(page, u)
        if item is not None:
            n += 1
            yield item
