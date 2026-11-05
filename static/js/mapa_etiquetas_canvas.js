/* Uma única superfície para etiquetas: sem tooltip/DOM por quarteirão.
 * API Leaflet 1.9.4: panes, projeção container/layer e eventos de movimento.
 */
(() => {
  'use strict';
  window.VSATTMapLabels = function(map, {status, minZoom=15, maxLabels=300}={}) {
    const canvas=L.DomUtil.create('canvas','ambiental-labels-canvas leaflet-zoom-hide');
    canvas.setAttribute('aria-hidden','true');
    canvas.hidden=true;
    map.getPane('tooltipPane').append(canvas);
    let items=[], enabled=false, frame=null, destroyed=false;

    function hide(message='') {
      canvas.hidden=true;
      canvas.dataset.labelCount='0';
      if(status)status.textContent=message;
    }
    function render() {
      frame=null;
      if(destroyed)return;
      if(!enabled){hide();return;}
      if(map.getZoom()<minZoom){hide(`Amplie o mapa para ver as etiquetas (zoom ${minZoom} ou maior).`);return;}
      const size=map.getSize(), bounds=map.getBounds().pad(.05);
      const ratio=Math.min(window.devicePixelRatio||1,2);
      canvas.width=Math.ceil(size.x*ratio);canvas.height=Math.ceil(size.y*ratio);
      canvas.style.width=size.x+'px';canvas.style.height=size.y+'px';
      L.DomUtil.setPosition(canvas,map.containerPointToLayerPoint([0,0]));
      const ctx=canvas.getContext('2d');
      if(!ctx){hide('Etiquetas indisponíveis neste navegador.');return;}
      ctx.setTransform(ratio,0,0,ratio,0,0);
      ctx.font='600 11px system-ui, sans-serif';
      ctx.textAlign='center';ctx.textBaseline='middle';
      const candidates=[];
      for(const item of items) {
        if(!bounds.contains(item.position))continue;
        const point=map.latLngToContainerPoint(item.position);
        if(point.x<0||point.y<0||point.x>size.x||point.y>size.y)continue;
        candidates.push({...item,point,distance:(point.x-size.x/2)**2+(point.y-size.y/2)**2});
      }
      candidates.sort((a,b)=>a.distance-b.distance);
      const occupied=new Map(), seen=new Set();
      let count=0;
      for(const item of candidates) {
        if(seen.has(item.id))continue;
        const width=Math.min(ctx.measureText(item.text).width+10,160), p=item.point;
        const rect={left:p.x-width/2-3,right:p.x+width/2+3,top:p.y-12,bottom:p.y+12};
        const cells=[];let overlaps=false;
        for(let x=Math.floor(rect.left/64);x<=Math.floor(rect.right/64);x++) {
          for(let y=Math.floor(rect.top/32);y<=Math.floor(rect.bottom/32);y++) {
            const cell=x+':'+y;cells.push(cell);
            if((occupied.get(cell)||[]).some(r=>rect.left<r.right&&rect.right>r.left&&rect.top<r.bottom&&rect.bottom>r.top))overlaps=true;
          }
        }
        if(overlaps)continue;
        for(const cell of cells){if(!occupied.has(cell))occupied.set(cell,[]);occupied.get(cell).push(rect);}
        ctx.fillStyle='rgba(255,255,255,.92)';
        ctx.fillRect(p.x-width/2,p.y-9,width,18);
        ctx.strokeStyle='rgba(68,111,105,.5)';ctx.lineWidth=.5;
        ctx.strokeRect(p.x-width/2,p.y-9,width,18);
        ctx.fillStyle='#172b35';ctx.fillText(item.text,p.x,p.y,150);
        seen.add(item.id);count++;
        if(count>=maxLabels)break;
      }
      canvas.dataset.labelCount=String(count);
      canvas.dataset.visibleCandidates=String(candidates.length);
      canvas.hidden=count===0;
      if(status)status.textContent=count
        ? `${count} etiqueta(s) visível(is). Amplie para detalhar os quarteirões; até ${maxLabels} etiquetas por tela.`
        : 'Nenhum quarteirão na área visível.';
    }
    function schedule() {
      if(destroyed)return;
      if(frame!==null)cancelAnimationFrame(frame);
      frame=requestAnimationFrame(render);
    }
    function moving() {
      if(frame!==null){cancelAnimationFrame(frame);frame=null;}
      canvas.hidden=true;
    }
    function destroy() {
      destroyed=true;
      if(frame!==null)cancelAnimationFrame(frame);
      map.off('movestart zoomstart',moving);map.off('moveend zoomend resize',schedule);
      map.off('unload',destroy);canvas.remove();items=[];
    }
    map.on('movestart zoomstart',moving);map.on('moveend zoomend resize',schedule);
    map.on('unload',destroy);
    return {
      setItems(values){items=values.map(v=>({...v,text:String(v.text).slice(0,24)}));schedule();},
      setEnabled(value){enabled=Boolean(value);if(enabled)schedule();else hide();},
      destroy,
    };
  };
})();
