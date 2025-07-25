import streamlit as st
from equipos_predefinidos import equipos_predefinidos
import pandas as pd
import numpy as np
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))

st.set_page_config(page_title="Calculadora Solar", layout="wide")

# --- Cargar catálogos ---
@st.cache_data
def load_catalogs():
    # Cargar catálogo de paneles
    catalogo_paneles = pd.read_excel("Catalogo_Modulos_Fotovoltaicos.xlsx")
    
    # Cargar catálogo de controladores
    catalogo_controladores = pd.read_excel("Catalogo__Controladores.xlsx")
    
    return catalogo_paneles, catalogo_controladores

catalogo_paneles, catalogo_controladores = load_catalogs()

# Procesar columnas que tienen rangos (tomamos el promedio)
def limpiar_rangos(valor):
    if isinstance(valor, str) and ("–" in valor or "-" in valor):
        separador = "–" if "–" in valor else "-"
        partes = [p.strip() for p in valor.split(separador)]
        try:
            return (float(partes[0]) + float(partes[1])) / 2
        except:
            return np.nan
    try:
        return float(valor)
    except:
        return np.nan

# Limpiar datos de paneles
catalogo_paneles["Pmax (W)"] = catalogo_paneles["Pmax (W)"].apply(limpiar_rangos)
catalogo_paneles["Vmp (V)"] = catalogo_paneles["Vmp (V)"].apply(limpiar_rangos)
catalogo_paneles["Imp (A)"] = catalogo_paneles["Imp (A)"].apply(limpiar_rangos)
catalogo_paneles["Isc (A)"] = catalogo_paneles["Isc (A)"].apply(limpiar_rangos)

# --- Streamlit Config ---
st.title("🔆 Sistema Dimensionamiento Aislado")

# Usar session_state para mantener los equipos
if 'equipos' not in st.session_state:
    st.session_state.equipos = equipos_predefinidos.copy()

# ----------------------------
# Formulario para agregar equipo
# ----------------------------
with st.expander("➕ Agregar nuevo equipo manualmente"):
    with st.form("agregar_equipo"):
        nombre = st.text_input("Nombre del equipo")
        potencia = st.number_input("Potencia (W)", min_value=1)
        cantidad = st.number_input("Cantidad", min_value=1)
        horas = st.number_input("Horas de uso por día", min_value=0.0, step=0.1)
        
        if st.form_submit_button("Agregar a la tabla"):
            nuevo_equipo = {
                "nombre": nombre,
                "potencia": potencia,
                "cantidad": cantidad,
                "horas": horas
            }
            st.session_state.equipos.append(nuevo_equipo)
            st.success("Equipo agregado correctamente!")
            st.rerun()

# ----------------------------
# Mostrar equipos en tabla editable
# ----------------------------
st.subheader("📋 Equipos seleccionados")

# Crear DataFrame con columna de selección
df = pd.DataFrame(st.session_state.equipos)
df["Potencia Total (W)"] = df["potencia"] * df["cantidad"]
df["Energía diaria (Wh)"] = df["Potencia Total (W)"] * df["horas"]
df["Seleccionar"] = False  # Columna para selección

# Mostrar tabla con checkbox de selección
edited_df = st.data_editor(
    df,
    column_config={
        "Seleccionar": st.column_config.CheckboxColumn("Seleccionar"),
        "nombre": "Equipo",
        "potencia": st.column_config.NumberColumn("Potencia (W)", format="%d W"),
        "cantidad": st.column_config.NumberColumn("Cantidad", format="%d"),
        "horas": st.column_config.NumberColumn("Horas/día", format="%.1f"),
        "Potencia Total (W)": st.column_config.NumberColumn("Potencia Total", format="%d W"),
        "Energía diaria (Wh)": st.column_config.NumberColumn("Energía diaria", format="%.1f Wh")
    },
    hide_index=True,
    disabled=["nombre", "potencia", "cantidad", "horas", "Potencia Total (W)", "Energía diaria (Wh)"],
    use_container_width=True,
    key="equipos_table"
)

# Botón para eliminar seleccionados
if st.button("🗑️ Eliminar equipos seleccionados"):
    # Obtener índices de las filas seleccionadas
    selected_indices = [i for i, row in enumerate(edited_df.to_dict('records')) if row['Seleccionar']]
    
    if selected_indices:
        # Eliminar en orden inverso para evitar problemas de índices
        for i in sorted(selected_indices, reverse=True):
            st.session_state.equipos.pop(i)
        st.success(f"{len(selected_indices)} equipos eliminados correctamente!")
        st.rerun()
    else:
        st.warning("Por favor selecciona al menos un equipo para eliminar")
# ----------------------------
# Cálculos solares
# ----------------------------
energia_total = df["Energía diaria (Wh)"].sum()
st.markdown(f"### ⚡ Energía total diaria: {energia_total:.2f} Wh")

st.subheader("🔧 Cálculo del sistema fotovoltaico")
hsp = st.number_input("Horas Sol Pico (HSP)", min_value=1.0, value=5.87, step=0.1)
voltaje_sistema = st.number_input("Voltaje del sistema (V)", min_value=12, value=12, step=12)

# Cálculos
eficiencia = 0.20  # 20% pérdidas fijas
energia_ajustada = energia_total / (1 - eficiencia)
wp_necesarios = energia_ajustada / hsp
potencia_inversor = df["Potencia Total (W)"].sum() * 1.2  # Factor fijo 1.2

# Buscar panel recomendado
panel_recomendado = catalogo_paneles[catalogo_paneles["Pmax (W)"] >= wp_necesarios / 2].sort_values("Pmax (W)")
if panel_recomendado.empty:
    st.error("No se encontraron paneles adecuados en el catálogo para la potencia requerida")
    st.stop()

panel_recomendado = panel_recomendado.iloc[0]
n_paneles = wp_necesarios / panel_recomendado["Pmax (W)"]

# Configuración de paneles
n_paneles_serie = max(1, int(voltaje_sistema / panel_recomendado["Vmp (V)"]))
n_paneles_paralelo = max(1, int(np.ceil(n_paneles / n_paneles_serie)))

# Cálculo del controlador MPPT
st.subheader("⚡ Cálculo del controlador MPPT")

# Calcular corriente necesaria con factor de seguridad
isc_panel = panel_recomendado["Isc (A)"]
corriente_controlador = isc_panel * n_paneles_paralelo * 1.25  # Factor de seguridad del 25%

# Buscar controlador recomendado
try:
    controlador_recomendado = catalogo_controladores[
        (catalogo_controladores["Corriente Nominal (A)"] >= corriente_controlador)
    ].sort_values("Corriente Nominal (A)").iloc[0]
    
    # Mostrar información del controlador
    st.markdown(f"""
    - Corriente de cortocircuito (Isc) del panel: {isc_panel:.2f} A
    - Corriente mínima del controlador: {corriente_controlador:.2f} A
    - 🔌 *Controlador sugerido*: **{controlador_recomendado['Marca']}, {controlador_recomendado['Modelo']}** ({controlador_recomendado['Corriente Nominal (A)']}A)
    """)
except IndexError:
    st.warning(f"No se encontró controlador adecuado para corriente de {corriente_controlador:.2f}A. Considere usar múltiples controladores.")

# Cálculo de baterías
st.subheader("🔋 Cálculo de banco de baterías")
dias_autonomia = st.number_input("Días de autonomía", min_value=1, value=2, step=1)
profundidad_descarga = 0.5  # 50%
capacidad_bateria_total = (energia_total * dias_autonomia) / (voltaje_sistema * profundidad_descarga)
capacidad_bateria_total_ah = capacidad_bateria_total / voltaje_sistema

# Datos de batería estándar
capacidad_bateria_individual = st.number_input("Capacidad de cada batería (Ah)", min_value=1, value=150)
n_baterias = np.ceil(capacidad_bateria_total_ah / capacidad_bateria_individual)

# ----------------------------
# Resultados
# ----------------------------
st.markdown(f"""
## 📊 Resultados del sistema

### Paneles solares
- Energía ajustada por pérdidas: {energia_ajustada:.2f} Wh
- Potencia requerida: {wp_necesarios:.2f} W
- 🔆 *Panel sugerido*: {panel_recomendado['Marca']}, {panel_recomendado['Modelo']} de {panel_recomendado['Pmax (W)']:.0f} W
- Número total de paneles requeridos: {np.ceil(n_paneles):.0f}

### Inversor
- Potencia recomendada del inversor: {potencia_inversor:.2f} W

### Baterías
- Capacidad total requerida: {capacidad_bateria_total:.2f} Wh
- Capacidad total en Ah: {capacidad_bateria_total_ah:.2f} Ah
- 🔋 Número de baterías de {capacidad_bateria_individual} Ah: {n_baterias:.0f}
""")

# --- Estilo adicional ---
st.markdown("""
<style>
    .stMarkdown h3 {
        color: #2e86c1;
        margin-top: 20px;
    }
    .stMarkdown h2 {
        color: #1a5276;
        border-bottom: 2px solid #1a5276;
        padding-bottom: 5px;
    }
</style>
""", unsafe_allow_html=True)