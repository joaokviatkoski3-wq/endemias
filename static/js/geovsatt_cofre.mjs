const encoder = new TextEncoder();
const decoder = new TextDecoder();
const nomeDoBanco = 'geovsatt-campo';
const armazenamento = 'pacotes';
const chaveLocal = 'mapa';

async function chaveDaSenha(senha, sal) {
  const entrada = await crypto.subtle.importKey('raw', encoder.encode(senha), 'PBKDF2', false, ['deriveKey']);
  return crypto.subtle.deriveKey({name: 'PBKDF2', hash: 'SHA-256', iterations: 600000, salt: sal},
    entrada, {name: 'AES-GCM', length: 256}, false, ['encrypt', 'decrypt']);
}

function parametros(registro, iv, tipo) {
  const additionalData = encoder.encode(JSON.stringify([registro.formato, registro.id, registro.usuario,
    registro.criado_em, registro.valido_ate, tipo]));
  return {name: 'AES-GCM', iv, additionalData};
}

async function criptografar(registro, chave, bytes, tipo) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  return {iv, conteudo: await crypto.subtle.encrypt(parametros(registro, iv, tipo), chave, bytes)};
}

async function descriptografar(registro, chave, protegido, tipo) {
  return crypto.subtle.decrypt(parametros(registro, protegido.iv, tipo), chave, protegido.conteudo);
}

export function decodificarPacote(bytes) {
  const dados = JSON.parse(decoder.decode(bytes));
  const inicio = Date.parse(dados.criado_em);
  const fim = Date.parse(dados.valido_ate);
  if (dados.formato !== 1 || !Number.isSafeInteger(dados.usuario) || !Array.isArray(dados.camadas)
      || !(dados.camadas.length || dados.ortofotos?.length) || !dados.dados || !(inicio < fim)) {
    throw Error('Formato da cópia offline incompatível.');
  }
  return dados;
}

export async function criarRegistro(bytes, dados, senha, projetos = []) {
  if (senha.length < 10 || senha.length > 128) throw Error('Use uma senha de 10 a 128 caracteres.');
  const registro = {formato: 1, id: crypto.randomUUID(), usuario: dados.usuario, tamanho: bytes.byteLength,
    criado_em: dados.criado_em, valido_ate: dados.valido_ate, sal: crypto.getRandomValues(new Uint8Array(16))};
  const chave = await chaveDaSenha(senha, registro.sal);
  registro.pacote = await criptografar(registro, chave, bytes, 'mapa');
  if (projetos.length) registro.projetos = await protegerProjetos(registro, chave, projetos);
  return registro;
}

export async function abrirRegistro(registro, senha) {
  if (registro.formato !== 1) throw Error('Baixe uma nova cópia do mapa para esta versão do GeoVSATT.');
  const chave = await chaveDaSenha(senha, registro.sal);
  try {
    const bytes = await descriptografar(registro, chave, registro.pacote, 'mapa');
    const dados = decodificarPacote(bytes);
    if (dados.usuario !== registro.usuario || dados.valido_ate !== registro.valido_ate) throw Error();
    return {chave, dados};
  } catch {
    throw Error('A senha está incorreta ou a cópia está corrompida.');
  }
}

export async function lerProjetos(registro, chave) {
  if (!registro.projetos) return [];
  const bytes = await descriptografar(registro, chave, registro.projetos, 'projetos');
  return JSON.parse(decoder.decode(bytes));
}

export function protegerProjetos(registro, chave, projetos) {
  return criptografar(registro, chave, encoder.encode(JSON.stringify(projetos)), 'projetos');
}

async function usarBanco(modo, operar) {
  const banco = await new Promise((resolve, reject) => {
    const consulta = indexedDB.open(nomeDoBanco, 1);
    consulta.onupgradeneeded = () => consulta.result.createObjectStore(armazenamento);
    consulta.onsuccess = () => resolve(consulta.result);
    consulta.onerror = () => reject(consulta.error);
    consulta.onblocked = () => reject(Error('Feche as outras janelas do GeoVSATT e tente novamente.'));
  });
  try {
    return await new Promise((resolve, reject) => {
      const tx = banco.transaction(armazenamento, modo);
      let resultado;
      let erro;
      tx.oncomplete = () => resolve(resultado);
      tx.onabort = () => reject(erro || tx.error || Error('Não foi possível gravar a cópia.'));
      const loja = tx.objectStore(armazenamento);
      const atual = loja.get(chaveLocal);
      atual.onsuccess = () => {
        try {
          resultado = operar(loja, atual.result);
        } catch (falha) {
          erro = falha;
          tx.abort();
        }
      };
    });
  } finally {
    banco.close();
  }
}

export const lerRegistro = () => usarBanco('readonly', (loja, atual) => atual);

export function guardarRegistro(esperado, revisao, registro) {
  return usarBanco('readwrite', (loja, atual) => {
    if (atual?.id !== esperado || (atual?.revisao || 0) !== revisao) {
      throw Error('A cópia foi alterada em outra janela. Abra o menu novamente.');
    }
    loja.put(registro, chaveLocal);
  });
}

export function gravarProjetos(id, revisao, projetos) {
  return usarBanco('readwrite', (loja, atual) => {
    if (atual?.id !== id || (atual.revisao || 0) !== revisao) {
      throw Error('As composições mudaram em outra janela. Abra a cópia novamente.');
    }
    loja.put({...atual, projetos, revisao: revisao + 1}, chaveLocal);
  });
}

export function removerRegistro(esperado = null) {
  return usarBanco('readwrite', (loja, atual) => {
    if (esperado === null || atual?.id === esperado) loja.delete(chaveLocal);
  });
}

export function bloquearRegistro(esperado) {
  return usarBanco('readwrite', (loja, atual) => {
    if (atual?.id === esperado) loja.put({...atual, bloqueado: true, revisao: (atual.revisao || 0) + 1}, chaveLocal);
  });
}
