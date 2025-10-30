import streamlit as st
import ifcopenshell
import ifcopenshell.util.element
from anytree import Node, RenderTree
from io import StringIO

# -----------------------------------------------------------
# CONFIGURACIÓN BÁSICA
# -----------------------------------------------------------
st.set_page_config(page_title="🔍 Estructura IFC - Auditoría B.4", layout="wide")
st.title("🔍 Visualización de la Estructura Espacial IFC (ID B.4)")
st.markdown("""
Esta herramienta permite inspeccionar la **estructura jerárquica** del modelo IFC  
(IfcProject → IfcSite → IfcBuilding → IfcBuildingStorey → Elementos)  
para verificar si cumple con el criterio **B.4** del checklist de auditoría.
""")

# -----------------------------------------------------------
# SUBIR ARCHIVO IFC
# -----------------------------------------------------------
uploaded_file = st.file_uploader("📤 Sube un archivo IFC", type=["ifc"])

if uploaded_file:
    # Guardar archivo temporalmente
    with open("temp.ifc", "wb") as f:
        f.write(uploaded_file.read())
    
    # Cargar IFC
    try:
        ifc = ifcopenshell.open("temp.ifc")
        st.success("✅ Archivo IFC cargado correctamente.")
    except Exception as e:
        st.error(f"Error al abrir el IFC: {e}")
        st.stop()

    # -----------------------------------------------------------
    # FUNCIÓN RECURSIVA PARA CREAR ÁRBOL
    # -----------------------------------------------------------
    def crear_nodo(elemento, padre=None):
        nombre = elemento.Name or "(sin nombre)"
        tipo = elemento.is_a()
        texto = f"{tipo} — {nombre}"
        nodo = Node(texto, parent=padre)
        hijos = ifcopenshell.util.element.get_decomposition(elemento)
        for hijo in hijos:
            crear_nodo(hijo, nodo)
        return nodo

    # -----------------------------------------------------------
    # GENERAR Y MOSTRAR ÁRBOL
    # -----------------------------------------------------------
    proyecto = ifc.by_type("IfcProject")
    if not proyecto:
        st.error("❌ No se ha encontrado ningún IfcProject en el modelo.")
    else:
        proyecto = proyecto[0]
        raiz = crear_nodo(proyecto)

        # Mostrar en texto
        st.subheader("🌳 Estructura jerárquica del modelo IFC")
        salida = StringIO()
        for pre, _, node in RenderTree(raiz):
            # Colores según tipo
            if "IfcSite" in node.name:
                color = "🟩"
            elif "IfcBuilding" in node.name:
                color = "🏢"
            elif "IfcBuildingStorey" in node.name:
                color = "📊"
            elif "IfcProject" in node.name:
                color = "📁"
            else:
                color = "▫️"
            salida.write(f"{pre}{color} {node.name}\n")

        st.text(salida.getvalue())

        # -----------------------------------------------------------
        # ANÁLISIS SIMPLE DE CUMPLIMIENTO B.4
        # -----------------------------------------------------------
        sites = ifc.by_type("IfcSite")
        buildings = ifc.by_type("IfcBuilding")
        storeys = ifc.by_type("IfcBuildingStorey")

        if not sites or not buildings or not storeys:
            st.warning("⚠️ El modelo no tiene estructura completa (Site, Building, Storey).")
            st.markdown("**Resultado:** ❌ *No cumple con B.4*")
        else:
            # Comprobamos si hay elementos fuera de storeys
            elementos_fuera = []
            for elem in ifc.by_type("IfcElement"):
                contenedor = ifcopenshell.util.element.get_container(elem)
                if contenedor and not contenedor.is_a("IfcBuildingStorey"):
                    elementos_fuera.append(elem)
            
            if len(elementos_fuera) > 0:
                st.warning(f"⚠️ Se encontraron {len(elementos_fuera)} elementos fuera de niveles (IfcBuildingStorey).")
                st.markdown("**Resultado:** 🟠 *Aprobado con comentarios (AC)*")
            else:
                st.success("✅ Todos los elementos están correctamente agrupados en niveles.")
                st.markdown("**Resultado:** 🟢 *Cumple con B.4*")

else:
    st.info("⬆️ Sube un archivo IFC para analizar su estructura jerárquica.")
