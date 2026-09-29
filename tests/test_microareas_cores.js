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
const comPartes = [
  {id_microarea:10, id_localidade:1, quarteiroes:[], partes:[{geometry:poligono(10, '0012', -49.3).geometry}]},
  {id_microarea:11, id_localidade:1, quarteiroes:[], partes:[{geometry:poligono(11, '0013', -49.2989).geometry}]},
];
assert.deepEqual([...vizinhanca(comPartes, [])?.get('10')], ['11'],
  'Lados parciais vizinhos também precisam receber cores contrastantes');
const cores = atribuir(registros, features, 1234);
assert.equal(CORES.length, 37);
assert.equal(new Set(CORES).size, CORES.length);
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
assert.ok(new Set(Object.values(gradeCores)).size >= 13,
  'A paleta ampliada deve usar mais cores sem sacrificar contraste entre vizinhas');
for (const [id, proximas] of gradeVizinhos) {
  for (const vizinha of proximas) {
    assert.notEqual(gradeCores[id], gradeCores[vizinha]);
    assert.ok(diferenca(gradeCores[id], gradeCores[vizinha]) >= 25,
      `${id}/${vizinha}: ${diferenca(gradeCores[id], gradeCores[vizinha]).toFixed(1)}`);
  }
}
const combinacoes = new Set(Array.from({length:12}, (_, indice) =>
  JSON.stringify(atribuir(grade, quadras, indice + 1, gradeVizinhos))));
assert.ok(combinacoes.size >= 10, 'Embaralhar deve oferecer várias combinações distintas');
const dispersas = grade.map((r, indice) => poligono(r.id_microarea, r.quarteiroes[0],
  -49.30 + indice * .01));
assert.equal(new Set(Object.values(atribuir(grade, dispersas, 42))).size, grade.length,
  'Microáreas afastadas devem aproveitar cores sem repetição');
console.log('Cores de microáreas: vizinhança, contraste e variação OK.');
