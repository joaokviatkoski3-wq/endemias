"""Reenvio do piloto de campo sem DDL e sem confiar no relógio do aparelho."""
import hashlib
import json
from uuid import UUID
from datetime import date

META = "_captura_campo"


class ConflitoCampo(ValueError):
    def __init__(self, mensagem, codigo="conflito"):
        super().__init__(mensagem)
        self.codigo = codigo


def preparar(tipo, payload, uuid_cliente, status, captura):
    if META in payload:
        raise ValueError("Metadados de recebimento não podem ser enviados no formulário.")
    if captura is None:
        return None
    if tipo != "rg_atualizacao" or not isinstance(captura, dict) or set(captura) != {"versao", "revisao", "dispositivo"}:
        raise ValueError("Protocolo de campo inválido.")
    if captura["versao"] != 1 or isinstance(captura["versao"], bool):
        raise ValueError("Atualize o aplicativo antes de enviar esta versão de formulário.")
    revision = captura["revisao"]
    if not isinstance(revision, int) or isinstance(revision, bool) or not 1 <= revision <= 1_000_000_000:
        raise ValueError("Revisão do formulário inválida.")
    try:
        identifier = str(UUID(str(uuid_cliente)))
        device = str(UUID(str(captura["dispositivo"])))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("Identificação do formulário ou aparelho inválida.") from exc
    if identifier != uuid_cliente:
        raise ValueError("Identificação do formulário inválida.")
    encoded = json.dumps({"payload": payload, "status": status}, ensure_ascii=False, sort_keys=True, allow_nan=False)
    if len(encoded.encode("utf-8")) > 2 * 1024 * 1024:
        raise ValueError("Formulário muito grande. Divida o levantamento em mais envios.")
    return {"versao": 1, "revisao": revision, "dispositivo": device,
            "hash": hashlib.sha256(encoded.encode("utf-8")).hexdigest()}


def validar_rg(payload, status):
    """Limites do piloto; rascunhos aceitam campos ainda não preenchidos."""
    from app_core.registro_geografico import TIPOS
    if not isinstance(payload, dict):
        raise ValueError("Conteúdo de campo inválido.")
    localidade = payload.get("id_localidade")
    if not isinstance(localidade, int) or isinstance(localidade, bool) or localidade < 1:
        raise ValueError("Localidade inválida.")
    def texto(value, limite):
        return value is None or isinstance(value, str) and len(value) <= limite
    if not isinstance(payload.get("quarteirao"), str) or not payload["quarteirao"].strip() or len(payload["quarteirao"]) > 40:
        raise ValueError("Quarteirão inválido.")
    if not texto(payload.get("localidade"), 250):
        raise ValueError("Nome de localidade inválido.")
    if payload.get("data_atualizacao"):
        try:
            date.fromisoformat(payload["data_atualizacao"])
        except (ValueError, TypeError):
            raise ValueError("Data inválida.") from None
    lines = payload.get("linhas")
    if not isinstance(lines, list) or len(lines) > 3000:
        raise ValueError("Limite de 3.000 imóveis por formulário.")
    if status == "enviado" and (not lines or not payload.get("data_atualizacao") or not payload.get("agentes_ids")):
        raise ValueError("Confira os imóveis, a data e os agentes antes de enviar.")
    for line in lines:
        if not isinstance(line, dict) or any(not texto(line.get(k), n) for k, n in (("logradouro",250),("numero",30),("sequencia",30),("lado",10),("observacao",2000))):
            raise ValueError("Dados de imóvel inválidos.")
        units = line.get("condominio", 0)
        if not isinstance(line.get("tipo"), str) or line["tipo"] not in TIPOS or not isinstance(units, int) or isinstance(units, bool) or not 0 <= units <= 10000:
            raise ValueError("Tipo ou quantidade de unidades inválida.")
        if status == "enviado" and any(not isinstance(line.get(k), str) or not line[k].strip() for k in ("logradouro", "numero")):
            raise ValueError("Confira o logradouro e o número dos imóveis antes de enviar.")
    editor = payload.get("_editor")
    if editor is not None:
        if not isinstance(editor, dict) or editor.get("versao") != 1 or not isinstance(editor.get("lados"), list) or not 1 <= len(editor["lados"]) <= 100:
            raise ValueError("Editor de campo inválido.")
        count = 0
        for side in editor["lados"]:
            if not isinstance(side, dict) or not isinstance(side.get("lado"), str) or len(side["lado"]) > 10 or not isinstance(side.get("logradouros"), list) or not 1 <= len(side["logradouros"]) <= 100:
                raise ValueError("Lados do formulário inválidos.")
            for road in side["logradouros"]:
                if not isinstance(road, dict) or not isinstance(road.get("logradouro"), str) or len(road["logradouro"]) > 250 or not isinstance(road.get("imoveis"), list) or not 1 <= len(road["imoveis"]) <= 3000:
                    raise ValueError("Logradouros do formulário inválidos.")
                count += len(road["imoveis"])
                for house in road["imoveis"]:
                    if not isinstance(house, dict) or any(not isinstance(house.get(k), str) or len(house[k]) > n for k,n in (("numero",30),("sequencia",30),("observacao",2000))) or not isinstance(house.get("tipo"), str) or house["tipo"] not in TIPOS:
                        raise ValueError("Rascunho de imóvel inválido.")
        if count > 3000:
            raise ValueError("Limite de 3.000 imóveis por formulário.")


def conferir(existente, metadata):
    old = json.loads(existente["payload_json"] or "{}").get(META)
    if old is None and metadata is None:
        return False
    if old is None:
        raise ConflitoCampo("Este envio pertence à versão anterior. Confira-o antes de iniciar uma nova captura.")
    if not isinstance(old, dict) or not isinstance(old.get("revisao"), int) or not isinstance(old.get("hash"), str):
        raise ConflitoCampo("O recebimento anterior precisa de conferência pelo gestor.")
    if metadata is None or old.get("dispositivo") != metadata["dispositivo"]:
        raise ConflitoCampo("Este envio foi alterado em outro contexto. Confira o registro recebido.")
    if old["revisao"] == metadata["revisao"]:
        if old["hash"] == metadata["hash"]:
            return True  # Confirma a repetição, mesmo depois de revisão/oficialização.
        raise ConflitoCampo("A mesma revisão possui dados diferentes. Preserve o rascunho e confira o envio.")
    if old["revisao"] > metadata["revisao"]:
        raise ConflitoCampo("O sistema já recebeu uma revisão mais recente. O rascunho foi preservado.", "revisao_antiga")
    return False
