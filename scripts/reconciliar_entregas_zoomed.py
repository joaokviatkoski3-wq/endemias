"""Conciliação controlada de entregas com planilha e plano privado conferidos.

Sem --aplicar, apenas valida a origem e o estado esperado em transação read-only.
Não remove entregas, não altera receitas, situações clínicas, anexos ou entradas.
"""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TABLES = {
    'animais': 'esporotricose_doentes_animais',
    'receitas': 'esporotricose_doentes_receitas',
    'entregas': 'esporotricose_doentes_entregas',
    'anexos': 'esporotricose_doentes_anexos',
    'estoque': 'esporotricose_estoque_medicacao',
}
FIELDS = ('quantidade', 'data_entrega', 'fonte_medicacao', 'baixa_zoomed')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    default=str, separators=(',', ':')).encode()).hexdigest()


def snapshot(conn):
    return {key: sorted((dict(r) for r in conn.execute('SELECT * FROM ' + table).fetchall()),
                        key=lambda r: json.dumps(r, sort_keys=True, default=str))
            for key, table in TABLES.items()}


def signatures(data):
    return {key: digest(sorted(rows, key=lambda r: json.dumps(r, sort_keys=True, default=str)))
            for key, rows in data.items()}


def totals(rows):
    counts = Counter()
    for row in rows:
        counts[row['fonte_medicacao']] += int(row['quantidade'])
    return {'registros': len(rows), 'capsulas': sum(counts.values()), 'fontes': dict(counts)}


def validate(conn, plan):
    before = snapshot(conn)
    if signatures(before) != plan['assinaturas_antes']:
        raise ValueError('Os dados mudaram desde a conferência. Refazer o plano.')
    deliveries = {r['id_entrega']: r for r in before['entregas']}
    recipes = {r['id_receita']: r for r in before['receitas']}
    animals = {r['id_animal_doente']: r for r in before['animais']}
    seen = set()
    for op in plan['operacoes']:
        if op['tipo'] not in {'atualizar', 'inserir'}:
            raise ValueError('Operação não permitida.')
        new = op['depois']
        if set(new) != set(FIELDS) or type(new['quantidade']) is not int or new['quantidade'] <= 0:
            raise ValueError('Campos ou quantidade inválidos.')
        if new['fonte_medicacao'] not in {'SESA', 'Município'} or new['baixa_zoomed'] != 'Sim':
            raise ValueError('Fonte/baixa incompatível com entrega comprovada no ZooMed.')
        datetime.strptime(new['data_entrega'], '%Y-%m-%d')
        if not op['linhas_zoomed'] or not op['motivo']:
            raise ValueError('Operação sem evidência.')
        recipe = recipes[op['id_receita']]
        animal = animals[recipe['id_animal_doente']]
        if animal['id_animal_doente'] != op['id_animal_doente']:
            raise ValueError('Vínculo com animal incorreto.')
        if op['tipo'] == 'atualizar':
            ident = op['id_entrega']
            if ident in seen or deliveries[ident]['id_receita'] != op['id_receita']:
                raise ValueError('Entrega repetida ou vínculo modificado.')
            seen.add(ident)
            if {f: str(deliveries[ident][f]) if f == 'data_entrega' else deliveries[ident][f]
                    for f in FIELDS} != op['antes']:
                raise ValueError('Entrega diferente da conferida.')
        else:
            if any(e['id_receita'] == op['id_receita'] and str(e['data_entrega']) == new['data_entrega']
                   and e['quantidade'] == new['quantidade'] for e in before['entregas']):
                raise ValueError('A entrega a incluir já existe.')
    return before


def apply(conn, plan):
    """Transação única; qualquer erro desfaz todo o lote e sua auditoria."""
    with conn:
        before = validate(conn, plan)
        em = datetime.now().isoformat(timespec='seconds')
        changes = []
        for op in plan['operacoes']:
            new = op['depois']
            args = tuple(new[f] for f in FIELDS)
            if op['tipo'] == 'atualizar':
                ident = op['id_entrega']
                conn.execute('UPDATE esporotricose_doentes_entregas SET quantidade=?, '
                             'data_entrega=?,fonte_medicacao=?,baixa_zoomed=? WHERE id_entrega=?',
                             (*args, ident))
            else:
                row = conn.execute('INSERT INTO esporotricose_doentes_entregas '
                                   '(quantidade,data_entrega,fonte_medicacao,baixa_zoomed,id_receita,'
                                   'observacoes,criado_em) VALUES(?,?,?,?,?,?,?) RETURNING id_entrega',
                                   (*args, op['id_receita'], 'Conferência ZooMed ' + plan['lote'], em)).fetchone()
                ident = row[0]
            conn.execute('UPDATE esporotricose_doentes_animais SET atualizado_em=? '
                         'WHERE id_animal_doente=?', (em, op['id_animal_doente']))
            detail = {**op, 'lote': plan['lote'], 'fonte_sha256': plan['fonte_sha256'],
                      'plano_sha256': digest(plan), 'id_entrega_resultante': ident}
            conn.execute('INSERT INTO auditoria_eventos '
                         '(acao,entidade,entidade_id,usuario_nome,detalhes_json,criado_em,setor) '
                         "VALUES('entrega_conciliada_zoomed','esporotricose_entrega',?,'Operação VSATT',?,?, 'ambiental')",
                         (str(ident), json.dumps(detail, ensure_ascii=False), em))
            changes.append(detail)
        after = snapshot(conn)
        expected = {r['id_entrega']: dict(r) for r in before['entregas']}
        actual = {r['id_entrega']: dict(r) for r in after['entregas']}
        for change in changes:
            ident = change['id_entrega_resultante']
            if change['tipo'] == 'atualizar':
                expected[ident].update(change['depois'])
            else:
                expected[ident] = {**change['depois'], 'id_entrega': ident,
                                   'id_receita': change['id_receita'],
                                   'observacoes': 'Conferência ZooMed ' + plan['lote'], 'criado_em': em}
        if digest(expected) != digest(actual):
            raise ValueError('Uma entrega diverge do resultado esperado.')
        expected_animals = {r['id_animal_doente']: dict(r) for r in before['animais']}
        for change in changes:
            expected_animals[change['id_animal_doente']]['atualizado_em'] = em
        if digest(expected_animals) != digest({r['id_animal_doente']: r for r in after['animais']}):
            raise ValueError('Dados clínicos fora do escopo foram alterados.')
        for key in ('receitas', 'anexos', 'estoque'):
            if digest(before[key]) != digest(after[key]):
                raise ValueError('Tabela fora do escopo foi alterada: ' + key)
        if totals(after['entregas']) != plan['totais_depois']:
            raise ValueError('Resultado não corresponde ao lote conferido.')
        return {'status': 'aplicado', 'lote': plan['lote'], 'em': em,
                'antes': totals(before['entregas']), 'depois': totals(after['entregas']),
                'mudancas': changes, 'assinaturas_depois': signatures(after)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plano', type=Path, required=True)
    parser.add_argument('--fonte', type=Path, required=True)
    parser.add_argument('--resultado', type=Path, required=True)
    parser.add_argument('--aplicar', action='store_true')
    args = parser.parse_args()
    from app_core import db
    from scripts.ativar_acesso_externo_windows import connect
    from scripts.endurecer_web_windows import backup_before_change
    plan = json.loads(args.plano.read_text(encoding='utf-8'))
    if hashlib.sha256(args.fonte.read_bytes()).hexdigest() != plan['fonte_sha256']:
        raise ValueError('Planilha diferente da conferida.')
    config = json.loads(Path('C:/ProgramData/EndemiasWeb/config.json').read_text(encoding='utf-8'))
    if config['env']['ENDEMIAS_PG_DATABASE'] != 'endemias':
        raise ValueError('Banco diferente do oficial.')
    backup = None
    if args.aplicar:
        private = Path('C:/ProgramData/EndemiasWeb') / ('conciliacao-zoomed-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
        private.mkdir()
        backup = backup_before_change(config, private)
        shutil.copy2(args.fonte, private / 'zoomed.xlsx')
        shutil.copy2(args.plano, private / 'plano.json')
    raw = connect(config, readonly=not args.aplicar)
    conn = db.PostgreSQLConnection(raw)
    try:
        if args.aplicar:
            conn.execute("SET LOCAL lock_timeout='5s'")
            conn.execute('LOCK TABLE ' + ','.join(TABLES.values()) + ' IN SHARE ROW EXCLUSIVE MODE')
            result = apply(conn, plan)
            result['backup'] = backup
        else:
            before = validate(conn, plan)
            result = {'status': 'validado_somente_leitura', 'lote': plan['lote'],
                      'antes': totals(before['entregas']), 'operacoes': len(plan['operacoes'])}
            conn.rollback()
    finally:
        conn.close()
    args.resultado.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    print(result['status'])


if __name__ == '__main__':
    main()
