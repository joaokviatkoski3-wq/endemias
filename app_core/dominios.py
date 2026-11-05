"""Aplicacoes por hostname exato; nenhuma sessao ou permissao cruza setores."""
import re

from flask import Flask, render_template
from werkzeug.wrappers import Response

from app_core.web_security import TunnelLocal


class PorDominio:
    def __init__(self, applications):
        self.applications = applications

    def __call__(self, environ, start_response):
        host = environ.get('HTTP_HOST', '').lower()
        # Host com porta e aceito apenas se for a porta HTTPS padrao.
        host = host.removesuffix(':443')
        application = self.applications.get(host)
        if application is None:
            return Response('Dominio nao configurado.', status=400)(environ, start_response)
        return application(environ, start_response)


def dominio_base(config):
    domain = config.get('DOMINIO_BASE', '')
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', domain) or '..' in domain or '.' not in domain:
        raise ValueError('Dominio base invalido.')
    return domain


def ambiental_application(endemias):
    from app import create_app
    config = dict(endemias.config)
    config.update(SETOR='ambiental', TRUSTED_HOSTS=['ambiental.' + dominio_base(config)])
    return create_app(config)


def portal_application(domain, external=True, logging_config=None):
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    portal = Flask('portal_vsatt', template_folder=str(root / 'templates'), static_folder=str(root / 'static'))
    portal.config.update(TRUSTED_HOSTS=[domain])
    if logging_config and logging_config.get('LOG_PATH'):
        from app_core import logging_rastreamento
        portal.config.update(LOG_PATH=logging_config['LOG_PATH'], SETOR='portal', SETORES_ENABLED=True)
        logging_rastreamento.registrar(portal)

    @portal.get('/')
    def inicio():
        from app_core.version import APP_VERSION,APP_VERSION_DATE
        return render_template('portal_vsatt.html', dominio=domain,APP_VERSION=APP_VERSION,APP_VERSION_DATE=APP_VERSION_DATE)

    @portal.after_request
    def headers(response):
        response.headers.update({
            'Cache-Control': 'private, no-store',
            'Content-Security-Policy': "default-src 'none'; style-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
            'X-Content-Type-Options': 'nosniff',
            'Referrer-Policy': 'same-origin',
        })
        if external:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        return response

    if external:
        portal.wsgi_app = TunnelLocal(portal.wsgi_app)
    return portal


def application(endemias):
    if not endemias.config.get('SETORES_ENABLED'):
        return endemias
    if endemias.config['SETOR'] != 'endemias':
        raise ValueError('A aplicacao principal deve ser Endemias.')
    domain = dominio_base(endemias.config)
    if endemias.config.get('ACESSO_EXTERNO') and endemias.config.get('TRUSTED_HOSTS') != ['endemias.' + domain]:
        raise ValueError('O hostname de Endemias deve corresponder ao dominio base.')
    return PorDominio({
        'endemias.' + domain: endemias,
        'ambiental.' + domain: ambiental_application(endemias),
        domain: portal_application(domain, external=endemias.config.get('ACESSO_EXTERNO', False), logging_config=endemias.config),
    })
