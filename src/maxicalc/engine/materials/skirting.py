"""Skirting: pieces = ceil(length x 1.05 / piece length); corners from geometry."""
from decimal import Decimal

from maxicalc.engine.geometry import Room
from maxicalc.engine.result import Calc
from maxicalc.engine.units import Number, ceil_int, d

RESERVE = Decimal("0.05")


def pieces(room: Room, piece_len_m: Number = "2.5") -> Calc:
    p = d(piece_len_m)
    if p <= 0:
        raise ValueError("Некорректная длина плинтуса")
    ln = room.skirting_length_m
    n = ceil_int(ln * (1 + RESERVE) / p)
    return Calc(
        Decimal(n), "шт",
        (f"Длина: периметр {room.perimeter_m} м − двери {room.doors_width_m} м = {ln} м",
         f"ceil({ln} × 1.05 / {p}) = {n} шт",
         f"Углы: внутренних {room.inner_corners}, внешних {room.outer_corners}"),
    )
