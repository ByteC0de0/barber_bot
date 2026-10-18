"""Все роутеры (группы обработчиков) собираются здесь."""

from aiogram import Router

from . import admin, booking, common, fallback, my_bookings


def get_routers() -> list[Router]:
    # Порядок важен: апдейт проверяется роутерами сверху вниз,
    # fallback ловит всё остальное и поэтому стоит последним
    return [common.router, admin.router, booking.router, my_bookings.router, fallback.router]
