import csv
import io
from datetime import date
from html import escape

from flask import current_app,Blueprint,Response,jsonify,render_template,request,send_file
from app_core import ambiental,auth,blueprint_helpers as bh
from app_core.csv_seguranca import campo_csv

bp=Blueprint('ambiental',__name__)


def filtros():
    args={k:request.args.get(k,'').strip() for k in ('d_ini','d_fim','localidade','agente')}
    for k in ('d_ini','d_fim'):
        if args[k]:date.fromisoformat(args[k])
    if args['d_ini'] and args['d_fim'] and args['d_ini']>args['d_fim']:
        raise ValueError('A data inicial deve anteceder a final.')
    return args


def painel(titulo='Dashboard Ambiental'):
    try:
        args=filtros();dados=ambiental.resumo(bh.db_target(),args)
    except ValueError:
        return 'Período inválido.',400
    return render_template('ambiental_painel.html',titulo=titulo,dados=dados,filtros=args)


@bp.get('/vigiagua')
@auth.login_required
def vigiagua():
    return render_template('ambiental_vigiagua.html')


@bp.get('/relatorios')
@auth.login_required
def relatorios():return painel('Relatórios Ambientais')


@bp.get('/api/ambiental/dashboard')
@auth.login_required
def dashboard():
    try:return jsonify(ambiental.resumo(bh.db_target(),filtros()))
    except ValueError:return jsonify({'erro':'Período inválido.'}),400


@bp.get('/relatorios/exportar/<formato>')
@auth.login_required
def exportar(formato):
    if formato not in {'csv','xlsx','pdf'}:return 'Formato inválido.',404
    try:args=filtros();rows=ambiental.linhas(bh.db_target(),args)
    except ValueError:return 'Período inválido.',400
    headers=['Data','Fonte','Localidade','Quarteirão','Registros']
    values=[[str(r['data'] or ''),r['fonte'],r['localidade'],str(r['quarteirao'] or ''),r['registros']] for r in rows]
    if formato=='csv':
        buffer=io.StringIO();buffer.write('\ufeff')
        writer=csv.writer(buffer,delimiter=';');writer.writerow(headers)
        writer.writerows([[campo_csv(v,numerico=i==4) for i,v in enumerate(row)] for row in values])
        return Response(buffer.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=relatorio_ambiental.csv'})
    output=io.BytesIO()
    if formato=='xlsx':
        from openpyxl import Workbook
        book=Workbook();sheet=book.active;sheet.title='Ambiental';sheet.append(headers)
        for row in values:sheet.append([campo_csv(v,numerico=i==4) for i,v in enumerate(row)])
        book.save(output);book.close()
    else:
        from reportlab.lib.pagesizes import A4,landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate,Paragraph,Table,TableStyle
        from reportlab.lib import colors
        styles=getSampleStyleSheet()
        cells=[[Paragraph(escape(str(v)),styles['BodyText']) for v in row] for row in [headers,*values]]
        table=Table(cells,colWidths=[75,125,230,75,70],repeatRows=1)
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.lightgrey),('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.25,colors.lightgrey)]))
        SimpleDocTemplate(output,pagesize=landscape(A4)).build([Paragraph('Vigilância Ambiental — relatório',styles['Title']),table])
    output.seek(0)
    return send_file(output,as_attachment=True,download_name='relatorio_ambiental.'+formato)


def dados_mapa():
    try:return jsonify(ambiental.resumo(bh.db_target(),filtros()))
    except ValueError:return jsonify({'erro':'Período inválido.'}),400


@bp.get('/api/ambiental/territorio')
@auth.login_required
def territorio():
    from app_core import registro_geografico
    try:
        geometry=registro_geografico.geojson_ativo(bh.db_target(),current_app.config['BASE_DIR'])
    except ValueError:return jsonify({'erro':'Camada territorial indisponível.'}),400
    # Nao transportar propriedades extras de uma importacao territorial.
    return jsonify({'type':'FeatureCollection','features':[
        {'type':'Feature','geometry':f['geometry'],'properties':{k:v for k,v in f.get('properties',{}).items() if k in {'Localidade','Localidade_nome','id_quart'}}}
        for f in geometry.get('features',[])]})
