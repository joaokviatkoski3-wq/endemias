// Executa o script da tela renderizada com uma base sintética isolada.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {spawnSync}=require('node:child_process');
const root=path.resolve(__dirname,'..');
const python=spawnSync('python',['-c',[
  'from tests.test_liraa_integracao import IntegracaoTests',
  't=IntegracaoTests();t.setUp()',
  'try:',
  ' t.importar()',
  " r=t.client().get('/laboratorio/lancamentos?tipo=LIRAA')",
  ' assert r.status_code==200',
  ' print(r.get_data(as_text=True))',
  'finally:t.doCleanups()',
].join('\n')],{cwd:root,encoding:'utf8',env:{...process.env,PYTHONIOENCODING:'utf-8'},timeout:30000});
assert.equal(python.status,0,python.stderr);
const html=python.stdout;
assert.equal((html.match(/name="aegypt_larvas"/g)||[]).length,1);
assert.ok(!html.includes('lab-module-liraa'));
let script=[...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(m=>m[1]).find(s=>s.includes('let labPendentes'));
assert.ok(script,'Script do laboratório presente');
script=script.replace(/^carregarPendentes\(\);$/gm,'').replace(/^carregarOviLab\(false\);$/gm,'').replace(/^if\(new URLSearchParams\(location.search\).*$/gm,'');
const elements=new Map(),fields=new Map(),requests=[];
function element(id){
  if(!elements.has(id))elements.set(id,{value:'',dataset:{},hidden:false,disabled:false,open:false,
    style:{},classList:{toggle(){}},addEventListener(){},setAttribute(n){if(n==='hidden')this.hidden=true;},
    removeAttribute(n){if(n==='hidden')this.hidden=false;},showModal(){this.open=true;},close(){this.open=false;},reset(){}});
  return elements.get(id);
}
const document={getElementById:element,querySelectorAll:()=>[],querySelector(selector){
  const name=selector.match(/\[name="([^"]+)"\]/)?.[1];
  if(!fields.has(name)){const parent={hidden:false};fields.set(name,{value:0,disabled:false,max:'100000',closest:()=>parent});}
  return fields.get(name);
}};
const context=vm.createContext({document,URLSearchParams,location:{search:'?tipo=LIRAA&ciclo=4'},
  escapeAttr:v=>String(v??''),fmtDate:v=>v||'',toast(){},console,
  apiGet:async()=>({pendentes:[],registros:[]}),
  apiPost:async(url,body)=>{requests.push({url,body});return {ok:true};},
  setTimeout,clearTimeout});
vm.runInContext(script,context);
async function run(){
  element('lab-filtro-tipo').value='LIRAA';
  assert.equal(vm.runInContext('parametrosLab().get("ciclo")',context),'4');
  vm.runInContext("labPendentes=[{id_coleta:'liraa-t-1',tipo:'LIRAA',num_tubo:'100'}];abrirLancamento(0)",context);
  assert.equal(fields.get('aegypt_exuvias').disabled,true);
  assert.equal(fields.get('aegypt_exuvias').closest().hidden,true);
  assert.equal(fields.get('aegypt_larvas').disabled,false);
  assert.equal(fields.get('aegypt_larvas').max,'1000000');
  fields.get('aegypt_larvas').value=2;
  await vm.runInContext('confirmarSalvarResultado()',context);
  assert.equal(requests[0].url,'/api/laboratorio/lancamentos/liraa-t-1/resultado');
  assert.equal(requests[0].body.aegypt_larvas,2);
  vm.runInContext("labPendentes=[{id_coleta:'rotina',tipo:'TB'}];abrirLancamento(0)",context);
  assert.equal(fields.get('aegypt_exuvias').disabled,false);
  assert.equal(fields.get('aegypt_exuvias').closest().hidden,false);
  assert.equal(fields.get('aegypt_larvas').max,'100000');
  vm.runInContext("labHistorico=[{editavel:true,tipo:'LIRAA',id_coleta:'liraa-t-1',id_resultado:-1,atualizado_em:'versao-1'}];abrirEdicaoResultado(0)",context);
  assert.equal(element('form-laboratorista-wrap').hidden,true);
  await vm.runInContext('confirmarSalvarResultado()',context);
  assert.equal(requests[1].url,'/api/laboratorio/lancamentos/resultados/-1/editar');
  assert.equal(requests[1].body.versao,'versao-1');
  assert.equal(requests[1].body.id_laboratorista,undefined);
  console.log('OK: fila única, campos LIRAa, retorno à rotina e versão da correção.');
}
run().catch(err=>{console.error(err);process.exitCode=1;});
