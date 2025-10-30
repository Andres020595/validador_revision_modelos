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
from Tools import bim_ifc_to_geojson_2d as bimgeo
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
# 🌍 TAB 3 — BIM → GIS VISUALIZER (CÓDIGO COMPLETO ORIGINAL)
# ===========================================================
with tab3:
    st.header("🌍 BIM → GIS 2D Visualizer (Multi-IFC + Vista fluida)")

    # --------------------------------------------------
    # BOTÓN DE REINICIO
    # --------------------------------------------------
    st.markdown("""
        <div style='display: flex; justify-content: flex-end;'>
            <form><input type='submit' value='🔁 Reiniciar aplicación'
            style='padding:0.5em 1em;border-radius:6px;border:1px solid #ccc;
            background-color:#f44336;color:white;font-weight:bold;'></form>
        </div>
    """, unsafe_allow_html=True)

    # --------------------------------------------------
    # ESTILOS PERSONALIZADOS
    # --------------------------------------------------
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

    st.sidebar.header("🔍 Subir archivos IFC")
    uploaded_files = st.sidebar.file_uploader(
        "Selecciona uno o varios archivos IFC",
        type=["ifc"],
        accept_multiple_files=True,
        key="ifc_gis"
    )

    if "ifc_models" not in st.session_state:
        st.session_state.ifc_models = {}
    if "geojson_data" not in st.session_state:
        st.session_state.geojson_data = None
    if "selected_props" not in st.session_state:
        st.session_state.selected_props = []
    if "entity_choices" not in st.session_state:
        st.session_state.entity_choices = []
    if "all_props" not in st.session_state:
        st.session_state.all_props = []
    if "available_prop_keys" not in st.session_state:
        st.session_state.available_prop_keys = []
    if "crs_input" not in st.session_state:
        st.session_state.crs_input = "EPSG:25830 → EPSG:4326"

    # --------------------------------------------------
    # PASO 1 – GEORREFERENCIACIÓN
    # --------------------------------------------------
    st.sidebar.header("🌍 Georreferenciación del proyecto")
    st.session_state.crs_input = st.sidebar.text_input(
        "✍️ Introduce el sistema CRS manual (opcional)",
        value=st.session_state.crs_input,
        key="crs_input_key"
    )

    ubicacion_texto = st.sidebar.text_input("📍 Describe la ubicación del proyecto (para sugerencia IA)", value="")

    if st.sidebar.button("🔎 Sugerir CRS con Gemini") and ubicacion_texto:
        with st.spinner("Consultando IA..."):
            try:
                sugerido = sugerir_epsg(ubicacion_texto)
                st.session_state.crs_input = f"{sugerido} → EPSG:4326"
                st.sidebar.success(f"CRS sugerido: {sugerido}")
            except Exception as e:
                st.sidebar.error(f"No se pudo obtener sugerencia de IA: {e}")

    try:
        from_crs, to_crs = [s.strip() for s in st.session_state.crs_input.split("→")]
        transformer = Transformer.from_crs(from_crs, to_crs, always_xy=True)
        bimgeo.set_transformer(transformer)
        st.sidebar.info(f"CRS en uso: {from_crs} → {to_crs}")
    except Exception as e:
        st.error(f"❌ Error en configuración CRS: {e}")
        st.stop()

    # --------------------------------------------------
    # PASO 2 – CARGA DE IFC
    # --------------------------------------------------
    if uploaded_files:
        for uploaded_file in uploaded_files:
            if uploaded_file.name not in st.session_state.ifc_models:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".ifc") as tmp_ifc:
                    tmp_ifc.write(uploaded_file.read())
                    tmp_ifc_path = tmp_ifc.name
                model = bimgeo.load_ifc(tmp_ifc_path)
                st.session_state.ifc_models[uploaded_file.name] = model

    # --------------------------------------------------
    # PASO 3 – ENTIDADES Y PROPIEDADES
    # --------------------------------------------------
    if st.session_state.ifc_models:
        entity_types = set()
        for model in st.session_state.ifc_models.values():
            entity_types.update(bimgeo.get_entity_types(model))
        entity_types = sorted(entity_types)

        st.sidebar.header("🏷️ Selección de entidades")
        all_selected = st.sidebar.checkbox("Seleccionar todos", value=False)

        entity_choices = []
        for etype in entity_types:
            default = all_selected or (etype in st.session_state.entity_choices or etype == "IfcProduct")
            if st.sidebar.checkbox(etype, value=default, key=f"etype_{etype}"):
                entity_choices.append(etype)

        if st.sidebar.button("✅ Confirmar entidades"):
            st.session_state.entity_choices = entity_choices
            all_props = []

            for file_name, model in st.session_state.ifc_models.items():
                for entity_choice in st.session_state.entity_choices:
                    props = bimgeo.extract_ifc_properties(model, entity_choice)
                    for p in props:
                        p["Source_File"] = file_name
                    all_props.extend(props)

            all_keys = set()
            for p in all_props:
                all_keys.update(p.keys())

            st.session_state.available_prop_keys = sorted(all_keys)
            st.session_state.all_props = all_props

    if st.session_state.available_prop_keys:
        st.sidebar.header("🧩 Selección de propiedades")
        selected_props = []
        for prop in st.session_state.available_prop_keys:
            if st.sidebar.checkbox(
                prop,
                value=(prop in st.session_state.selected_props or prop in ["IFC_ID", "IFC_Type", "Source_File"]),
                key=f"prop_{prop}"
            ):
                selected_props.append(prop)

        if st.sidebar.button("🚀 Procesar y generar GeoJSON"):
            st.session_state.selected_props = selected_props
            all_features, all_centroids = [], []

            for file_name, model in st.session_state.ifc_models.items():
                for entity_choice in st.session_state.entity_choices:
                    entities = bimgeo.get_entities_with_geometry(model, entity_choice)
                    features = bimgeo.extract_clean_geometry_2D(entities)
                    centroids = bimgeo.calculate_centroids(features)
                    for f in features:
                        f["properties"]["Source_File"] = file_name
                    all_features.extend(features)
                    all_centroids.extend(centroids)

            if all_features:
                st.session_state.geojson_data = bimgeo.build_geojson(
                    all_features,
                    all_centroids,
                    st.session_state.all_props or [],
                    st.session_state.selected_props or []
                )
                st.success(
                    f"✅ Se procesaron {len(all_features)} entidades con geometría "
                    f"de {len(st.session_state.ifc_models)} archivos IFC."
                )

    # --------------------------------------------------
    # PASO 4 – MAPA FLUIDO
    # --------------------------------------------------
    if st.session_state.geojson_data:
        try:
            first_coords = st.session_state.geojson_data["features"][0]["geometry"]["coordinates"]
            while isinstance(first_coords[0], list):
                first_coords = first_coords[0]
            lat, lon = first_coords[0][1], first_coords[0][0]
        except Exception as e:
            st.error(f"No se pudo determinar el centro del mapa: {e}")
            st.stop()

        m = folium.Map(location=[lat, lon], zoom_start=18, max_zoom=30, control_scale=True, prefer_canvas=True)

        normal_tiles = folium.TileLayer("OpenStreetMap", name="🗺️ Calles", control=False)
        sat_tiles = folium.TileLayer(
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            attr="Esri World Imagery",
            name="🛰️ Satélite (Esri)",
            control=False
        )
        normal_tiles.add_to(m)
        sat_tiles.add_to(m)

        features_by_file = {}
        for feature in st.session_state.geojson_data["features"]:
            src = feature["properties"].get("Source_File", "Desconocido")
            features_by_file.setdefault(src, []).append(feature)

        base_group = folium.FeatureGroup(name="📦 Entidades IFC", show=True).add_to(m)
        color_palette = [
            "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
            "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"
        ]

        for i, (src, feats) in enumerate(features_by_file.items()):
            color = color_palette[i % len(color_palette)]
            layer = FeatureGroupSubGroup(base_group, name=f"📁 {src}")
            m.add_child(layer)
            for feat in feats:
                folium.GeoJson(
                    feat,
                    tooltip=folium.GeoJsonTooltip(fields=st.session_state.selected_props),
                    style_function=lambda f, color=color: {
                        "fillColor": color,
                        "color": "black",
                        "weight": 1,
                        "fillOpacity": 0.7
                    },
                    highlight_function=lambda x: {"weight": 3, "fillColor": "#FFFF00"}
                ).add_to(layer)

        folium.LayerControl(collapsed=False, position="topright").add_to(m)

        toggle_js = """
            <script>
            let current = 'normal';
            function toggleTiles(){
                const osm = document.querySelectorAll('img.leaflet-tile[src*="tile.openstreetmap.org"]');
                const sat = document.querySelectorAll('img.leaflet-tile[src*="arcgisonline.com"]');
                if(current === 'normal'){
                    osm.forEach(t=>t.style.display='none');
