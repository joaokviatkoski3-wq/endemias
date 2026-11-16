import uuid
from datetime import datetime
from pathlib import Path

from flask import Blueprint, abort, current_app, jsonify, render_template, request, send_file

from app_core import amostras_animais as amostras_core
from app_core import auth as auth_core
from app_core import blueprint_helpers as bh
from app_core import utils as utils_core
from app_core import db as db_core
from app_core import audit


bp = Blueprint("amostras_animais", __name__)
login_required = auth_core.login_required


@bp.route("/amostras-animais")
@login_required
def page():
    return render_template(
        "amostras_animais.html",
        d_ini=request.args.get("d_ini", utils_core.data_n_dias(365)),
        d_fim=request.args.get("d_fim", utils_core.hoje()),
        localidades=amostras_core.localidades(bh.db_target()),
        agentes=bh.catalogo_agentes(amostras_core.agentes(bh.db_target())),
        motivos=amostras_core.opcoes(bh.db_target(), "motivo_visita"),
        tipos=amostras_core.opcoes(bh.db_target(), "tipo_animal"),
        pode_anexar=(bh.usuario_atual() or {}).get('nivel') in {'operador', 'admin', 'superadmin'},
    )


@bp.route("/api/amostras-animais")
@login_required
def api_resumo():
    return jsonify(amostras_core.resumo(bh.db_target(), _filtros()))


@bp.route("/api/amostras-animais/listar")
@login_required
def api_listar():
    filtros = _filtros()
    filtros["busca"] = request.args.get("busca", "")
    return jsonify(amostras_core.listar(bh.db_target(), filtros))


@bp.route('/api/amostras-animais/<id_amostra>/anexos', methods=['GET', 'POST'])
@login_required
def anexos(id_amostra):
    conn = db_core.connect(bh.db_target())
    try:
        amostras_core.ensure_schema(conn)
        if not conn.execute('SELECT 1 FROM amostras_animais WHERE id_amostra=?', (id_amostra,)).fetchone():
            return jsonify({'erro': 'Registro não encontrado.'}), 404
        if request.method == 'POST':
            usuario = bh.usuario_atual() or {}
            if usuario.get('nivel') not in {'operador', 'admin', 'superadmin'}:
                return jsonify({'erro': 'Sem permissão para adicionar anexos.'}), 403
            from blueprints import esporotricose as anexos_core
            arquivos = request.files.getlist('arquivos')
            if not arquivos or len(arquivos) > 10:
                return jsonify({'erro': 'Escolha de 1 a 10 arquivos.'}), 400
            validados = []
            for arquivo in arquivos:
                meta, erro = anexos_core._validar_upload_anexo(arquivo)
                if erro:
                    return jsonify({'erro': erro}), 400
                validados.append((arquivo, meta))
            base = Path(current_app.config['ANEXOS_DIR']).resolve()
            destino = base / 'amostras_animais'
            destino.mkdir(parents=True, exist_ok=True)
            salvos = []
            try:
                for arquivo, meta in validados:
                    item = anexos_core._salvar_upload_anexo(arquivo, meta, destino)
                    salvos.append(item['caminho'])
                    conn.execute('INSERT INTO amostra_animais_anexos (id_anexo,id_amostra,nome_original,caminho_rel,mime_type,tamanho,criado_em,criado_por) VALUES (?,?,?,?,?,?,?,?)',
                                 (uuid.uuid4().hex, id_amostra, item['nome_original'], str(item['caminho'].relative_to(base)).replace('\\', '/'), item['mime_type'], item['tamanho'], datetime.now().isoformat(timespec='seconds'), usuario.get('nome') or 'sistema'))
                audit.registrar_evento(bh.get_db, 'amostras_animais_anexos_incluidos', entidade='amostras_animais', entidade_id=id_amostra, detalhes={'quantidade': len(salvos)}, conn=conn)
                conn.commit()
            except Exception:
                conn.rollback()
                anexos_core._remover_caminhos(salvos)
                current_app.logger.exception('Falha ao salvar anexos de amostras')
                return jsonify({'erro': 'Não foi possível salvar os anexos.'}), 500
        rows = conn.execute('SELECT id_anexo,nome_original,tamanho,criado_em FROM amostra_animais_anexos WHERE id_amostra=? ORDER BY criado_em,id_anexo', (id_amostra,)).fetchall()
        return jsonify({'anexos': [db_core.serialize_row(row) for row in rows]})
    finally:
        conn.close()


@bp.route('/amostras-animais/anexos/<id_anexo>/download')
@login_required
def baixar_anexo(id_anexo):
    conn = db_core.connect(bh.db_target())
    try:
        row = conn.execute('SELECT nome_original,caminho_rel,mime_type FROM amostra_animais_anexos WHERE id_anexo=?', (id_anexo,)).fetchone()
        if not row:
            abort(404)
        base = Path(current_app.config['ANEXOS_DIR']).resolve()
        caminho = (base / row['caminho_rel']).resolve()
        if base not in caminho.parents or not caminho.is_file():
            abort(404)
        return send_file(caminho, mimetype=row['mime_type'], as_attachment=True, download_name=row['nome_original'], max_age=0)
    finally:
        conn.close()


@bp.route("/api/amostras-animais/exportar")
@login_required
def exportar():
    from app_core.listagem_operacional import exportar_csv
    filtros = _filtros()
    filtros["busca"] = request.args.get("busca", "")
    dados = amostras_core.listar(bh.db_target(), filtros, completo=True)
    campos = [["data","Data"],["hora","Hora"],["agentes","Agentes"],["motivo_visita","Motivo"],["animal_motivador","Animal motivador"],["animal_motivador_outro","Outro motivador"],["localidade","Localidade"],["quarteirao","Quarteirão"],["tipo_imovel","Tipo de imóvel"],["visita","Visita"],["logradouro","Logradouro"],["numero","Número"],["sequencia","Sequência"],["morador","Morador"],["ocorrencia_residencia","Ocorrência"],["onde","Onde"],["houve_acidente","Acidente"],["houve_captura","Captura"],["local_captura","Local da captura"],["tipo_animal","Tipo capturado"],["animal_capturado","Animal capturado"],["especie_serpente","Espécie de serpente"],["especie_escorpiao","Espécie de escorpião"],["especie_lagarta","Espécie de lagarta"],["especie_aranha","Espécie de aranha"],["especie_carrapato","Espécie de carrapato"],["quantidade","Quantidade"],["origem_estrutura","Origem"]]
    return exportar_csv(dados["registros"], campos, "amostras_animais", bh.db_target(), bh.usuario_atual() or {})


def _filtros():
    return {
        "pagina": request.args.get("pagina", ""),
        "por_pagina": request.args.get("por_pagina", ""),
        "d_ini": request.args.get("d_ini", ""),
        "d_fim": request.args.get("d_fim", ""),
        "localidade": request.args.get("localidade", ""),
        "agente": request.args.get("agente", ""),
        "motivo": request.args.get("motivo", ""),
        "tipo_animal": request.args.get("tipo_animal", ""),
        "acidente": request.args.get("acidente", ""),
        "captura": request.args.get("captura", ""),
        "origem": request.args.get("origem", ""),
    }
