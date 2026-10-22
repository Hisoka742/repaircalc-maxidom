"""Room geometry: simple polygon (rectilinear or not) with openings.

Assumes a non-self-intersecting polygon. Wall i is the edge from vertex i to vertex i+1.
Doors reduce the usable wall width and the skirting length; windows reduce only wall area.
"""
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from functools import cached_property
from typing import Literal

from maxicalc.engine.units import Number, d


@dataclass(frozen=True)
class Opening:
    kind: Literal["door", "window"]
    width_m: Decimal
    height_m: Decimal
    wall: int


Point = tuple[Decimal, Decimal]


def _dist(a: Point, b: Point) -> Decimal:
    return ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2).sqrt()


@dataclass(frozen=True)
class Room:
    vertices: tuple[Point, ...]
    height_m: Decimal
    openings: tuple[Opening, ...] = ()

    def __post_init__(self) -> None:
        if len(self.vertices) < 3:
            raise ValueError("Помещение должно иметь не менее 3 вершин")
        if self.height_m <= 0:
            raise ValueError("Высота потолка должна быть положительной")
        lens = self.wall_lengths_m()
        if any(x <= 0 for x in lens):
            raise ValueError("Длина стены должна быть положительной")
        used = [Decimal(0)] * len(lens)
        for o in self.openings:
            if not 0 <= o.wall < len(lens):
                raise ValueError(f"Проём ссылается на несуществующую стену {o.wall}")
            if o.width_m <= 0 or o.height_m <= 0:
                raise ValueError("Размеры проёма должны быть положительными")
            if o.height_m > self.height_m:
                raise ValueError("Проём выше потолка")
            used[o.wall] += o.width_m
        if any(u > ln for u, ln in zip(used, lens, strict=True)):
            raise ValueError("Проёмы шире стены")

    @classmethod
    def from_vertices(
        cls, pts: Sequence[tuple[Number, Number]], height_m: Number,
        openings: Sequence[Opening] = (),
    ) -> "Room":
        return cls(tuple((d(x), d(y)) for x, y in pts), d(height_m), tuple(openings))

    @classmethod
    def rectangle(
        cls, length_m: Number, width_m: Number, height_m: Number,
        openings: Sequence[Opening] = (),
    ) -> "Room":
        ln, w = d(length_m), d(width_m)
        if ln <= 0 or w <= 0:
            raise ValueError("Размеры комнаты должны быть положительными")
        z = Decimal(0)
        return cls(((z, z), (ln, z), (ln, w), (z, w)), d(height_m), tuple(openings))

    @cached_property
    def _lengths(self) -> tuple[Decimal, ...]:
        v = self.vertices
        return tuple(_dist(v[i], v[(i + 1) % len(v)]) for i in range(len(v)))

    def wall_lengths_m(self) -> tuple[Decimal, ...]:
        """Cached: a Room is immutable, and sqrt is the hot spot of every estimate."""
        return self._lengths

    def _signed_area(self) -> Decimal:
        v = self.vertices
        s = sum(
            (v[i][0] * v[(i + 1) % len(v)][1] - v[(i + 1) % len(v)][0] * v[i][1]
             for i in range(len(v))),
            Decimal(0),
        )
        return s / 2

    @property
    def floor_area_m2(self) -> Decimal:
        return abs(self._signed_area())

    @property
    def ceiling_area_m2(self) -> Decimal:
        return self.floor_area_m2

    @property
    def perimeter_m(self) -> Decimal:
        return sum(self.wall_lengths_m(), Decimal(0))

    @property
    def wall_area_gross_m2(self) -> Decimal:
        return self.perimeter_m * self.height_m

    @property
    def openings_area_m2(self) -> Decimal:
        return sum((o.width_m * o.height_m for o in self.openings), Decimal(0))

    @property
    def wall_area_net_m2(self) -> Decimal:
        return self.wall_area_gross_m2 - self.openings_area_m2

    @property
    def doors_width_m(self) -> Decimal:
        return sum((o.width_m for o in self.openings if o.kind == "door"), Decimal(0))

    @property
    def skirting_length_m(self) -> Decimal:
        return self.perimeter_m - self.doors_width_m

    def wall_net_widths_m(self) -> tuple[Decimal, ...]:
        """Per-wall width minus doors (windows leave strips above/below, so they stay)."""
        w = list(self.wall_lengths_m())
        for o in self.openings:
            if o.kind == "door":
                w[o.wall] -= o.width_m
        return tuple(w)

    def _corner_counts(self) -> tuple[int, int]:
        v = self.vertices
        n = len(v)
        orient = 1 if self._signed_area() > 0 else -1
        inner = outer = 0
        for i in range(n):
            a, b, c = v[i - 1], v[i], v[(i + 1) % n]
            cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
            if cross == 0:
                continue
            if (cross > 0) == (orient > 0):
                inner += 1  # convex vertex = internal corner of the room
            else:
                outer += 1
        return inner, outer

    @property
    def inner_corners(self) -> int:
        return self._corner_counts()[0]

    @property
    def outer_corners(self) -> int:
        return self._corner_counts()[1]


@dataclass(frozen=True)
class WallSurface(Room):
    """A single flat surface of `width x height` metres: what a customer types into a product
    card ("my wall is 4.2 x 2.6"). It is not a room: no floor, no ceiling, no skirting, no
    openings. `as_floor` lets tile (laid on the given area) read the same area as its floor.

    Source: area = width x height (plane geometry)."""

    as_floor: bool = False

    @classmethod
    def of(cls, width_m: Number, height_m: Number, as_floor: bool = False) -> "WallSurface":
        w, h = d(width_m), d(height_m)
        if w <= 0 or h <= 0:
            raise ValueError("Размеры поверхности должны быть положительными")
        # a valid triangle so Room's own checks pass; every measure below is overridden
        return cls(vertices=((Decimal(0), Decimal(0)), (w, Decimal(0)), (Decimal(0), Decimal(1))),
                   height_m=h, openings=(), as_floor=as_floor)

    @property
    def _width(self) -> Decimal:
        return self.vertices[1][0]

    def wall_lengths_m(self) -> tuple[Decimal, ...]:
        return (self._width,)

    @property
    def perimeter_m(self) -> Decimal:
        return self._width

    @property
    def wall_area_gross_m2(self) -> Decimal:
        return self._width * self.height_m

    @property
    def floor_area_m2(self) -> Decimal:
        return self._width * self.height_m if self.as_floor else Decimal(0)

    @property
    def ceiling_area_m2(self) -> Decimal:
        return Decimal(0)

    @property
    def skirting_length_m(self) -> Decimal:
        return Decimal(0)

    def wall_net_widths_m(self) -> tuple[Decimal, ...]:
        return (self._width,)
