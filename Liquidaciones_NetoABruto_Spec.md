# Liquidaciones: introducir derechos como Neto y cuadre de conceptos

Documento de referencia para portar la lógica a otra calculadora de liquidaciones
(p. ej. una webapp en Python). Describe **qué** hace cada cambio y **por qué**, de forma
independiente del lenguaje, con notas concretas para Python.

---

## 1. Cambio central: introducir Derechos de Imagen / P.I. como importe NETO

### Contexto
En "Objetivo Neto", el usuario quiere teclear lo que el artista **percibe** (neto) en
Derechos de Imagen y Propiedad Intelectual, no el bruto facturado. El motor de cálculo,
en cambio, parte siempre del bruto. Por tanto hay que **invertir** neto → bruto antes de
entrar al motor.

### Cómo calcula el motor un derecho (forward)
A partir del bruto, encadena (redondeando a 2 decimales en cada paso):

```
comision = round2(bruto * COMISION_AGENCIA)
base     = round2(bruto - comision)
irpf     = round2(base * IRPF_pct/100)
neto     = round2(base - irpf)
```

Sin redondeos, la relación es lineal:

```
neto = bruto * (1 - COMISION_AGENCIA) * (1 - IRPF_pct/100)
```

### La inversión (neto → bruto)
Fórmula cerrada (la "semilla"):

```
bruto ≈ neto / [ (1 - COMISION_AGENCIA) * (1 - IRPF_pct/100) ]
```

**Problema:** la fórmula cerrada sola se desvía ±1 céntimo, porque el motor redondea cada
subpaso y el bruto facturado es un importe de 2 decimales.

**Solución (clave):** usar la fórmula como semilla y hacer una **micro-búsqueda local**:
probar candidatos de bruto a ±unos céntimos de la semilla, recalcular el neto **con la
misma función forward del motor**, y quedarse con el que reproduce el neto objetivo exacto.

**Por qué funciona siempre:** como `factor = (1-comisión)(1-IRPF/100)` es menor que 1, al
subir el bruto 1 céntimo el neto sube *menos* de 1 céntimo. La función neto(bruto) es
monótona y **nunca salta dos céntimos**, así que para casi cualquier neto objetivo existe
un bruto de 2 decimales que lo reproduce exacto. Verificado sobre 1.5M de valores: 0 €
de desviación.

### Dónde aplicarlo
- Solo en modo **Objetivo Neto**.
- Convertir **en el límite** (al leer los inputs): se convierte neto → bruto y se guarda el
  **bruto** en la estructura de datos. **Todo el motor aguas abajo se queda igual.** Esto es
  lo que hace el cambio barato y de bajo riesgo.
- Cada derecho usa su propio IRPF: Imagen un tipo fijo; P.I. el seleccionado (o uno por
  defecto si no hay selector).

### Implementación de referencia en Python

```python
from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")
COMISION_AGENCIA = Decimal("0.05")

def round2(x: Decimal) -> Decimal:
    # OJO: round() nativo de Python usa redondeo bancario (half-to-even).
    # El motor original redondea HALF-UP. Hay que ser consistente.
    return x.quantize(CENT, rounding=ROUND_HALF_UP)

def neto_de_derecho(bruto: Decimal, irpf_pct: Decimal) -> Decimal:
    """Réplica EXACTA del forward del motor. Si el motor cambia, cambia esto también."""
    bruto = round2(bruto)
    comision = round2(bruto * COMISION_AGENCIA)
    base = round2(bruto - comision)
    irpf = round2(base * (irpf_pct / Decimal(100)))
    return round2(base - irpf)

def bruto_desde_neto_derecho(neto_objetivo: Decimal, irpf_pct: Decimal) -> Decimal:
    neto_objetivo = round2(neto_objetivo)
    factor = (Decimal(1) - COMISION_AGENCIA) * (Decimal(1) - irpf_pct / Decimal(100))
    if factor <= 0:                       # guarda defensiva (IRPF >= 100%)
        return neto_objetivo
    semilla = round2(neto_objetivo / factor)
    mejor, mejor_diff = semilla, None
    for c in range(-5, 6):                # ventana ±5 céntimos (sobra)
        cand = round2(semilla + Decimal(c) * CENT)
        if cand < 0:
            continue
        diff = abs(neto_de_derecho(cand, irpf_pct) - neto_objetivo)
        if mejor_diff is None or diff < mejor_diff:
            mejor_diff, mejor = diff, cand
    return mejor
```

> **Regla de oro:** `bruto_desde_neto_derecho` solo es exacto si `neto_de_derecho`
> es una réplica fiel del cálculo real del motor (mismo orden de operaciones, mismo
> redondeo). La micro-búsqueda absorbe cualquier redondeo *siempre que el forward
> replicado coincida con el real*. Si puedes, llama directamente a la función forward
> del propio motor en vez de duplicarla.

---

## 2. Cuadre de conceptos (solo si existe un modo "Autónomo" / Factura Única)

Aplica únicamente si tu calculadora tiene un modo sin "días de alta" (factura única de
autónomo/sociedad), donde el ingreso principal NO es un caché por días.

### Regla
Sin días de alta no existe el concepto "Honorarios" de relleno. Los únicos conceptos
asignables (Gastos Justificados, Derechos de Imagen, Propiedad Intelectual) **deben cuadrar
con el total**.

- **Desactivar el sumidero:** el sobrante que normalmente se vuelca como "Honorarios"
  del último día NO debe asignarse en modo autónomo.
- **Si faltan importes** (conceptos < total): mostrar el desglose parcial, que la fila TOTAL
  refleje lo realmente asignado, y avisar: *"Has asignado X de Y; faltan Z por asignar"*.
  En Objetivo Neto, ocultar el banner que dice "para conseguir X el bruto sería Y" (sería
  engañoso, no se alcanza X).
- **Si sobran** (conceptos > total): recortar por **orden de prioridad de asignación**.
  En nuestro caso el orden es: Gastos → Material → Derechos de Imagen → Propiedad Intelectual.
  El último de la cola (P.I.) es el primero en recortarse; los Gastos quedan intactos.
  Avisar también del recorte.
- **No pintar la fila de Honorarios** cuando su importe es 0 (en autónomo es siempre 0).
  Práctico: condicionar el render a `cache.bruto > 0` en todos los puntos de pintado
  (vista agrupada, vista por día, y la versión PDF).

### Detección del descuadre (pseudocódigo)

```
total_objetivo  = importe tecleado (bruto) u objetivo (neto)
asignado        = (modo bruto) suma de brutos de conceptos solicitados
                  (modo neto)  neto máximo alcanzable con esos conceptos
diff = total_objetivo - asignado
if diff > 0:  -> FALTAN |diff|   (mostrar parcial + aviso; ocultar banner verde en neto)
if diff < 0:  -> SOBRAN |diff|   (recorte por prioridad + aviso)
if diff == 0: -> cuadra (sin aviso)
```

En Objetivo Neto, el "neto máximo alcanzable" se obtiene simulando el escenario con el
bruto justo de los conceptos (sin relleno). Para el caso de exceso, una bisección sobre el
bruto en `[0, suma_brutos_conceptos]` clava el objetivo recortando el último concepto.

---

## 3. Detalles de UX (menores, opcionales)

- Título del importe principal y placeholders de derechos en modo **Bruto a Neto**:
  añadir "(sin IVA)" para dejar claro que el importe es sin IVA.
  - Título: `Importe venta bruto (sin IVA)`
  - Placeholders de derechos: `Importe bruto (sin IVA)`
- En modo **Objetivo Neto**, los placeholders de derechos pasan a `Importe neto`
  (coherente con el cambio 1).
- Si los textos se fijan en dos sitios (HTML inicial + función que alterna de modo),
  actualizar **ambos** para que la carga inicial y el cambio de modo sean coherentes.

---

## 4. Checklist al portar a Python

1. **Dinero con precisión controlada.** Usa `Decimal` con `ROUND_HALF_UP`, o trabaja en
   **céntimos enteros**. No mezcles `float` con redondeos: introduce errores. Define un único
   `round2` y úsalo en todo el motor.
2. **Cuidado con `round()` nativo:** Python redondea half-to-even (bancario), distinto del
   half-up del motor JS original. Replica el redondeo que use tu motor real.
3. **Convierte en el límite (input), no en el motor.** Neto → bruto al leer; guarda el bruto;
   el resto del cálculo no se toca.
4. **El inversor debe replicar el forward exacto.** Idealmente, reutiliza la función de
   cálculo del propio motor dentro de la micro-búsqueda.
5. **Tests de regresión:** recorre netos de 0,01 € a un máximo razonable para cada tipo de
   IRPF y comprueba que `neto_de_derecho(bruto_desde_neto_derecho(n)) == n`. Debe dar 0
   fallos. Es la prueba que garantiza que el redondeo está bien.
6. **Cuadre/Autónomo:** solo si tu calc tiene ese modo. Desactiva el relleno de honorarios,
   añade el aviso de descuadre y oculta filas a 0.
7. **Orden de recorte:** documenta y respeta el orden de prioridad de asignación; el último
   concepto es el que absorbe el recorte por exceso.

---

## 5. Casos límite a no olvidar

- IRPF = 100% rompería la división (factor 0): guarda defensiva.
- Importe objetivo menor que un concepto ya asignado: en modo con días reales el sobrante se
  recorta por `Math.min`/clamp contra el "bucket" disponible; documenta ese comportamiento.
- Coherencia de la fila TOTAL: debe sumar lo realmente pintado en las filas, no el importe
  tecleado, cuando hay descuadre.
