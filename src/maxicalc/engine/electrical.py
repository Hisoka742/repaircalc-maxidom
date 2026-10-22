"""Electrical points estimate (heuristic, configurable).

This is NOT a design calculation and not a code-compliance check: counts come from
per-room-type norms supplied by the caller (knowledge/norms.yaml), which are team defaults.
Every result is labelled as an estimate.
"""
from dataclasses import dataclass
from decimal import Decimal

from maxicalc.engine.units import Number, ceil_int, d


@dataclass(frozen=True)
class RoomNorms:
    m2_per_socket: Decimal
    min_sockets: int
    switches: int
    m2_per_light: Decimal
    cable_m_per_point: Decimal
    sockets_per_breaker: int = 6
    lights_per_breaker: int = 10


@dataclass(frozen=True)
class ElectricalEstimate:
    sockets: int
    switches: int
    light_points: int
    cable_m: Decimal
    breakers: int
    explain: tuple[str, ...]

    @property
    def points(self) -> int:
        return self.sockets + self.switches + self.light_points

    @property
    def junction_boxes(self) -> int:
        return self.points


def estimate(
    room_type: str, floor_area_m2: Number, norms: dict[str, RoomNorms]
) -> ElectricalEstimate:
    if room_type not in norms:
        raise ValueError(f"Нет норм электрики для типа помещения: {room_type}")
    n = norms[room_type]
    a = d(floor_area_m2)
    if a < 0:
        raise ValueError("Площадь не может быть отрицательной")
    sockets = max(n.min_sockets, ceil_int(a / n.m2_per_socket))
    lights = max(1, ceil_int(a / n.m2_per_light))
    points = sockets + n.switches + lights
    cable = points * n.cable_m_per_point
    breakers = -(-sockets // n.sockets_per_breaker) + -(-lights // n.lights_per_breaker)
    ex = (
        "ОЦЕНКА (эвристика, не проект электрики)",
        f"Розетки: max({n.min_sockets}, ceil({a}/{n.m2_per_socket})) = {sockets}",
        f"Выключатели: {n.switches}; светильники: ceil({a}/{n.m2_per_light}) = {lights}",
        f"Кабель: {points} точек × {n.cable_m_per_point} м = {cable} м",
        f"Автоматы: розеточные группы + световые группы = {breakers}",
    )
    return ElectricalEstimate(sockets, n.switches, lights, cable, breakers, ex)
