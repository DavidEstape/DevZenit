from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional

# =====================================================================
# 1. MODELOS DE DATOS (PYDANTIC) - Entradas de la API
# =====================================================================
class AlquilerItem(BaseModel):
    nombre: str
    precio: float
    cantidad: int

class CalculoRequest(BaseModel):
    importe_principal: float = Field(..., description="Bruto de venta o Neto objetivo según el endpoint")
    dias_trabajo: int = Field(default=1, ge=1)
    porcentaje_irpf: float = Field(default=2.0, ge=2.0)
    kilometraje_total: float = Field(default=0.0, ge=0.0)
    dias_dieta: int = Field(default=0, ge=0)
    tarifa_dieta: float = Field(default=28.0736)
    gastos_justificados: float = Field(default=0.0, ge=0.0)
    alquiler_material: List[AlquilerItem] = []

# =====================================================================
# 2. INICIALIZACIÓN DE LA APLICACIÓN FASTAPI
# =====================================================================
app = FastAPI(
    title="API Simulador Liquidaciones Zenit / Taiman",
    description="Motor de cálculo financiero para desgloses de artistas",
    version="1.0.0"
)

# =====================================================================
# 3. LÓGICA DE NEGOCIO (MOTOR MATEMÁTICO CORE)
# =====================================================================
def calcular_dia(bruto: float, porcentaje_irpf: float) -> dict:
    """Calcula los impuestos y Seguridad Social de un día de caché."""
    comision = bruto * 0.05
    coste = bruto - comision
    
    # Tramos de Seguridad Social
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
        seg_social = 179.49
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
    """Distribuye el presupuesto en cascada respetando las prioridades."""
    
    # Asegurar mínimos lógicos
    dias = max(1, req.dias_trabajo)
    dias_dieta = min(req.dias_dieta, dias)
    bucket = importe_bruto_prueba - (dias * 75.0)
    
    # Estructura de días inicial (garantizando 75€/día base)
    d_data = [{"dia": i, "cache": 75.0, "km": 0.0, "dieta": 0.0, "alquiler": 0.0} for i in range(1, dias + 1)]

    # 1. Kilometraje (Equitativo)
    if req.kilometraje_total > 0:
        req_km = req.kilometraje_total * 0.2737
        total_req_km = req_km * dias
        available_km = min(total_req_km, bucket)
        per_day_km = available_km / dias
        for i in range(dias):
            d_data[i]["km"] = per_day_km
            bucket -= per_day_km
        bucket = max(0, bucket)

    # 2. Dietas (Equitativo)
    if dias_dieta > 0:
        total_req_dieta = req.tarifa_dieta * dias_dieta
        available_dieta = min(total_req_dieta, bucket)
        per_day_dieta = available_dieta / dias_dieta
        for i in range(dias_dieta):
            d_data[i]["dieta"] = per_day_dieta
            bucket -= per_day_dieta
        bucket = max(0, bucket)

    # 3. Gastos Justificados
    gastos_justificados_sim = 0.0
    if req.gastos_justificados > 0 and bucket > 0:
        gastos_justificados_sim = min(req.gastos_justificados, bucket)
        bucket -= gastos_justificados_sim

    # 4. Alquiler de Material (En cascada / greedy greedy por día)
    total_alquiler = sum(item.precio * item.cantidad for item in req.alquiler_material)
    if total_alquiler > 0:
        for i in range(dias):
            alquiler_dia_bruto = min(total_alquiler, bucket)
            d_data[i]["alquiler"] = alquiler_dia_bruto
            bucket -= alquiler_dia_bruto
        bucket = max(0, bucket)

    # 5. Sobrante vuelve al último día
    if bucket > 0:
        d_data[-1]["cache"] += bucket

    # Calcular resultados finales iterando sobre la estructura
    totals_zenit = {"bruto": 0.0, "comision": 0.0, "coste": 0.0, "seg_social": 0.0, "irpf": 0.0, "a_liquidar": 0.0}
    day_results = []

    for d in d_data:
        # Caché
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

        # Agregados extras del día
        if d["km"] > 0:
            c = d["km"] * 0.05
            bl = d["km"] - c
            totals_zenit["bruto"] += d["km"]; totals_zenit["comision"] += c; totals_zenit["coste"] += bl; totals_zenit["a_liquidar"] += bl
            conceptos.append({"tipo": "kilometraje", "bruto": d["km"], "comision": c, "base_liquidable": bl, "a_liquidar": bl})

        if d["dieta"] > 0:
            c = d["dieta"] * 0.05
            bl = d["dieta"] - c
            totals_zenit["bruto"] += d["dieta"]; totals_zenit["comision"] += c; totals_zenit["coste"] += bl; totals_zenit["a_liquidar"] += bl
            conceptos.append({"tipo": "dieta", "bruto": d["dieta"], "comision": c, "base_liquidable": bl, "a_liquidar": bl})

        if d["alquiler"] > 0:
            c = d["alquiler"] * 0.05
            bl = d["alquiler"] - c
            totals_zenit["bruto"] += d["alquiler"]; totals_zenit["comision"] += c; totals_zenit["coste"] += bl
            conceptos.append({"tipo": "alquiler_material", "bruto": d["alquiler"], "comision": c, "base_liquidable": bl, "a_liquidar": "via Taiman"})

        day_results.append({"dia": d["dia"], "conceptos": conceptos})

    # Construir Output Gastos
    gastos_res = {"bruto": 0.0, "a_liquidar": 0.0}
    if gastos_justificados_sim > 0:
        c = gastos_justificados_sim * 0.05
        bl = gastos_justificados_sim - c
        totals_zenit["bruto"] += gastos_justificados_sim; totals_zenit["comision"] += c; totals_zenit["coste"] += bl; totals_zenit["a_liquidar"] += bl
        gastos_res = {"bruto": gastos_justificados_sim, "comision": c, "base_liquidable": bl, "a_liquidar": bl}

    # Construir Output Taiman
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
            "a_liquidar_taiman": round(taiman_neto, 2)
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
    """Estructura la respuesta final JSON según la arquitectura definida."""
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
# 4. RUTAS HTTP (ENDPOINTS)
# =====================================================================

@app.post("/api/v1/simulaciones/bruto-a-neto")
def calcular_bruto_a_neto(req: CalculoRequest):
    min_bruto_requerido = max(1, req.dias_trabajo) * 75.0
    bruto_final = max(req.importe_principal, min_bruto_requerido)
    
    sim = simular_escenario(bruto_final, req)
    adjusted = req.importe_principal < min_bruto_requerido
    
    return format_response(sim, adjusted=adjusted)

@app.post("/api/v1/simulaciones/neto-a-bruto")
def calcular_neto_a_bruto(req: CalculoRequest):
    min_bruto_requerido = max(1, req.dias_trabajo) * 75.0
    sim_minima = simular_escenario(min_bruto_requerido, req)
    
    objetivo_neto = req.importe_principal
    
    # Si el usuario pide un neto imposiblemente bajo, devolvemos el mínimo legal
    if objetivo_neto <= sim_minima["neto_calculado"]:
        return format_response(sim_minima, adjusted=True)
        
    # Algoritmo de Búsqueda Binaria (Goal Seek)
    low = min_bruto_requerido
    high = objetivo_neto * 3 + min_bruto_requerido + 1000 # Cota superior garantizada
    bruto_final = min_bruto_requerido
    res = sim_minima
    
    for _ in range(100): # Tope de seguridad de iteraciones
        mid = (low + high) / 2
        sim = simular_escenario(mid, req)
        
        # Margen de error aceptado: Medio céntimo
        if abs(sim["neto_calculado"] - objetivo_neto) < 0.005:
            bruto_final = mid
            res = sim
            break
            
        if sim["neto_calculado"] < objetivo_neto:
            low = mid
        else:
            high = mid
            
        bruto_final = mid
        res = sim

    return format_response(res)

# =====================================================================
# INSTRUCCIONES PARA LEVANTAR EL SERVIDOR LOCALMENTE
# =====================================================================
# 1. Instalar dependencias: pip install fastapi uvicorn pydantic
# 2. Guardar este código como: main.py
# 3. Ejecutar en terminal: uvicorn main:app --reload
# 4. Abrir en navegador: http://127.0.0.1:8000/docs para ver la interfaz Swagger de testeo
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)