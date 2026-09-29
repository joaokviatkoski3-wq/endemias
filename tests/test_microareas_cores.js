const assert = require('node:assert/strict');
const {atribuir, vizinhanca, diferenca, CORES} = require('../static/js/microareas_cores.js');

function poligono(id, quarteirao, lon, localidade=1, lat=-25.30) {
  return {type:'Feature', properties:{Localidade:localidade, id_quart:quarteirao}, geometry:{
    type:'Polygon', coordinates:[[[lon,lat],[lon+.001,lat],
      [lon+.001,lat-.001],[lon,lat-.001],[lon,lat]]],
  }};
}

const registros = [
  {id_microarea:1, id_localidade:1, quarteiroes:['0007','0011']},
  {id_microarea:2, id_localidade:1, quarteiroes:['0008']},
  {id_microarea:3, id_localidade:1, quarteiroes:['0009']},
  {id_microarea:4, id_localidade:1, quarteiroes:['0010']},
];
const features = [
  poligono(1,'0007',-49.3000), poligono(1,'0011',-49.3000),
  poligono(2,'0008',-49.2989), poligono(3,'0009',-49.2978),
  poligono(4,'0010',-49.2700),
];
const vizinhos = vizinhanca(registros, features);
assert.deepEqual([...vizinhos.get('1')].sort(), ['2','3']);
assert.deepEqual([...vizinhos.get('4')], []);
const cores = atribuir(registros, features, 1234);
assert.deepEqual(atribuir(registros, features, 1234), cores);
assert.deepEqual(atribuir(registros, features, 1234, vizinhos), cores);
for (const [id, proximas] of vizinhos) {
  for (const vizinha of proximas) {
    assert.notEqual(cores[id], cores[vizinha]);
    assert.ok(diferenca(cores[id], cores[vizinha]) > 40,
      `Microáreas próximas ${id} e ${vizinha} ficaram com cores parecidas`);
  }
}
assert.ok(Object.values(cores).every(cor => CORES.includes(cor)));
assert.notDeepEqual(atribuir(registros, features, 9876), cores);

const grade = Array.from({length:25}, (_, indice) => ({
  id_microarea:indice + 1, id_localidade:1, quarteiroes:[String(indice + 1)],
}));
const quadras = grade.map((r, indice) => poligono(r.id_microarea, r.quarteiroes[0],
  -49.30 + (indice % 5) * .0011, 1, -25.30 - Math.floor(indice / 5) * .0011));
const gradeVizinhos = vizinhanca(grade, quadras);
const gradeCores = atribuir(grade, quadras, 234, gradeVizinhos);
for (const [id, proximas] of gradeVizinhos) {
  for (const vizinha of proximas) assert.notEqual(gradeCores[id], gradeCores[vizinha]);
}
console.log('Cores de microáreas: vizinhança, contraste e variação OK.');
