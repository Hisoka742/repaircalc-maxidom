"""Human-in-the-loop review queue with JSONL feedback that feeds retraining."""
import json
import time
from pathlib import Path

from maxicalc.ml.match import MatchResult
from maxicalc.ml.synth import Labels


class ReviewQueue:
    def __init__(self, feedback_path: Path | None = None) -> None:
        self._path = feedback_path
        self._pending: dict[str, MatchResult] = {}
        self._feedback: dict[str, Labels] = {}
        if feedback_path and feedback_path.exists():
            for line in feedback_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self._feedback[row["sku"]] = _labels_from_json(row["labels"])

    def add(self, results: list[MatchResult]) -> None:
        for r in results:
            if r.status == "review" and r.sku not in self._feedback:
                self._pending[r.sku] = r

    def pending(self, limit: int | None = None) -> list[MatchResult]:
        items = sorted(self._pending.values(), key=lambda r: (r.review_confidence, r.sku))
        return items[:limit] if limit else items

    def resolve(self, sku: str, labels: Labels, reviewer: str) -> None:
        if sku not in self._pending:
            raise KeyError(f"SKU {sku} нет в очереди проверки")
        del self._pending[sku]
        self._feedback[sku] = labels
        if self._path:
            row = {"sku": sku, "reviewer": reviewer, "ts": time.time(),
                   "labels": _labels_to_json(labels)}
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def override(self, sku: str, labels: Labels, reviewer: str) -> None:
        """A human binding for ANY product (queued or not). Always wins over ML labels."""
        self._pending.pop(sku, None)
        self._feedback[sku] = labels
        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            row = {"sku": sku, "reviewer": reviewer, "ts": time.time(),
                   "labels": _labels_to_json(labels)}
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def feedback(self) -> dict[str, Labels]:
        """Human-verified labels; use them to override weak labels when retraining."""
        return dict(self._feedback)


def _labels_to_json(lab: Labels) -> dict[str, object]:
    return {"work": sorted(lab.work), "rooms": sorted(lab.rooms), "props": sorted(lab.props),
            "calc": lab.calc}


def _labels_from_json(d: dict[str, object]) -> Labels:
    return Labels(set(d["work"]), set(d["rooms"]), set(d["props"]), str(d["calc"]))  # type: ignore[call-overload]
