/* Território compartilhado; dados operacionais exclusivamente ambientais. */
(() => {
  const status = document.getElementById('mapa-status');
  const form = document.getElementById('filtros-mapa');
  const catalog = new Map(JSON.parse(document.getElementById('mapa-localidades').textContent).map(r=>[String(r.id_localidade),r.nome]));
  const map = L.map('mapa-ambiental').setView([-25.32,-49.31],12);
  const tile = service => L.tileLayer(`https://server.arcgisonline.com/ArcGIS/rest/services/${service}/MapServer/tile/{z}/{y}/{x}`,{maxZoom:19,attribution:'Tiles &copy; Esri — Esri, Maxar, Earthstar Geographics, GIS User Community'});
  const streets = tile('World_Street_Map'), satellite = tile('World_Imagery');
  const reference = tile('Reference/World_Boundaries_and_Places');
  const satelliteGroup = L.layerGroup([satellite,reference]);
  streets.addTo(map);
  L.control.layers({'Ruas':streets,'Satélite':satelliteGroup},{},{collapsed:false}).addTo(map);
  L.control.scale({imperial:false}).addTo(map);
  function labelVisibility(){map.getContainer().classList.toggle('mapa-sem-etiquetas',map.getZoom()<15);}
  map.on('zoomend',labelVisibility);labelVisibility();
  for(const base of [streets,satellite,reference])base.on('tileerror',()=>{
    document.getElementById('mapa-base-status').textContent='Algumas imagens de fundo não carregaram. Confira a internet ou alterne a base; quarteirões e registros continuam disponíveis.';
  });
  const legend=L.control({position:'bottomright'});
  legend.onAdd=()=>{
    const node=L.DomUtil.create('div','ambiental-map-legend');
    const heading=document.createElement('strong');heading.textContent='Visitas por quarteirão';node.append(heading);
    for(const [color,label] of [['#d7dfe0','Sem registros'],['#9bc6bc','1 a 4'],['#469482','5 a 19'],['#176456','20 ou mais']]){
      const row=document.createElement('div'),swatch=document.createElement('i');swatch.style.background=color;
      row.append(swatch,document.createTextNode(label));node.append(row);
    }
    L.DomEvent.disableClickPropagation(node);return node;
  };legend.addTo(map);
  let geometry, layer, rows=[], requestNumber=0, activeController;
  const labels=document.getElementById('mapa-etiquetas');
  const onlyRecords=document.getElementById('mapa-com-registros');
  const opacity=document.getElementById('mapa-opacidade');
  const normal = value => String(value??'').replace(/^0+(?=\d)/,'');
  const key = (loc,q) => `${normal(loc)}:${normal(q)}`;
  const localName = p => catalog.get(normal(p.Localidade)) || p.Localidade_nome || `Localidade ${p.Localidade}`;
  const color = n => n>=20?'#176456':n>=5?'#469482':n>0?'#9bc6bc':'#d7dfe0';
  function fit(){if(layer&&layer.getBounds().isValid())map.fitBounds(layer.getBounds(),{padding:[24,24],maxZoom:17});}
  function draw(enquadrar=true){
    if(!geometry)return;
    const totals=new Map();let total=0;
    for(const row of rows){
      total+=row.registros;
      if(row.id_localidade==null||row.quarteirao==null)continue;
      const id=key(row.id_localidade,row.quarteirao);totals.set(id,(totals.get(id)||0)+row.registros);
    }
    const locality=form.elements.localidade.value, block=form.elements.quarteirao.value;
    const matching=new Set();let features=[];
    for(const feature of geometry.features){
      const p=feature.properties,id=key(p.Localidade,p.id_quart),count=totals.get(id)||0;
      if(locality&&localName(p)!==locality)continue;
      if(block&&normal(p.id_quart)!==normal(block))continue;
      if(count)matching.add(id);
      if(onlyRecords.checked&&!count)continue;
      features.push(feature);
    }
    if(layer)map.removeLayer(layer);
    layer=L.geoJSON({type:'FeatureCollection',features},{
      style:f=>({color:'#446f69',weight:1,fillColor:color(totals.get(key(f.properties.Localidade,f.properties.id_quart))||0),fillOpacity:Number(opacity.value)/100}),
      onEachFeature(f,polygon){
        const p=f.properties,count=totals.get(key(p.Localidade,p.id_quart))||0;
        const popup=document.createElement('div');
        const title=document.createElement('strong');title.textContent=localName(p);popup.append(title);
        const text=document.createElement('p');text.textContent=`Quarteirão ${p.id_quart} · ${count} visita(s) ambientais na consulta`;popup.append(text);polygon.bindPopup(popup);
        if(labels.checked){const label=document.createElement('span');label.textContent=`Q ${p.id_quart}`;polygon.bindTooltip(label,{permanent:true,direction:'center',className:'ambiental-map-label'});}
        polygon.on('mouseover',()=>polygon.setStyle({weight:3}));polygon.on('mouseout',()=>polygon.setStyle({weight:1}));
      },
    }).addTo(map);
    const located=[...matching].reduce((sum,id)=>sum+(totals.get(id)||0),0);
    status.textContent=`${total} registro(s) no período. ${matching.size} quarteirão(ões) com registros na camada. ${Math.max(0,total-located)} sem correspondência territorial. ${features.length} polígono(s) exibido(s).`;
    if(!features.length)status.textContent+=' Nenhum quarteirão corresponde à seleção; altere os filtros.';
    if(enquadrar)fit();
  }
  async function load(){
    const current=++requestNumber;
    if(activeController)activeController.abort();activeController=new AbortController();
    status.textContent='Consultando registros ambientais…';
    try{
      const response=await fetch('/api/mapa?'+new URLSearchParams(new FormData(form)),{signal:activeController.signal});
      if(!response.ok)throw new Error();
      const data=await response.json();if(current!==requestNumber)return;rows=data.linhas;draw();
    }catch(error){if(error.name!=='AbortError')status.textContent='Não foi possível consultar os dados. Confira a conexão e os filtros.';}
  }
  form.addEventListener('submit',e=>{e.preventDefault();load();});
  form.addEventListener('reset',()=>setTimeout(load,0));
  labels.addEventListener('change',()=>draw(false));onlyRecords.addEventListener('change',()=>draw());
  opacity.addEventListener('input',()=>{if(layer)layer.setStyle({fillOpacity:Number(opacity.value)/100});});
  document.getElementById('mapa-enquadrar').addEventListener('click',fit);
  fetch('/api/ambiental/territorio').then(r=>{if(!r.ok)throw new Error();return r.json();})
    .then(data=>{geometry=data;load();}).catch(()=>{status.textContent='Não foi possível carregar a base territorial.';});
})();
