"""Trechos do RG e validação das geometrias desenhadas para microáreas."""

import hashlib
import json
import math

from app_core import db as db_core


def chave(parte):
    return (parte["id_localidade"], parte["quarteirao"], parte["logradouro"], parte["lado"])


def trechos_rg(conn, id_localidade, quarteirao):
    """Lados disponíveis; logradouro + lado são a identidade do trecho no RG."""
    rows = conn.execute("""SELECT TRIM(i.logradouro) AS logradouro,
        TRIM(i.lado) AS lado,
        COUNT(*) AS imoveis,
        SUM(CASE WHEN COALESCE(i.condominio,0)>0 THEN i.condominio ELSE 1 END) AS imoveis_reais,
        SUM(CASE WHEN i.tipo='R' THEN CASE WHEN COALESCE(i.condominio,0)>0 THEN i.condominio ELSE 1 END ELSE 0 END) AS residencias_reais,
        SUM(CASE WHEN i.tipo='R' AND COALESCE(i.condominio,0)<=0 THEN 1 ELSE 0 END) AS residencias_sem_condominio,
        SUM(CASE WHEN i.tipo='R' AND COALESCE(i.condominio,0)>0 THEN i.condominio ELSE 0 END) AS residencias_condominio
        FROM registro_geografico_imoveis i
        WHERE i.id_localidade=? AND i.quarteirao=? AND TRIM(COALESCE(i.lado,''))<>''
          AND COALESCE(i.tipo,'')<>'REF'
        GROUP BY TRIM(i.logradouro), TRIM(i.lado)
        ORDER BY TRIM(i.logradouro), TRIM(i.lado)""", (id_localidade, quarteirao)).fetchall()
    return [db_core.serialize_row(row) for row in rows]


def hash_base(geometry):
    raw = json.dumps(geometry, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def validar_geometria(geometry, outras):
    """Aceita desenho dentro ou fora da base; lados do mesmo Q não se sobrepõem."""
    try:
        from shapely.geometry import Polygon, shape, mapping
    except ImportError as exc:
        raise ValueError("Validação geográfica indisponível: instale Shapely 2.1.2 antes de usar partes de microáreas.") from exc
    if not isinstance(geometry, dict) or geometry.get("type") != "Polygon":
        raise ValueError("Desenhe um polígono para cada lado do quarteirão.")
    rings = geometry.get("coordinates")
    if not isinstance(rings, list) or len(rings) != 1 or not isinstance(rings[0], list) or not 4 <= len(rings[0]) <= 151:
        raise ValueError("O desenho precisa ter entre 3 e 150 vértices e não pode ter buracos.")
    for point in rings[0]:
        if (not isinstance(point, (list, tuple)) or len(point) != 2
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in point)
                or not (-180 <= point[0] <= 180 and -90 <= point[1] <= 90)):
            raise ValueError("O desenho contém coordenadas inválidas.")
    if rings[0][0] != rings[0][-1]:
        raise ValueError("Feche o desenho antes de salvar.")
    try:
        polygon = shape(geometry)
        siblings = [shape(item) for item in outras]
    except (TypeError, ValueError, KeyError) as exc:
        raise ValueError("Não foi possível interpretar a geometria desenhada.") from exc
    if not isinstance(polygon, Polygon) or not polygon.is_valid or polygon.area <= 0:
        raise ValueError("O desenho é vazio, cruzado ou geometricamente inválido.")
    if any(polygon.intersection(outro).area > 0 for outro in siblings):
        raise ValueError("O desenho se sobrepõe a outra parte desse quarteirão.")
    return mapping(polygon)


def preparar(conn, id_localidade, raw, geometrias, id_microarea=None):
    if not isinstance(raw, list) or len(raw) > 100:
        raise ValueError("Informe até 100 lados parciais por microárea.")
    preparados = []
    vistas = set()
    trechos = {}
    existentes = {}
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Parte do quarteirão inválida.")
        q = str(item.get("quarteirao") or "").strip()
        rua = str(item.get("logradouro") or "").strip()
        lado = str(item.get("lado") or "").strip()
        if not q or not rua or not lado or len(rua) > 250 or len(lado) > 50:
            raise ValueError("Informe quarteirão, logradouro e lado válidos.")
        key = (id_localidade, q, rua, lado)
        if key in vistas:
            raise ValueError("O mesmo lado foi selecionado mais de uma vez.")
        vistas.add(key)
        feature = geometrias.get((id_localidade, q))
        if not feature:
            raise ValueError(f"Quarteirão {q} não está na camada geográfica ativa.")
        base_hash = hash_base(feature["geometry"])
        if item.get("base_geometry_hash") and item["base_geometry_hash"] != base_hash:
            raise ValueError(f"O polígono oficial do quarteirão {q} mudou. Redesenhe {rua} · lado {lado} antes de salvar.")
        if q not in trechos:
            trechos[q] = {(t["logradouro"], t["lado"]) for t in trechos_rg(conn, id_localidade, q)}
        if (rua, lado) not in trechos[q]:
            raise ValueError(f"{rua} · lado {lado} não consta mais no RG do quarteirão {q}.")
        if q not in existentes:
            rows = conn.execute("""SELECT id_microarea, logradouro, lado, geometry_json
                FROM territorializacao_microarea_partes
                WHERE id_localidade=? AND quarteirao=? AND id_microarea<>?""",
                (id_localidade, q, id_microarea or 0)).fetchall()
            existentes[q] = [db_core.serialize_row(row) for row in rows]
        if any(row["logradouro"] == rua and row["lado"] == lado for row in existentes[q]):
            raise ValueError(f"{rua} · lado {lado} já pertence a outra microárea.")
        outras = [json.loads(row["geometry_json"]) for row in existentes[q]]
        outras += [p["geometry"] for p in preparados if p["quarteirao"] == q]
        geometry = validar_geometria(item.get("geometry"), outras)
        preparados.append({"id_localidade": id_localidade, "quarteirao": q,
                           "logradouro": rua, "lado": lado, "geometry": geometry,
                           "base_geometry_hash": base_hash})
    return preparados
