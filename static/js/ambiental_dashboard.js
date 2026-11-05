/* O servidor aplica os mesmos filtros aos indicadores, relatório e exportações. */
(() => {
  const data = JSON.parse(document.getElementById('ambiental-dados').textContent);
  if (!data.registros || typeof Chart === 'undefined') return;
  const palette = ['#1b786f','#3b73a3','#c19034','#9b5f77','#647e91','#66814e'];
  const color = getComputedStyle(document.documentElement).getPropertyValue('--text2').trim() || '#4b5563';
  function chart(id, type, labels, datasets, horizontal = false) {
    const canvas = document.getElementById(id);
    if (!canvas) return;
    canvas._chart = new Chart(canvas, {
      type, data: {labels, datasets},
      options: {
        responsive:true, maintainAspectRatio:false, indexAxis:horizontal?'y':'x',
        plugins:{legend:{display:type==='doughnut'||datasets.length>1,labels:{color,boxWidth:12}},tooltip:{enabled:true}},
        ...(type==='doughnut' ? {cutout:'62%'} : {
          scales:{
            x:{ticks:{color,precision:0},grid:{display:!horizontal},beginAtZero:horizontal},
            y:{beginAtZero:!horizontal,ticks:{color,precision:0},grid:{display:horizontal}},
          },
        }),
      },
    });
  }
  const sources = Object.keys(data.totais);
  chart('ambiental-evolucao','bar',data.por_mes.map(r=>r.mes.split('-').reverse().join('/')),sources.map((s,i)=>({label:s,data:data.por_mes.map(r=>r[s]),backgroundColor:palette[i],borderRadius:3})));
  chart('ambiental-fontes','doughnut',sources,[{data:Object.values(data.totais),backgroundColor:palette}]);
  for (const [id,rows] of [['ambiental-localidades',data.por_localidade],['ambiental-situacao',data.por_situacao],['ambiental-animais',data.por_tipo_animal]]) {
    const top=rows.slice(0,10);
    // Reúne demais categorias para o gráfico continuar somando o total exibido.
    if(rows.length>10)top.push({nome:'Demais categorias',registros:rows.slice(10).reduce((sum,r)=>sum+r.registros,0)});
    chart(id,'bar',top.map(r=>r.nome),[{label:'Visitas',data:top.map(r=>r.registros),backgroundColor:palette[0],borderRadius:3}],true);
  }
})();
