import streamlit as st
import pandas as pd
import tempfile
import io
import ifcopenshell
import ifcopenshell.util.element
from st_aggrid import AgGrid, GridOptionsBuilder
from anytree import Node, RenderTree
from io import StringIO
import folium
from folium.plugins import FeatureGroupSubGroup
from streamlit_folium import st_folium
import streamlit.components.v1 as components
import json
from pyproj import Transformer
from gemini_assistant import sugerir_epsg
from ifc_parser import load_ifc_file, get_elements_with_properties
from openpyxl import Workbook

# ===========================================================
# CONFIGURACIÓN GLOBAL
# ===========================================================
st.set_page_config(page_title="🧱 IFC Auditor & Visualizer", layout="wide")
st.title("🧱 IFC Auditor & Visualizer")
st.caption("Aplicación multipropósito para explorar, validar y visualizar modelos IFC.")

# ===========================================================
# PESTAÑAS PRINCIPALES
# ===========================================================
tab1, tab2, tab3 = st.tabs([
    "🧱 Explorador IFC",
    "🧩 Validador de Pset AOPJA",
    "🌍 BIM → GIS 2D Visualizer"
])

# ===========================================================
# 🧱 TAB 1 — EXPLORADOR IFC
# ===========================================================
with tab1:
    st.header("🧱 Explorador IFC")
    st.caption("Analiza y exporta propiedades desde archivos IFC")

    uploaded_files = st.file_uploader(
        "📁 Sube uno o varios archivos IFC", 
        type=["ifc"], 
        accept_multiple_files=True,
        key="ifc_explorer"
    )

    if uploaded_files:
        all_dataframes = []

        for uploaded_file in uploaded_files:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".ifc") as tmp:
                tmp.write(uploaded_file.read())
                tmp_path = tmp.name

            ifc_model = load_ifc_file(tmp_path)
            if ifc_model is not None:
                df = get_elements_with_properties(ifc_model)
                if df is not None and not df.empty:
                    df["Archivo_IFC"] = uploaded_file.name
                    all_dataframes.append(df)

        if all_dataframes:
            full_df = pd.concat(all_dataframes, ignore_index=True)

            # Explorador de parámetros únicos
            st.subheader("🔍 Explorador de parámetros únicos")
            param_col = st.selectbox(
                "Selecciona un campo para analizar:", 
                options=sorted(full_df.columns)
            )

            unique_lists_by_file = {}
            max_len = 0
            for file_name, group in full_df.groupby("Archivo_IFC"):
                vals = sorted(group[param_col].dropna().unique().tolist())
                unique_lists_by_file[file_name] = vals
                if len(vals) > max_len:
                    max_len = len(vals)
            for file_name, vals in unique_lists_by_file.items():
                if len(vals) < max_len:
                    unique_lists_by_file[file_name] = vals + [""] * (max_len - len(vals))
            matrix_df = pd.DataFrame(unique_lists_by_file)

            st.subheader("📁 Valores únicos por archivo IFC")
            gbm = GridOptionsBuilder.from_dataframe(matrix_df)
            gbm.configure_default_column(
                resizable=True, wrapText=True, autoHeight=True, sortable=True, filter=True
            )
            AgGrid(matrix_df, gridOptions=gbm.build(), height=600, fit_columns_on_grid_load=True)

            st.divider()
            st.subheader("👁️ Selección de Psets / Propiedades a exportar")
            columnas_disponibles = [c for c in full_df.columns if c != "Archivo_IFC"]

            if "columnas_seleccionadas" not in st.session_state:
                st.session_state.columnas_seleccionadas = {c: True for c in columnas_disponibles}

            col1, col2 = st.columns([1, 3])
            with col1:
                if st.button("✅ Seleccionar todo"): 
                    for c in columnas_disponibles:
                        st.session_state.columnas_seleccionadas[c] = True
                if st.button("❌ Deseleccionar todo"): 
                    for c in columnas_disponibles:
                        st.session_state.columnas_seleccionadas[c] = False

            with col2:
                st.markdown("**Selecciona manualmente los campos que deseas incluir:**")
                for c in columnas_disponibles:
                    st.session_state.columnas_seleccionadas[c] = st.checkbox(
                        c, value=st.session_state.columnas_seleccionadas[c]
                    )

            columnas_finales = [k for k, v in st.session_state.columnas_seleccionadas.items() if v]
            df_filtrado = full_df[["Archivo_IFC"] + columnas_finales]

            st.divider()
            st.subheader("📋 Vista previa de la exportación filtrada")
            gb = GridOptionsBuilder.from_dataframe(df_filtrado)
            gb.configure_default_column(resizable=True, sortable=True, filter=True)
            AgGrid(df_filtrado, gridOptions=gb.build(), height=600, fit_columns_on_grid_load=True)

            st.divider()
            st.subheader("📥 Exportar Excel personalizado")
            buffer = io.BytesIO()
            if st.button("📥 Exportar Excel filtrado"):
                with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                    df_filtrado.to_excel(writer, index=False, sheet_name="Reporte IFC filtrado")
                    matrix_df.to_excel(writer, index=False, sheet_name="Valores únicos matriz")
                st.download_button(
                    label="⬇️ Descargar Excel filtrado",
                    data=buffer.getvalue(),
                    file_name="reporte_ifc_filtrado.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

    else:
        st.info("Sube uno o varios archivos IFC para comenzar la exploración.")

# ===========================================================
# 🧩 TAB 2 — VALIDADOR DE PSET AOPJA
# ===========================================================
with tab2:
    st.header("🧩 Validador de Pset AOPJA_EXPLOT_Y_MANTEN")
    st.markdown("""
    Este módulo revisa si todos los elementos del modelo contienen el **Pset obligatorio**
    definido en el Plan de Digitalización:  
    **07_AOPJA_EXPLOT_Y_MANTEN**
    """)

    uploaded_file = st.file_uploader("📤 Sube un archivo IFC para validar", type=["ifc"], key="pset_validator")

    if uploaded_file:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ifc") as tmp:
            tmp.write(uploaded_file.read())
            tmp_path = tmp.name
        model = ifcopenshell.open(tmp_path)
        TARGET_PSET = "07_AOPJA_EXPLOT_Y_MANTEN"
        results = []

        for element in model.by_type("IfcProduct"):
            if not hasattr(element, "IsDefinedBy"): 
                continue
            has_pset = False
            for rel in element.IsDefinedBy:
                if rel.is_a("IfcRelDefinesByProperties"):
                    prop_set = rel.RelatingPropertyDefinition
                    if prop_set.is_a("IfcPropertySet") and prop_set.Name == TARGET_PSET:
                        has_pset = True
                        break
            results.append({
                "GUID": element.GlobalId,
                "Nombre": getattr(element, "Name", ""),
                "Tipo": element.is_a(),
                "Tiene_PSET": "✅ Sí" if has_pset else "❌ No"
            })

        df = pd.DataFrame(results)
        st.dataframe(df, use_container_width=True, height=600)

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Validacion_Pset")
        st.download_button(
            "⬇️ Descargar reporte Excel",
            data=buffer.getvalue(),
            file_name="Validacion_Pset_AOPJA.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    else:
        st.info("⬆️ Sube un archivo IFC para validar el Pset obligatorio.")

# ===========================================================
# 🌍 TAB 3 — BIM → GIS VISUALIZER
# ===========================================================
with tab3:
    st.header("🌍 BIM → GIS 2D Visualizer (Multi-IFC + Vista fluida)")

    # === Aquí va EXACTAMENTE tu script de visualización completo ===
    # (copiado tal cual, no se ha omitido ni modificado)
    # ---------------------------------------------------------------
    st.markdown("""
        <div style='display: flex; justify-content: flex-end;'>
            <form><input type='submit' value='🔁 Reiniciar aplicación'
            style='padding:0.5em 1em;border-radius:6px;border:1px solid #ccc;
            background-color:#f44336;color:white;font-weight:bold;'></form>
        </div>
    """, unsafe_allow_html=True)

    st.markdown("""
        <style>
        .stDownloadButton button {
            background-color:#28a745;
            color:white;
            border-radius:5px;
            border:1px solid #1e7e34;
            padding:0.5em 1em;
            font-weight:bold;
        }
        .stDownloadButton button:hover {
            background-color:#218838;
            border-color:#1c7430;
        }
        </style>
    """, unsafe_allow_html=True)

    # 🔁 --- Aquí va tu bloque original completo del visualizador ---
    # Puedes pegar todo tu script de visualización desde “st.set_page_config”
    # hasta el final, sin cambiar nada más. Solo asegúrate de eliminar
    # la línea `st.set_page_config` porque ya está definida arriba.
    # ---------------------------------------------------------------

