(() => {
  'use strict';

  const area = document.getElementById('pessoal-folgas');
  if (!area) return;

  const element = (name) => document.getElementById(`pessoal-${name}`);
  const api = '/api/pessoal/folgas';
  const filtroServidor = element('filtro-servidor');
  const filtroTipo = element('filtro-tipo');
  const filtroSituacao = element('filtro-situacao');
  const formCredito = element('form-credito');
  const formOcorrencia = element('form-ocorrencia');
  const dialogDetalhes = element('dialog-detalhes');
  const formDetalhes = element('detalhes-form');
  const acoesDetalhes = element('detalhes-acoes');
  const rotulosStatus = {
    agendada: 'Folga agendada', aguardando_confirmacao: 'Folga a confirmar', utilizada: 'Folga utilizada',
    registrada: 'Falta', cancelada: 'Cancelada', ativo: 'Ativo', esgotado: 'Esgotado',
    expirado: 'Expirado', cancelado: 'Cancelado',
  };
  const rotulosFaltas = {
    pendente: 'Aguardando justificativa', justificada: 'Falta justificada',
    abonada: 'Falta abonada', injustificada: 'Falta não justificada',
  };
  const rotulosOrigens = Object.fromEntries(Array.from(formCredito.elements.origem.options)
    .filter((opcao) => opcao.value).map((opcao) => [opcao.value, opcao.textContent]));
  const rotulosSetores = {endemias: 'Endemias', ambiental: 'Vigilância Ambiental'};
  const formatoNumero = new Intl.NumberFormat('pt-BR', {maximumFractionDigits: 1});
  const fuso = 'America/Sao_Paulo';
  const formatoDataLocal = new Intl.DateTimeFormat('sv-SE', {timeZone: fuso});
  const formatoHoraLocal = new Intl.DateTimeFormat('sv-SE', {timeZone: fuso, timeStyle: 'medium'});
  let calendario;
  let consultaResumo;
  let ultimaConsultaAgenda = 0;
  let alterarDetalhes;

  function node(tag, texto, classes) {
    const item = document.createElement(tag);
    if (texto !== undefined) item.textContent = texto;
    if (classes) item.className = classes;
    return item;
  }

  function botao(texto, acao) {
    const item = node('button', texto, 'btn btn-ghost btn-sm');
    item.type = 'button';
    item.addEventListener('click', acao);
    return item;
  }

  function dataExibida(data) {
    return data ? data.slice(0, 10).split('-').reverse().join('/') : '—';
  }

  function dias(unidades) {
    const quantidade = unidades / 2;
    return `${formatoNumero.format(quantidade)} ${quantidade > 0 && quantidade <= 1 ? 'dia' : 'dias'}`;
  }

  function situacaoOcorrencia(ocorrencia) {
    if (ocorrencia.status === 'registrada') return rotulosFaltas[ocorrencia.classificacao] || 'Falta';
    return rotulosStatus[ocorrencia.status] || ocorrencia.status;
  }

  function horarioOcorrencia(ocorrencia) {
    if (ocorrencia.dia_inteiro) return 'Dia inteiro';
    const faixa = `${ocorrencia.hora_inicio} às ${ocorrencia.hora_fim}`;
    return ocorrencia.tipo === 'folga' ? `Meio dia · ${faixa}` : faixa;
  }

  function status(alvo, mensagem, erro = false) {
    alvo.textContent = mensagem;
    alvo.toggleAttribute('data-falha', erro);
  }

  async function requisicao(caminho, {dados, signal} = {}) {
    const opcoes = {signal, cache: 'no-store', headers: {'Accept': 'application/json'}};
    if (dados !== undefined) {
      opcoes.method = 'POST';
      opcoes.headers['Content-Type'] = 'application/json';
      opcoes.headers['X-CSRFToken'] = getCsrf();
      opcoes.body = JSON.stringify(dados);
    }
    const resposta = await fetch(`${api}${caminho}`, opcoes);
    const json = await resposta.json().catch(() => null);
    if (!resposta.ok || !json) {
      throw new Error(json?.erro || 'Não foi possível acessar o Controle de Pessoal. Confira sua sessão e tente novamente.');
    }
    return json;
  }

  function mostrarVencimentos(saldos) {
    const alvo = element('vencimentos');
    alvo.replaceChildren();
    const proximos = saldos.filter((saldo) => saldo.a_vencer > 0)
      .sort((a, b) => a.proximo_vencimento.localeCompare(b.proximo_vencimento));
    if (!proximos.length) return;
    const detalhes = node('details');
    const titulo = proximos.length === 1 ? 'Créditos a vencer de 1 servidor' : `Créditos a vencer de ${proximos.length} servidores`;
    detalhes.append(node('summary', titulo));
    const lista = node('ul');
    for (const saldo of proximos) {
      const linha = node('li');
      const resumo = `próximo vencimento em ${dataExibida(saldo.proximo_vencimento)} · ${dias(saldo.a_vencer)} a vencer em 30 dias`;
      if (filtroServidor.value) {
        linha.textContent = resumo;
      } else {
        linha.append(botao(`${saldo.nome} · ${resumo}`, () => {
          filtroServidor.value = saldo.id_agente;
          filtroServidor.focus();
          atualizarServidor();
        }));
      }
      lista.append(linha);
    }
    detalhes.append(lista);
    alvo.append(detalhes);
  }

  async function carregarPainel() {
    consultaResumo?.abort();
    const consulta = new AbortController();
    consultaResumo = consulta;
    const servidor = filtroServidor.value;
    const saldoRetorno = element('saldo-retorno');
    const extratoRetorno = element('extrato-retorno');
    const campos = ['disponivel', 'reservado', 'utilizado', 'expirado', 'concedido', 'a_vencer'];
    const opcoes = {signal: consulta.signal};
    element('extrato').hidden = !servidor;
    element('vencimentos').replaceChildren();
    for (const campo of campos) element(`saldo-${campo}`).textContent = '—';
    status(saldoRetorno, 'Carregando saldos…');
    if (servidor) {
      element('extrato-titulo').textContent = 'Extrato do servidor';
      element('extrato-conteudo').replaceChildren();
      status(extratoRetorno, 'Carregando extrato…');
    }

    try {
      const extrato = servidor ? await requisicao(`/servidores/${servidor}/extrato`, opcoes) : null;
      const saldos = extrato ? [extrato.saldo] : (await requisicao('/saldos', opcoes)).saldos;
      if (consulta.signal.aborted) return;
      for (const campo of campos) {
        element(`saldo-${campo}`).textContent = dias(saldos.reduce((total, saldo) => total + saldo[campo], 0));
      }
      mostrarVencimentos(saldos);
      status(saldoRetorno, '');
      if (extrato) {
        mostrarExtrato(extrato);
        status(extratoRetorno, '');
      }
    } catch (erro) {
      if (consulta.signal.aborted) return;
      status(saldoRetorno, erro.message, true);
      status(extratoRetorno, 'Extrato indisponível. Alterne o filtro para tentar novamente.', true);
    }
  }

  function tabela(titulo, colunas, linhas, vazio) {
    const secao = node('section');
    secao.append(node('h4', titulo));
    if (!linhas.length) {
      secao.append(node('p', vazio, 'pessoal-folgas-ajuda'));
      return secao;
    }
    const rolagem = node('div', undefined, 'table-scroll');
    rolagem.setAttribute('role', 'region');
    rolagem.setAttribute('aria-label', titulo);
    rolagem.tabIndex = 0;
    const lista = node('table', undefined, 'pessoal-folgas-tabela');
    lista.setAttribute('aria-label', titulo);
    const cabecalho = lista.createTHead().insertRow();
    for (const coluna of colunas) {
      const th = node('th', coluna);
      th.scope = 'col';
      cabecalho.append(th);
    }
    const corpo = lista.createTBody();
    for (const campos of linhas) {
      const linha = corpo.insertRow();
      for (const campo of campos) linha.insertCell().append(campo ?? '—');
    }
    rolagem.append(lista);
    secao.append(rolagem);
    return secao;
  }

  function mostrarExtrato(extrato) {
    const {saldo, creditos, ocorrencias, consumos} = extrato;
    element('extrato-titulo').textContent = `Extrato de ${saldo.nome}`;
    const linhasCreditos = creditos.map((credito) => [
      dataExibida(credito.data_aquisicao), rotulosOrigens[credito.origem], dataExibida(credito.validade),
      dias(credito.unidades), dias(credito.disponivel), rotulosStatus[credito.status],
      botao(`Ver crédito #${credito.id_credito}`, () => abrirCredito(credito, saldo.nome)),
    ]);
    const consumoPorOcorrencia = new Map();
    for (const consumo of consumos) {
      const lista = consumoPorOcorrencia.get(consumo.id_ocorrencia) || [];
      lista.push(consumo);
      consumoPorOcorrencia.set(consumo.id_ocorrencia, lista);
    }
    const linhasOcorrencias = ocorrencias.map((ocorrencia) => [
      dataExibida(ocorrencia.data), horarioOcorrencia(ocorrencia), situacaoOcorrencia(ocorrencia),
      ocorrencia.tipo === 'folga' ? 'Folga' : 'Falta',
      botao(`Ver ocorrência #${ocorrencia.id_ocorrencia}`, () => abrirOcorrencia(ocorrencia, consumoPorOcorrencia.get(ocorrencia.id_ocorrencia) || [])),
    ]);
    element('extrato-conteudo').replaceChildren(
      node('p', `Total de créditos concedidos: ${dias(saldo.concedido)}.`, 'pessoal-folgas-ajuda'),
      tabela('Créditos de folga', ['Aquisição', 'Origem', 'Validade', 'Concedido', 'Disponível', 'Situação', 'Ação'], linhasCreditos, 'Nenhum crédito de folga registrado.'),
      tabela('Ocorrências', ['Data', 'Período', 'Situação', 'Tipo', 'Ação'], linhasOcorrencias, 'Nenhuma ocorrência registrada.'),
    );
  }

  function atualizarServidor() {
    const url = new URL(window.location.href);
    const id = filtroServidor.value;
    if (id) url.searchParams.set('id_agente', id);
    else url.searchParams.delete('id_agente');
    history.replaceState(null, '', url);
    carregarPainel();
    calendario?.refetchEvents();
  }

  function eventoAgenda(ocorrencia) {
    const allDay = ocorrencia.dia_inteiro;
    return {
      id: String(ocorrencia.id_ocorrencia),
      title: `${ocorrencia.nome} · ${situacaoOcorrencia(ocorrencia)}`,
      allDay,
      start: allDay ? ocorrencia.data : `${ocorrencia.data}T${ocorrencia.hora_inicio}:00`,
      end: allDay ? undefined : `${ocorrencia.data}T${ocorrencia.hora_fim}:00`,
      classNames: [`pessoal-evento-${ocorrencia.status}`],
      extendedProps: {ocorrencia},
    };
  }

  async function carregarEventos(intervalo, sucesso, falha) {
    const consulta = ++ultimaConsultaAgenda;
    const parametros = new URLSearchParams({inicio: intervalo.startStr.slice(0, 10), fim: intervalo.endStr.slice(0, 10)});
    const retorno = element('calendario-retorno');
    const situacao = filtroSituacao.value;
    if (filtroServidor.value) parametros.set('id_agente', filtroServidor.value);
    if (filtroTipo.value) parametros.set('tipo', filtroTipo.value);
    if (situacao === 'cancelada') parametros.set('incluir_canceladas', '1');
    status(retorno, 'Carregando agenda…');
    try {
      const dados = await requisicao(`/ocorrencias?${parametros}`);
      const ocorrencias = dados.ocorrencias.filter((ocorrencia) => {
        if (!situacao) return ocorrencia.status !== 'cancelada';
        return ocorrencia.status === situacao || (ocorrencia.status === 'registrada' && ocorrencia.classificacao === situacao);
      });
      sucesso(ocorrencias.map(eventoAgenda));
      if (consulta === ultimaConsultaAgenda) status(retorno, ocorrencias.length ? '' : 'Nenhuma ocorrência no período com os filtros selecionados.');
    } catch (erro) {
      if (consulta === ultimaConsultaAgenda) status(retorno, erro.message, true);
      falha(erro);
    }
  }

  function atualizarCamposOcorrencia() {
    const campos = formOcorrencia.elements;
    const falta = campos.tipo.value === 'falta';
    const parcial = campos.periodo.value === 'parcial';
    const hoje = formatoDataLocal.format(new Date());
    element('campo-classificacao').hidden = !falta;
    campos.classificacao.disabled = !falta;
    campos.periodo.options[1].textContent = falta ? 'Período com horário' : 'Meio dia';
    element('campos-horas').hidden = !parcial;
    for (const campo of [campos.hora_inicio, campos.hora_fim]) {
      campo.disabled = !parcial;
      campo.required = parcial;
    }
    campos.data.max = falta ? hoje : '';
    campos.observacao.required = Boolean(!falta && campos.data.value && campos.data.value < hoje);
    const ajuda = falta
      ? 'A falta fica no histórico sem alterar o saldo de folgas.'
      : 'O agendamento reserva o saldo válido para a data. Confirme o uso após a folga.';
    element('ocorrencia-ajuda').textContent = !falta && parcial
      ? `${ajuda} Informe o início e o fim da metade da jornada que será usada como folga.` : ajuda;
    const diaSemana = new Date(`${campos.data.value}T12:00:00Z`).getUTCDay();
    const aviso = element('ocorrencia-aviso');
    const fimDeSemana = !falta && [0, 6].includes(diaSemana);
    aviso.hidden = !fimDeSemana;
    aviso.textContent = fimDeSemana ? 'A data cai no fim de semana. Confira se o servidor teria expediente.' : '';
  }

  function abrirFormulario(formulario, data) {
    formulario.reset();
    formulario.querySelector('[data-erro]').textContent = '';
    const campos = formulario.elements;
    const hoje = formatoDataLocal.format(new Date());
    const id = filtroServidor.value;
    if (Array.from(campos.id_agente.options).some((opcao) => opcao.value === id)) campos.id_agente.value = id;
    if (formulario === formCredito) {
      campos.data_aquisicao.value = hoje;
      campos.data_aquisicao.max = hoje;
      campos.validade.min = hoje;
    } else {
      campos.data.value = data || hoje;
      if (filtroTipo.value === 'falta' && campos.data.value <= hoje) campos.tipo.value = 'falta';
      atualizarCamposOcorrencia();
    }
    formulario.closest('dialog').showModal();
  }

  function dadosCredito(formulario) {
    const {dias: quantidade, ...dados} = Object.fromEntries(new FormData(formulario));
    return {...dados, id_agente: Number(dados.id_agente), unidades: Number(quantidade) * 2};
  }

  function dadosOcorrencia(formulario) {
    const {periodo, ...dados} = Object.fromEntries(new FormData(formulario));
    return {...dados, id_agente: Number(dados.id_agente), dia_inteiro: periodo === 'inteiro'};
  }

  async function salvar(formulario, caminho, dados, mensagem) {
    const dialog = formulario.closest('dialog');
    if (dialog.dataset.salvando) return;
    const retorno = dialog.querySelector('[data-erro]');
    const submit = formulario.querySelector('button[type="submit"]');
    dialog.dataset.salvando = '1';
    dialog.setAttribute('aria-busy', 'true');
    submit.disabled = true;
    retorno.textContent = '';
    try {
      await requisicao(caminho, {dados});
      dialog.close();
      toast(mensagem, 'success');
      carregarPainel();
      calendario?.refetchEvents();
    } catch (erro) {
      retorno.textContent = erro.message;
    } finally {
      delete dialog.dataset.salvando;
      dialog.removeAttribute('aria-busy');
      submit.disabled = false;
    }
  }

  function valoresDetalhes(campos) {
    const lista = node('dl', undefined, 'pessoal-folgas-detalhes');
    for (const [campo, valor] of campos) {
      if (valor === undefined || valor === null || valor === '') continue;
      lista.append(node('dt', campo), node('dd', String(valor)));
    }
    return lista;
  }

  function iniciarAcaoDetalhes(caminho, rotulo, precisaMotivo, classificacao) {
    alterarDetalhes = {caminho, precisaMotivo, classificar: Boolean(classificacao)};
    const campos = formDetalhes.elements;
    formDetalhes.reset();
    campos.motivo.required = precisaMotivo;
    campos.classificacao.value = classificacao || 'pendente';
    element('detalhes-classificacao').hidden = !classificacao;
    element('detalhes-motivo').hidden = !precisaMotivo;
    element('detalhes-salvar').textContent = rotulo;
    acoesDetalhes.hidden = true;
    formDetalhes.hidden = false;
    dialogDetalhes.querySelector('[data-erro]').textContent = '';
    if (classificacao) campos.classificacao.focus();
    else if (precisaMotivo) campos.motivo.focus();
    else element('detalhes-salvar').focus();
  }

  function limparAcaoDetalhes() {
    formDetalhes.hidden = true;
    acoesDetalhes.hidden = false;
    alterarDetalhes = null;
    dialogDetalhes.querySelector('[data-erro]').textContent = '';
  }

  function abrirDetalhes(titulo, campos, acoes) {
    const heading = element('detalhes-titulo');
    heading.textContent = titulo;
    element('detalhes-conteudo').replaceChildren(valoresDetalhes(campos));
    acoesDetalhes.replaceChildren(...acoes, botao('Fechar', () => dialogDetalhes.close()));
    limparAcaoDetalhes();
    dialogDetalhes.showModal();
    heading.focus();
  }

  function abrirCredito(credito, servidor) {
    const caminho = `/creditos/${credito.id_credito}`;
    const acoes = [];
    if (credito.status !== 'cancelado' && !credito.reservado && !credito.utilizado) {
      acoes.push(botao('Cancelar crédito', () => iniciarAcaoDetalhes(`${caminho}/cancelar`, 'Confirmar cancelamento', true)));
    }
    abrirDetalhes(`Crédito #${credito.id_credito}`, [
      ['Servidor', servidor], ['Origem', rotulosOrigens[credito.origem]], ['Setor de registro', rotulosSetores[credito.setor]],
      ['Aquisição', dataExibida(credito.data_aquisicao)], ['Válido até', dataExibida(credito.validade)],
      ['Concedido', dias(credito.unidades)], ['Disponível', dias(credito.disponivel)], ['Reservado', dias(credito.reservado)],
      ['Utilizado', dias(credito.utilizado)], ['Expirado', dias(credito.expirado)], ['Situação', rotulosStatus[credito.status]],
      ['Atividade', credito.descricao], ['Referência', credito.referencia], ['Motivo do cancelamento', credito.motivo_cancelamento],
    ], acoes);
  }

  function abrirOcorrencia(ocorrencia, consumos = []) {
    const caminho = `/ocorrencias/${ocorrencia.id_ocorrencia}`;
    const folga = ocorrencia.tipo === 'folga';
    const acoes = [];
    if (ocorrencia.status === 'aguardando_confirmacao') {
      acoes.push(botao('Confirmar uso da folga', () => iniciarAcaoDetalhes(`${caminho}/confirmar`, 'Confirmar uso', false)));
    }
    if (ocorrencia.status === 'registrada' && !folga) {
      acoes.push(botao('Classificar falta', () => iniciarAcaoDetalhes(`${caminho}/classificar`, 'Salvar classificação', true, ocorrencia.classificacao || 'pendente')));
    }
    if (ocorrencia.status !== 'cancelada') {
      acoes.push(botao('Cancelar ocorrência', () => iniciarAcaoDetalhes(`${caminho}/cancelar`, 'Confirmar cancelamento', true)));
    }
    if (filtroServidor.value !== String(ocorrencia.id_agente)) {
      acoes.push(botao('Ver extrato', () => {
        dialogDetalhes.close();
        filtroServidor.value = ocorrencia.id_agente;
        atualizarServidor();
        element('extrato-titulo').focus();
      }));
    }
    const vinculos = consumos.map((consumo) => `#${consumo.id_credito} · ${dias(consumo.unidades)}`).join('\n');
    abrirDetalhes(`${folga ? 'Folga' : 'Falta'} #${ocorrencia.id_ocorrencia}`, [
      ['Servidor', ocorrencia.nome], ['Data', dataExibida(ocorrencia.data)], ['Período', horarioOcorrencia(ocorrencia)],
      ['Situação', situacaoOcorrencia(ocorrencia)], ['Classificação', ocorrencia.status === 'cancelada' ? rotulosFaltas[ocorrencia.classificacao] : ''],
      ['Saldo vinculado', folga ? dias(ocorrencia.unidades) : ''], ['Créditos vinculados', vinculos],
      ['Setor de registro', rotulosSetores[ocorrencia.setor]], ['Observação', ocorrencia.observacao],
      ['Motivo da classificação', ocorrencia.motivo_classificacao], ['Motivo do cancelamento', ocorrencia.motivo_cancelamento],
    ], acoes);
  }

  filtroServidor.addEventListener('change', atualizarServidor);
  for (const filtro of [filtroTipo, filtroSituacao]) filtro.addEventListener('change', () => calendario?.refetchEvents());
  element('novo-credito').addEventListener('click', () => abrirFormulario(formCredito));
  element('nova-ocorrencia').addEventListener('click', () => abrirFormulario(formOcorrencia));
  formCredito.elements.data_aquisicao.addEventListener('change', () => {
    formCredito.elements.validade.min = formCredito.elements.data_aquisicao.value;
  });
  for (const nome of ['tipo', 'periodo', 'data']) {
    formOcorrencia.elements[nome].addEventListener('change', atualizarCamposOcorrencia);
  }
  formCredito.addEventListener('submit', (evento) => {
    evento.preventDefault();
    salvar(formCredito, '/creditos', dadosCredito(formCredito), 'Crédito de folga registrado.');
  });
  formOcorrencia.addEventListener('submit', (evento) => {
    evento.preventDefault();
    salvar(formOcorrencia, '/ocorrencias', dadosOcorrencia(formOcorrencia), 'Ocorrência registrada.');
  });
  formDetalhes.addEventListener('submit', (evento) => {
    evento.preventDefault();
    if (!alterarDetalhes) return;
    const dados = {};
    if (alterarDetalhes.precisaMotivo) dados.motivo = formDetalhes.elements.motivo.value;
    if (alterarDetalhes.classificar) dados.classificacao = formDetalhes.elements.classificacao.value;
    salvar(formDetalhes, alterarDetalhes.caminho, dados, 'Registro atualizado.');
  });
  element('detalhes-voltar').addEventListener('click', () => {
    if (dialogDetalhes.dataset.salvando) return;
    limparAcaoDetalhes();
    acoesDetalhes.querySelector('button').focus();
  });
  area.querySelectorAll('dialog').forEach((dialog) => {
    dialog.addEventListener('cancel', (evento) => {
      if (dialog.dataset.salvando) evento.preventDefault();
    });
    dialog.querySelector('[data-fechar]').addEventListener('click', () => {
      if (!dialog.dataset.salvando) dialog.close();
    });
  });

  if (window.FullCalendar) {
    calendario = new FullCalendar.Calendar(element('calendario'), {
      locale: 'pt-br', timeZone: fuso,
      // O pacote local exibe horários sem deslocamento. Envie a hora local também para o botão Hoje.
      now: () => {
        const agora = new Date();
        return `${formatoDataLocal.format(agora)}T${formatoHoraLocal.format(agora)}`;
      },
      initialView: window.matchMedia('(max-width: 620px)').matches ? 'listMonth' : 'dayGridMonth',
      height: 'auto', fixedWeekCount: false, dayMaxEvents: 3,
      views: {timeGridWeek: {height: 520, scrollTime: '07:00:00'}},
      headerToolbar: {left: 'prev,next today', center: 'title', right: 'dayGridMonth,timeGridWeek,listMonth'},
      buttonIcons: false,
      buttonText: {prev: 'Anterior', next: 'Próximo', today: 'Hoje', month: 'Mês', week: 'Semana', list: 'Lista'},
      eventTimeFormat: {hour: '2-digit', minute: '2-digit', hour12: false},
      events: carregarEventos,
      dateClick: ({dateStr}) => abrirFormulario(formOcorrencia, dateStr.slice(0, 10)),
      eventClick: ({event}) => abrirOcorrencia(event.extendedProps.ocorrencia),
      eventDidMount: ({el, event}) => {
        el.tabIndex = 0;
        if (el.tagName === 'A') el.setAttribute('role', 'button');
        const ocorrencia = event.extendedProps.ocorrencia;
        el.setAttribute('aria-label', `${event.title}, ${dataExibida(ocorrencia.data)}, ${horarioOcorrencia(ocorrencia)}`);
        el.addEventListener('keydown', (tecla) => {
          if (tecla.key !== 'Enter' && tecla.key !== ' ') return;
          tecla.preventDefault();
          abrirOcorrencia(ocorrencia);
        });
      },
    });
    calendario.render();
  } else {
    status(element('calendario-retorno'), 'Calendário indisponível. Recarregue a página para tentar novamente.', true);
  }
  carregarPainel();
})();
