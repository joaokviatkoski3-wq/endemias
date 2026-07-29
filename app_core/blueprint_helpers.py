from flask import current_app, request

from app_core import auth as auth_core
from app_core import db as db_core
from app_core import utils as utils_core


def db_path():
    return current_app.config["DB_PATH"]


def db_target():
    return db_core.configured_target(current_app.config)


def get_db():
    return db_core.connect(db_target())


def q(sql, params=()):
    return db_core.query(db_target(), sql, params)


def q1(sql, params=()):
    return db_core.query_one(db_target(), sql, params)


def qval(sql, params=()):
    return db_core.scalar(db_target(), sql, params)


def usuario_atual():
    return auth_core.usuario_atual(q1)


def nivel_min(nivel):
    return auth_core.nivel_min(nivel, usuario_atual)


def request_int_arg(nome, default, minimo=None, maximo=None):
    return utils_core.bounded_int(request.args.get(nome), default, minimo, maximo)
