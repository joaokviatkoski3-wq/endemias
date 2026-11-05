"""Indicadores ambientais. Animais/vínculos não multiplicam a contagem de visitas."""
from collections import Counter, defaultdict

from app_core import db

FONTES = (
    ('esporotricose_visitas', 'esporotricose_visita_agentes', 'id_visita', 'Esporotricose'),
    ('amostras_animais', 'amostra_animais_agentes', 'id_amostra', 'Amostra de Animais'),
)
FILTROS_COMUNS = ('visita', 'tipo_imovel', 'origem_estrutura')
FILTROS_AMOSTRAS = ('motivo_visita', 'tipo_animal', 'houve_acidente', 'houve_captura')
AGRUPAMENTOS = {
    'territorio': ('data', 'fonte', 'localidade', 'quarteirao'),
    'dia': ('data', 'fonte'), 'mes': ('mes', 'fonte'),
    'localidade': ('localidade', 'fonte'),
    'quarteirao': ('localidade', 'quarteirao', 'fonte'),
    'situacao': ('visita', 'fonte'),
}
TITULOS = {'data': 'Data', 'mes': 'Mês', 'fonte': 'Área', 'localidade': 'Localidade',
           'quarteirao': 'Quarteirão', 'visita': 'Situação da visita'}


def _where(table, links, key, label, args):
    where, params = [], []
    if args.get('fonte') and args['fonte'] != label:
        return ['1=0'], []
    for field, op, arg in (('v.data', '>=', 'd_ini'), ('v.data', '<=', 'd_fim'),
                            ('COALESCE(l.nome,v.localidade)', '=', 'localidade'),
                            ('v.quarteirao', '=', 'quarteirao')):
        if args.get(arg):
            where.append(field + op + '?')
            params.append(args[arg])
    for field in FILTROS_COMUNS:
        if args.get(field):
            where.append('v.' + field + '=?')
            params.append(args[field])
    if args.get('agente'):
        where.append(f'EXISTS(SELECT 1 FROM {links} x JOIN agentes a ON a.id_agente=x.id_agente WHERE x.{key}=v.{key} AND a.nome=?)')
        params.append(args['agente'])
    amostra = table == 'amostras_animais'
    if any(args.get(k) for k in FILTROS_AMOSTRAS):
        if not amostra:
            where.append('1=0')
        else:
            for field in FILTROS_AMOSTRAS:
                if args.get(field):
                    where.append('v.' + field + '=?')
                    params.append(args[field])
    if args.get('especie') or args.get('feridas'):
        if amostra:
            where.append('1=0')
        else:
            animal_where = ['a.id_visita=v.id_visita']
            for field in ('especie', 'feridas'):
                if args.get(field):
                    animal_where.append('a.' + field + '=?')
                    params.append(args[field])
            where.append('EXISTS(SELECT 1 FROM esporotricose_animais a WHERE ' + ' AND '.join(animal_where) + ')')
    return where, params


def _visitas(conn, args):
    result = []
    for table, links, key, label in FONTES:
        where, params = _where(table, links, key, label, args)
        extra = ("v.tipo_animal,COALESCE(v.quantidade,0) AS quantidade,0 AS animais,0 AS animais_feridas"
                 if table == 'amostras_animais' else
                 "NULL AS tipo_animal,0 AS quantidade,"
                 "(SELECT COUNT(*) FROM esporotricose_animais a WHERE a.id_visita=v.id_visita) AS animais,"
                 "(SELECT COUNT(*) FROM esporotricose_animais a WHERE a.id_visita=v.id_visita AND LOWER(TRIM(a.feridas)) IN ('sim','s','1','yes')) AS animais_feridas")
        sql = f'''SELECT v.data,v.id_localidade,COALESCE(l.nome,NULLIF(v.localidade,''),'Não informada') AS localidade,
            v.quarteirao,COALESCE(NULLIF(v.visita,''),'Não informada') AS visita,{extra}
            FROM {table} v LEFT JOIN localidades l ON l.id_localidade=v.id_localidade'''
        if where:
            sql += ' WHERE ' + ' AND '.join(where)
        for row in conn.execute(sql, params):
            result.append({**db.serialize_row(row), 'fonte': label})
    return result


def _linhas(visitas):
    counts = Counter((str(v['data']), v['id_localidade'], v['localidade'], v['quarteirao'], v['fonte']) for v in visitas)
    rows = [dict(data=d, id_localidade=i, localidade=l, quarteirao=q, fonte=f, registros=n)
            for (d, i, l, q, f), n in counts.items()]
    return sorted(rows, key=lambda r: (r['data'], r['fonte'], r['localidade'], str(r['quarteirao'] or '')), reverse=True)


def linhas(target, args):
    conn = db.connect(target)
    try:
        return _linhas(_visitas(conn, args))
    finally:
        conn.close()


def resumo(target, args):
    conn = db.connect(target)
    try:
        visitas = _visitas(conn, args)
    finally:
        conn.close()
    totals = {label: sum(v['fonte'] == label for v in visitas) for *_, label in FONTES}
    series = defaultdict(Counter)
    for v in visitas:
        series[str(v['data'])[:7]][v['fonte']] += 1
    def ranking(field):
        return [{'nome': k, 'registros': n} for k, n in Counter(v[field] or 'Não informado' for v in visitas).most_common()]
    return {
        'totais': totals, 'registros': len(visitas), 'linhas': _linhas(visitas),
        'localidades': len({v['localidade'] for v in visitas}),
        'quarteiroes': len({(v['id_localidade'] or v['localidade'], v['quarteirao']) for v in visitas if v['quarteirao'] is not None}),
        'animais': sum(v['animais'] for v in visitas),
        'animais_feridas': sum(v['animais_feridas'] for v in visitas),
        'quantidade_amostras': sum(v['quantidade'] for v in visitas),
        'por_localidade': ranking('localidade'), 'por_situacao': ranking('visita'),
        'por_tipo_animal': [{'nome': k, 'registros': n} for k, n in Counter(
            v['tipo_animal'] or 'Não informado' for v in visitas if v['fonte'] == 'Amostra de Animais').most_common()],
        'por_mes': [{'mes': m, **{label: counts[label] for label in totals}} for m, counts in sorted(series.items())],
        'primeira_data': min((str(v['data']) for v in visitas), default=None),
        'ultima_data': max((str(v['data']) for v in visitas), default=None),
    }


def opcoes(target):
    """Somente categorias ambientais, sem nomes/endereços pessoais."""
    conn = db.connect(target)
    result = {}
    try:
        for field in (*FILTROS_COMUNS, *FILTROS_AMOSTRAS, 'especie', 'feridas'):
            tables = (('esporotricose_animais',) if field in ('especie', 'feridas') else
                      ('amostras_animais',) if field in FILTROS_AMOSTRAS else
                      tuple(f[0] for f in FONTES))
            values = set()
            for table in tables:
                values.update(r[0] for r in conn.execute(f'SELECT DISTINCT {field} FROM {table} WHERE {field} IS NOT NULL AND {field}<>? ORDER BY {field}', ('',)))
            result[field] = sorted(values)
        return result
    finally:
        conn.close()


def relatorio(target, args):
    fields = AGRUPAMENTOS[args.get('agrupamento', 'territorio')]
    conn = db.connect(target)
    try:
        visitas = _visitas(conn, args)
    finally:
        conn.close()
    groups = defaultdict(lambda: [0, 0, 0, 0])
    for v in visitas:
        v['mes'] = str(v['data'])[:7]
        values = tuple(str(v[f]) if v[f] is not None else 'Não informado' for f in fields)
        row = groups[values]
        row[0] += 1
        row[1] += v['animais']
        row[2] += v['animais_feridas']
        row[3] += v['quantidade']
    rows = [[*values, *counts] for values, counts in sorted(groups.items())]
    headers = [TITULOS[f] for f in fields] + ['Visitas', 'Animais cadastrados', 'Animais com feridas', 'Quantidade (Amostras)']
    return {'headers': headers, 'rows': rows, 'numericos': list(range(len(fields), len(headers))), 'visitas': len(visitas)}
