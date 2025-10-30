import ifcopenshell
import ifcopenshell.util.element
import pandas as pd


def load_ifc_file(file_path):
    try:
        return ifcopenshell.open(file_path)
    except Exception as e:
        print(f"Error al abrir el archivo IFC: {e}")
        return None


def get_elements_with_properties(ifc_model):
    elements_data = []

    # Filtrar solo entidades de tipo IfcProduct (paredes, puertas, etc.)
    products = ifc_model.by_type("IfcProduct")

    for product in products:
        if not hasattr(product, "IsDefinedBy"):
            continue

        guid = product.GlobalId
        name = product.Name or ""
        type_name = product.is_a()

        props_dict = {
            "GUID": guid,
            "Name": name,
            "Type": type_name,
        }

        # Recorremos las definiciones de propiedades (Psets)
        for rel in product.IsDefinedBy:
            if rel.is_a("IfcRelDefinesByProperties"):
                prop_set = rel.RelatingPropertyDefinition

                if prop_set.is_a("IfcPropertySet"):
                    pset_name = prop_set.Name

                    for prop in prop_set.HasProperties:
                        if hasattr(prop, "Name") and hasattr(prop, "NominalValue"):
                            key = f"{pset_name}.{prop.Name}"
                            props_dict[key] = str(prop.NominalValue.wrappedValue)

        elements_data.append(props_dict)

    return pd.DataFrame(elements_data)
