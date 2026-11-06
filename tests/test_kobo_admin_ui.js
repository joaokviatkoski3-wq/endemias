// Regressão: operação de admin não pode tentar ler/salvar campos técnicos ausentes.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('static/js/processar.js','utf8');
const save=source.slice(source.indexOf('async function salvarKoboConfig()'),source.indexOf('async function testarKobo()'));
let requests=0,errors=0;
const context=vm.createContext({document:{getElementById:()=>null},fetch:()=>{requests++;throw Error('Não chamar configuração');},setKoboStatus:()=>{errors++;},toast:()=>{errors++;}});
vm.runInContext(save,context);
(async()=>{await context.salvarKoboConfig();assert.equal(requests,0);assert.equal(errors,0);
 console.log('OK: admin mantém configuração existente sem tentativa técnica ou falso erro.');
})().catch(e=>{console.error(e);process.exitCode=1;});
