from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum

# =====================================================================
# 1. BASES DE DATOS SIMULADAS (Configuración centralizada)
# =====================================================================
# En un entorno real de producción, esto vendría de una base de datos (PostgreSQL, MongoDB...)
# o de variables de entorno para facilitar su mantenimiento.

TARIFAS_DIETA = {
    "nacional": 28.0736,
    "internacional": 50.6105,
    "pernocta_nacional": 56.1473,
    "pernocta_internacional": 96.1578
}

CATALOGO_MATERIAL = {
    "altavoces": {"nombre": "Altavoces", "precio": 105.2632},
    "bajos": {"nombre": "Bajos y complementos", "precio": 73.6842},
    "bateria_acustica": {"nombre": "Batería acústica", "precio": 105.2632},
    "bateria_electrica": {"nombre": "Batería eléctrica", "precio": 105.2632},
    "cables": {"nombre": "Cables", "precio": 5.2632},
    "clarinete": {"nombre": "Clarinete", "precio": 84.2105},
    "contrabajo": {"nombre": "Contrabajo", "precio": 105.2632},
    "guitarra_acustica": {"nombre": "Guitarra acústica", "precio": 73.6842},
    "guitarra_clasica": {"nombre": "Guitarra clásica", "precio": 63.1579},
    "guitarra_electrica": {"nombre": "Guitarra eléctrica", "precio": 105.2632},
    "microfono": {"nombre": "Micrófono", "precio": 52.6316},
    "ordenador": {"nombre": "Ordenador", "precio": 63.1579}
}

# =====================================================================
# 2. MODELOS DE DATOS (PYDANTIC) - Entradas de la API
# =====================================================================
class TipoDieta(str, Enum):
    nacional = "nacional"
    internacional = "internacional"
    pernocta_nacional = "pernocta_nacional"
    pernocta_internacional = "pernocta_internacional"

class AlquilerItem(BaseModel):
    id_material: str = Field(..., description="ID del catálogo de materiales (ej. 'microfono')")
    cantidad: int = Field(default=1, ge=1)

class CalculoRequest(BaseModel):
    importe_principal: float = Field(..., description="Bruto de venta o Neto objetivo")
    dias_trabajo: int = Field(default=1, ge=1)
    porcentaje_irpf: float = Field(default=2.0, ge=2.0)
    kilometraje_total: float = Field(default=0.0, ge=0.0)
    dias_dieta: int = Field(default=0, ge=0)
    tipo_dieta: TipoDieta = Field(default=TipoDieta.nacional)
    gastos_justificados: float = Field(default=0.0, ge=0.0)
    alquiler_material: List[AlquilerItem] = []

# =====================================================================
# 3. INICIALIZACIÓN DE LA APLICACIÓN FASTAPI
# =====================================================================
app = FastAPI(
    title="API Simulador Liquidaciones",
    description="Motor de cálculo financiero centralizado (Single Source of Truth)",
    version="1.1.0"
)

# =====================================================================
# 4. LÓGICA DE NEGOCIO (MOTOR MATEMÁTICO CORE)
# =====================================================================
def calcular_dia(bruto: float, porcentaje_irpf: float) -> dict:
    comision = bruto * 0.05
    coste = bruto - comision
    
    seg_social = 0.0
    if bruto <= 75:
        seg_social = 21.0
    elif bruto <= 477.25:
        intermedio1 = coste * 0.25009
        intermedio2 = (coste - intermedio1) * 0.0655
        seg_social = intermedio1 + intermedio2 + 2.5
    elif bruto <= 729.421578947369:
        seg_social = 138.86
    elif bruto <= 1250.26368421053:
        seg_social = 176.49
    elif bruto <= 2023.02157894737:
        seg_social = 221.41
    elif bruto <= 2287.30578947368:
        seg_social = 288.52
    elif bruto <= 2732.66368421053:
        seg_social = 294.67
    elif bruto <= 3158.85315789474:
        seg_social = 300.77
    else:
        seg_social = 310.27

    base_liq = coste - seg_social
    irpf = base_liq * (porcentaje_irpf / 100)
    a_liquidar = base_liq - irpf

    return {
        "bruto": bruto, "comision": comision, "coste": coste,
        "seg_social": seg_social, "base_liq": base_liq, "irpf": irpf, "a_liquidar": a_liquidar
    }

def simular_escenario(importe_bruto_prueba: float, req: CalculoRequest) -> dict:
    # Obtener el precio real de la dieta según el catálogo
    precio_dieta_real = TARIFAS_DIETA[req.tipo_dieta.value]

    # Calcular el coste total del material validándolo contra el catálogo
    total_alquiler = 0.0
    materiales_procesados = []
    
    for item in req.alquiler_material:
        if item.id_material in CATALOGO_MATERIAL:
            item_bd = CATALOGO_MATERIAL[item.id_material]
            subtotal = item_bd["precio"] * item.cantidad
            total_alquiler += subtotal
            materiales_procesados.append({
                "nombre": item_bd["nombre"],
                "cantidad": item.cantidad,
                "precio_unitario": item_bd["precio"],
                "subtotal": subtotal
            })
        else:
            # Opción estricta: podríamos lanzar HTTPException(400) si el ID no existe
            pass 

    dias = max(1, req.dias_trabajo)
    dias_dieta = min(req.dias_dieta, dias)
    bucket = importe_bruto_prueba - (dias * 75.0)
    
    d_data = [{"dia": i, "cache": 75.0, "km": 0.0, "dieta": 0.0, "alquiler": 0.0} for i in range(1, dias + 1)]

    # 1. Kilometraje
    if req.kilometraje_total > 0:
        req_km = req.kilometraje_total * 0.2737
        total_req_km = req_km * dias
        available_km = min(total_req_km, bucket)
        per_day_km = available_km / dias
        for i in range(dias):
            d_data[i]["km"] = per_day_km
            bucket -= per_day_km
        bucket = max(0, bucket)

    # 2. Dietas 
    if dias_dieta > 0:
        total_req_dieta = precio_dieta_real * dias_dieta
        available_dieta = min(total_req_dieta, bucket)
        per_day_dieta = available_dieta / dias_dieta
        for i in range(dias_dieta):
            d_data[i]["dieta"] = per_day_dieta
            bucket -= per_day_dieta
        bucket = max(0, bucket)

    # 3. Gastos
    gastos_justificados_sim = 0.0
    if req.gastos_justificados > 0 and bucket > 0:
        gastos_justificados_sim = min(req.gastos_justificados, bucket)
        bucket -= gastos_justificados_sim

    # 4. Alquiler Material
    if total_alquiler > 0:
        for i in range(dias):
            alquiler_dia_bruto = min(total_alquiler, bucket)
            d_data[i]["alquiler"] = alquiler_dia_bruto
            bucket -= alquiler_dia_bruto
        bucket = max(0, bucket)

    # 5. Sobrante
    if bucket > 0:
        d_data[-1]["cache"] += bucket

    # Calcular resultados finales
    totals_zenit = {"bruto": 0.0, "comision": 0.0, "coste": 0.0, "seg_social": 0.0, "irpf": 0.0, "a_liquidar": 0.0}
    day_results = []

    for d in d_data:
        res_cache = calcular_dia(d["cache"], req.porcentaje_irpf)
        totals_zenit["bruto"] += res_cache["bruto"]
        totals_zenit["comision"] += res_cache["comision"]
        totals_zenit["coste"] += res_cache["coste"]
        totals_zenit["seg_social"] += res_cache["seg_social"]
        totals_zenit["irpf"] += res_cache["irpf"]
        totals_zenit["a_liquidar"] += res_cache["a_liquidar"]

        conceptos = [{
            "tipo": "cache", "bruto": res_cache["bruto"], "comision": res_cache["comision"], 
            "base_liquidable": res_cache["coste"], "seg_social": res_cache["seg_social"], 
            "irpf": res_cache["irpf"], "a_liquidar": res_cache["a_liquidar"]
        }]

        if d["km"] > 0:
            c = d["km"] * 0.05; bl = d["km"] - c
            totals_zenit["bruto"] += d["km"]; totals_zenit["comision"] += c; totals_zenit["coste"] += bl; totals_zenit["a_liquidar"] += bl
            conceptos.append({"tipo": "kilometraje", "bruto": d["km"], "comision": c, "base_liquidable": bl, "a_liquidar": bl})

        if d["dieta"] > 0:
            c = d["dieta"] * 0.05; bl = d["dieta"] - c
            totals_zenit["bruto"] += d["dieta"]; totals_zenit["comision"] += c; totals_zenit["coste"] += bl; totals_zenit["a_liquidar"] += bl
            conceptos.append({"tipo": "dieta", "bruto": d["dieta"], "comision": c, "base_liquidable": bl, "a_liquidar": bl})

        if d["alquiler"] > 0:
            c = d["alquiler"] * 0.05; bl = d["alquiler"] - c
            totals_zenit["bruto"] += d["alquiler"]; totals_zenit["comision"] += c; totals_zenit["coste"] += bl
            conceptos.append({"tipo": "alquiler_material", "bruto": d["alquiler"], "comision": c, "base_liquidable": bl, "a_liquidar": "via Taiman"})

        day_results.append({"dia": d["dia"], "conceptos": conceptos})

    gastos_res = {"bruto": 0.0, "a_liquidar": 0.0}
    if gastos_justificados_sim > 0:
        c = gastos_justificados_sim * 0.05; bl = gastos_justificados_sim - c
        totals_zenit["bruto"] += gastos_justificados_sim; totals_zenit["comision"] += c; totals_zenit["coste"] += bl; totals_zenit["a_liquidar"] += bl
        gastos_res = {"bruto": gastos_justificados_sim, "comision": c, "base_liquidable": bl, "a_liquidar": bl}

    total_allocated_material = sum(d["alquiler"] for d in d_data)
    taiman_neto = 0.0
    taiman_res = None

    if total_allocated_material > 0:
        importe = total_allocated_material - (total_allocated_material * 0.05)
        comision = importe * 0.05
        base_liq = importe - comision
        irpf_7 = base_liq * 0.07
        taiman_neto = base_liq - irpf_7
        taiman_res = {
            "importe_material_asignado": round(total_allocated_material, 2),
            "importe_neto_inicial": round(importe, 2),
            "comision": round(comision, 2),
            "base_liquidable": round(base_liq, 2),
            "irpf_7": round(irpf_7, 2),
            "a_liquidar_taiman": round(taiman_neto, 2),
            "detalle_material": materiales_procesados
        }

    return {
        "bruto_evaluado": importe_bruto_prueba,
        "neto_calculado": totals_zenit["a_liquidar"] + taiman_neto,
        "day_results": day_results,
        "gastos_globales": gastos_res,
        "taiman_res": taiman_res,
        "totals_zenit": totals_zenit
    }

def format_response(sim_data: dict, adjusted: bool = False):
    return {
        "status": "success",
        "warnings": ["El neto era demasiado bajo y se ha ajustado al mínimo legal de 75€/día"] if adjusted else [],
        "parametros_calculados": {
            "bruto_necesario_calculado": round(sim_data["bruto_evaluado"], 2),
            "neto_total_percibir": round(sim_data["neto_calculado"], 2)
        },
        "desglose_zenit": {
            "totales": {k: round(v, 2) for k, v in sim_data["totals_zenit"].items()},
            "detalle_dias": sim_data["day_results"],
            "gastos_globales": sim_data["gastos_globales"]
        },
        "desglose_taiman": {
            "aplica_taiman": sim_data["taiman_res"] is not None,
            "totales": sim_data["taiman_res"]
        }
    }

# =====================================================================
# 5. RUTAS HTTP (ENDPOINTS)
# =====================================================================

@app.post("/api/v1/simulaciones/bruto-a-neto")
def calcular_bruto_a_neto(req: CalculoRequest):
    min_bruto_requerido = max(1, req.dias_trabajo) * 75.0
    bruto_final = max(req.importe_principal, min_bruto_requerido)
    sim = simular_escenario(bruto_final, req)
    return format_response(sim, adjusted=(req.importe_principal < min_bruto_requerido))

@app.post("/api/v1/simulaciones/neto-a-bruto")
def calcular_neto_a_bruto(req: CalculoRequest):
    min_bruto_requerido = max(1, req.dias_trabajo) * 75.0
    sim_minima = simular_escenario(min_bruto_requerido, req)
    objetivo_neto = req.importe_principal
    
    if objetivo_neto <= sim_minima["neto_calculado"]:
        return format_response(sim_minima, adjusted=True)
        
    low = min_bruto_requerido
    high = objetivo_neto * 3 + min_bruto_requerido + 1000 
    bruto_final = min_bruto_requerido
    res = sim_minima
    
    for _ in range(100): 
        mid = (low + high) / 2
        sim = simular_escenario(mid, req)
        
        if abs(sim["neto_calculado"] - objetivo_neto) < 0.005:
            res = sim; break
        if sim["neto_calculado"] < objetivo_neto:
            low = mid
        else:
            high = mid
        res = sim

    return format_response(res)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)