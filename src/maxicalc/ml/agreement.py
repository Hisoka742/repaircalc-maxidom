"""Inter-annotator agreement for multi-label annotation.

Every (product, work type) cell is a binary decision "this work applies". Agreement is computed
on the overlap rows labelled by several annotators:
  * Cohen's kappa for every pair of annotators, pooled over all cells (micro) and per work type;
  * Krippendorff's alpha (nominal, binary, any number of annotators, missing cells allowed).
Interpretation used in the methodology: kappa / alpha >= 0.8 reliable, 0.67-0.8 tentative.
"""
from collections.abc import Mapping, Sequence
from itertools import combinations

Labels = Mapping[str, Sequence[set[str]]]    # annotator -> sets per row (same row order)


def cohen_kappa_binary(a: Sequence[bool], b: Sequence[bool]) -> float:
    n = len(a)
    if n == 0:
        return 0.0
    po = sum(x == y for x, y in zip(a, b, strict=True)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    if pe == 1.0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)


def _cells(labels: Sequence[set[str]], classes: Sequence[str]) -> list[bool]:
    return [w in s for s in labels for w in classes]


def pairwise_kappa(labels: Labels, classes: Sequence[str]) -> dict[tuple[str, str], float]:
    out = {}
    for x, y in combinations(sorted(labels), 2):
        out[(x, y)] = cohen_kappa_binary(_cells(labels[x], classes), _cells(labels[y], classes))
    return out


def per_class_kappa(labels: Labels, classes: Sequence[str]) -> dict[str, float]:
    """Mean over annotator pairs of the binary kappa of one work type."""
    out = {}
    pairs = list(combinations(sorted(labels), 2))
    for w in classes:
        ks = [cohen_kappa_binary([w in s for s in labels[x]], [w in s for s in labels[y]])
              for x, y in pairs]
        pos = sum(w in s for ann in labels.values() for s in ann)
        if pos:
            out[w] = sum(ks) / len(ks) if ks else 0.0
    return out


def krippendorff_alpha(labels: Labels, classes: Sequence[str]) -> float:
    """Nominal alpha over binary cells; annotators are columns, (row, work) cells are units."""
    annotators = sorted(labels)
    n_rows = len(next(iter(labels.values()))) if labels else 0
    units = [[w in labels[a][i] for a in annotators] for i in range(n_rows) for w in classes]
    # coincidence counts for categories {False, True}
    o = {(False, False): 0.0, (False, True): 0.0, (True, False): 0.0, (True, True): 0.0}
    for u in units:
        m = len(u)
        if m < 2:
            continue
        for i in range(m):
            for j in range(m):
                if i != j:
                    o[(u[i], u[j])] += 1.0 / (m - 1)
    n_f = o[(False, False)] + o[(False, True)]
    n_t = o[(True, True)] + o[(True, False)]
    n = n_f + n_t
    if n <= 1:
        return 0.0
    d_obs = (o[(False, True)] + o[(True, False)]) / n
    d_exp = 2 * n_f * n_t / (n * (n - 1))
    return 1.0 - d_obs / d_exp if d_exp else 1.0


def majority_vote(votes: Sequence[set[str]], classes: Sequence[str]) -> tuple[set[str], set[str]]:
    """(labels chosen by a strict majority, work types with an exact tie -> needs adjudication)."""
    chosen: set[str] = set()
    ties: set[str] = set()
    n = len(votes)
    for w in classes:
        k = sum(w in v for v in votes)
        if 2 * k > n:
            chosen.add(w)
        elif 2 * k == n and k > 0:
            ties.add(w)
    return chosen, ties
