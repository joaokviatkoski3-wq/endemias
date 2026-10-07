const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source=fs.readFileSync(path.join(__dirname,'../static/js/liraa_plano_campo.js'),'utf8');
const box={dataset:{url:'/api/liraa/ciclos/1/plano-mapa?localidade=2'}};
const status={textContent:''};
const ciclo={addEventListener:(event,fn)=>ciclo.changed=fn};
const estrato={value:'99'};
let requests=0, layers=0, invalidations=0;
const feature={properties:{estrato:2,quarteirao:'408.1',Localidade:'São Venâncio <script>',imoveis_rg:null,meta_rg:null,fracao:.2}};
const L={map:()=>({setView(){return this},invalidateSize(){invalidations++},fitBounds(){}}),
  tileLayer:()=>({addTo(){}}), control:{layers:()=>({addTo(){}})},
  geoJSON:(data,options)=>{
    layers++;
    let popup='',label='';
    options.onEachFeature(data.features[0], {bindTooltip(value){label=value},bindPopup(value){popup=value}});
    assert.equal(label,'408.1');
    assert.ok(popup.includes('&lt;script&gt;'));
    assert.ok(popup.includes('Sem RG'));
    assert.equal(options.style(feature).color,'#dc2626');
    return {addTo(){return this},getBounds:()=>({isValid:()=>true})};
  }};
const ctx={window:{L},L,document:{getElementById:id=>id==='liraa-campo-mapa'?box:status,
  querySelectorAll:()=>[{querySelector:selector=>selector.includes('ciclo')?ciclo:estrato}]},
  fetch:async url=>{requests++;assert.equal(url,box.dataset.url);return {ok:true,json:async()=>({features:[feature]})}}};
vm.runInNewContext(source,ctx);
(async()=>{
  ciclo.changed();
  assert.equal(estrato.value,'');
  await ctx.window.LiraaPlanoCampo.iniciar();
  assert.equal(status.textContent,'Clique em um quarteirão para conferir seus dados.');
  await ctx.window.LiraaPlanoCampo.iniciar();
  assert.equal(requests,1);
  assert.equal(layers,1);
  assert.equal(invalidations,2);
  console.log('OK: plano de campo, filtros, cores, etiquetas e escape de HTML.');
})().catch(error=>{console.error(error);process.exitCode=1});
