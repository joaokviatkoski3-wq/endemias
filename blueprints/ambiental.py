import csv
import io
from datetime import date
from html import escape

from flask import current_app,Blueprint,Response,jsonify,render_template,request,send_file
from app_core import ambiental,auth,blueprint_helpers as bh,escopo_agente
from app_core.csv_seguranca import campo_csv

bp=Blueprint('ambiental',__name__)


def filtros():
    keys=('d_ini','d_fim','localidade','agente','quarteirao','fonte',
          *ambiental.FILTROS_COMUNS,*ambiental.FILTROS_AMOSTRAS,'especie','feridas')
    args={k:request.args.get(k,'').strip() for k in keys}
    if any(len(v)>200 for v in args.values()):raise ValueError('Filtro muito longo.')
    for k in ('d_ini','d_fim'):
        if args[k]:args[k]=date.fromisoformat(args[k]).isoformat()
    if args['d_ini'] and args['d_fim'] and args['d_ini']>args['d_fim']:
        raise ValueError('A data inicial deve anteceder a final.')
    if args['quarteirao']:
        if not args['quarteirao'].isascii() or not args['quarteirao'].isdigit() or int(args['quarteirao'])>2147483647:
            raise ValueError('Quarteirão inválido.')
        args['quarteirao']=str(int(args['quarteirao']))
    if args['fonte'] not in ('',*(f[3] for f in ambiental.FONTES)):raise ValueError('Área inválida.')
    args['agrupamento']=request.args.get('agrupamento','territorio')
    if args['agrupamento'] not in ambiental.AGRUPAMENTOS:raise ValueError('Agrupamento inválido.')
    user=bh.usuario_atual()
    if args['agente'] and escopo_agente.nivel_restrito(user):
        own=escopo_agente.agente_proprio(bh.db_target(),user)
        if not escopo_agente.filtrar_agentes([args['agente']],(own or {}).get('chaves') or set()):
            raise ValueError('Filtro de agente não permitido.')
    return args


def painel(titulo='Dashboard Ambiental'):
    if titulo=='Vigilância Ambiental':return render_template('ambiental_home.html')
    try:
        args=filtros();dados=ambiental.resumo(bh.db_target(),args)
    except ValueError:
        return 'Filtros inválidos. Confira as datas e os campos selecionados.',400
    return render_template('ambiental_painel.html',titulo=titulo,dados=dados,filtros=args,opcoes=ambiental.opcoes(bh.db_target()))


@bp.get('/vigiagua')
@auth.login_required
def vigiagua():
    return render_template('ambiental_vigiagua.html')


@bp.get('/relatorios')
@auth.login_required
def relatorios():
    try:
        args=filtros();report=ambiental.relatorio(bh.db_target(),args)
        pagina=max(1,int(request.args.get('pagina','1')))
    except ValueError:return 'Filtros inválidos.',400
    total=len(report['rows']);paginas=max(1,(total+49)//50);pagina=min(pagina,paginas)
    rows=report['rows'][(pagina-1)*50:pagina*50]
    return render_template('ambiental_relatorios.html',filtros=args,opcoes=ambiental.opcoes(bh.db_target()),
                           report=report,rows=rows,pagina=pagina,paginas=paginas,total_linhas=total)


@bp.get('/api/ambiental/dashboard')
@auth.login_required
def dashboard():
    try:return jsonify(ambiental.resumo(bh.db_target(),filtros()))
    except ValueError:return jsonify({'erro':'Período inválido.'}),400


@bp.get('/relatorios/exportar/<formato>')
@auth.login_required
def exportar(formato):
    if formato not in {'csv','xlsx','pdf'}:return 'Formato inválido.',404
    try:args=filtros();report=ambiental.relatorio(bh.db_target(),args)
    except ValueError:return 'Filtros inválidos.',400
    headers=report['headers'];values=report['rows'];numeric=report['numericos']
    if formato=='csv':
        buffer=io.StringIO();buffer.write('\ufeff')
        writer=csv.writer(buffer,delimiter=';');writer.writerow(headers)
        writer.writerows([[campo_csv(v,numerico=i in numeric) for i,v in enumerate(row)] for row in values])
        return Response(buffer.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=relatorio_ambiental.csv'})
    output=io.BytesIO()
    if formato=='xlsx':
        from openpyxl import Workbook
        book=Workbook();sheet=book.active;sheet.title='Ambiental';sheet.append(headers)
        for row in values:sheet.append([campo_csv(v,numerico=i in numeric) for i,v in enumerate(row)])
        sheet.freeze_panes='A2';sheet.auto_filter.ref=sheet.dimensions
        for col in sheet.columns:sheet.column_dimensions[col[0].column_letter].width=24
        book.save(output);book.close()
    else:
        from reportlab.lib.pagesizes import A4,landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate,Paragraph,Table,TableStyle
        from reportlab.lib import colors
        styles=getSampleStyleSheet()
        cells=[[Paragraph(escape(str(v)),styles['BodyText']) for v in row] for row in [headers,*values]]
        table=Table(cells,colWidths=[(landscape(A4)[0]-72)/len(headers)]*len(headers),repeatRows=1)
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.lightgrey),('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.25,colors.lightgrey)]))
        desc=' · '.join(f'{k}: {v}' for k,v in args.items() if v)
        SimpleDocTemplate(output,pagesize=landscape(A4),leftMargin=36,rightMargin=36).build([
            Paragraph('Vigilância Ambiental — relatório',styles['Title']),
            Paragraph(escape(desc),styles['BodyText']),
            Paragraph(f"{report['visitas']} visitas. Animais: cadastros nas visitas selecionadas; feridas não equivalem a diagnóstico.",styles['BodyText']),table])
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
