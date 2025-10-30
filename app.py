import streamlit as st
import pandas as pd
import tempfile
import io
import ifcopenshell
from ifc_parser import load_ifc_file, get_elements_with_properties
from st_aggrid import AgGrid, GridOptionsBuilder
from openpyxl import Workbook

# ===========================================================
# CONFIGURACIÓN GLOBAL
# ===========================================================
st.set_page_config(page_title="🧱 IFC Auditor & Visualizer", layout="wide")
st.title("🧱 IFC Auditor & Visualizer")
st.caption("Aplicación multipropósito para explorar y validar modelos IFC.")

# ===========================================================
# 📂 CARGA GLOBAL DE ARCHIVOS IFC
# ===========================================================
st.sidebar.header("📂 Carga de modelos IFC (común a todas las pestañas)")
uploaded_files = st.sidebar.file_uploader(
    "Sube uno o varios archivos IFC", 
    type=["ifc"], 
    accept_multiple_files=True,
    key="ifc_global"
)

if uploaded_files:
    if "ifc_models" not in st.session_state:
        st.session_state.ifc_models = {}

    for uploaded_file in uploaded_files:
        if uploaded_file.name not in st.session_state.ifc_models:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".ifc") as tmp:
                tmp.write(uploaded_file.read())
                tmp_path = tmp.name
            model = load_ifc_file(tmp_path)
            if model:
                st.session_state.ifc_models[uploaded_file.name] = model

    st.sidebar.success(f"✅ {len(st.session_state.ifc_models)} archivos cargados correctamente.")
else:
    st.sidebar.info("⬆️ Carga uno o varios archivos IFC para comenzar.")

# ===========================================================
# PESTAÑAS PRINCIPALES
# ===========================================================
tab1, tab2 = st.tabs([
    "🧱 Explorador IFC",
    "🧩 Validador de Pset AOPJA"
])

# ===========================================================
# 🧱 TAB 1 — EXPLORADOR IFC
# ===========================================================
with tab1:
    st.header("🧱 Explorador IFC")
    st.caption("Analiza y exporta propiedades desde los archivos IFC cargados.")

    if st.session_state.get("ifc_models"):
        all_dataframes = []

        for file_name, ifc_model in st.session_state.ifc_models.items():
            df = get_elements_with_properties(ifc_model)
            if df is not None and not df.empty:
                df["Archivo_IFC"] = file_name
                all_dataframes.append(df)

        if all_dataframes:
            full_df = pd.concat(all_dataframes, ignore_index=True)

            # ----------------------------------------
            # Explorador de parámetros únicos
            # ----------------------------------------
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
                max_len = max(max_len, len(vals))

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

            # ----------------------------------------
            # Selección de columnas
            # ----------------------------------------
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

            # ----------------------------------------
            # Vista previa
            # ----------------------------------------
            st.divider()
            st.subheader("📋 Vista previa de la exportación filtrada")
            gb = GridOptionsBuilder.from_dataframe(df_filtrado)
            gb.configure_default_column(resizable=True, sortable=True, filter=True)
            AgGrid(df_filtrado, gridOptions=gb.build(), height=600, fit_columns_on_grid_load=True)

            # ----------------------------------------
            # Exportación
            # ----------------------------------------
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
        st.info("📁 Carga uno o varios archivos IFC desde la barra lateral para comenzar.")

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

    if st.session_state.get("ifc_models"):
        TARGET_PSET = "07_AOPJA_EXPLOT_Y_MANTEN"
        all_results = []

        for file_name, model in st.session_state.ifc_models.items():
            results = []
            for element in model.by_type("IfcProduct"):
                if not hasattr(element, "IsDefinedBy"):
                    continue
                has_pset = any(
                    rel.is_a("IfcRelDefinesByProperties")
                    and rel.RelatingPropertyDefinition.is_a("IfcPropertySet")
                    and rel.RelatingPropertyDefinition.Name == TARGET_PSET
                    for rel in element.IsDefinedBy
                )
                results.append({
                    "Archivo_IFC": file_name,
                    "GUID": element.GlobalId,
                    "Nombre": getattr(element, "Name", ""),
                    "Tipo": element.is_a(),
                    "Tiene_PSET": "✅ Sí" if has_pset else "❌ No"
                })
            all_results.extend(results)

        df = pd.DataFrame(all_results)
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
        st.info("⬆️ Carga uno o varios archivos IFC desde la barra lateral para validar.")
