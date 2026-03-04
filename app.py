import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="BOM Tool v5.2", layout="wide")

# --- FILE CONFIGURATION ---
SKU_FILE = "SKU_Mapping.csv"
MASTER_FILE = "Item_Master_v4_Template.csv" 
LINKS_FILE = "BOM_Links_v4_Template.csv"

def clean_currency(value):
    if pd.isna(value) or value == "": return 0.0
    if isinstance(value, str):
        cleaned = re.sub(r'[^\d.]', '', value)
        return float(cleaned) if cleaned else 0.0
    return float(value)

try:
    # --- LOAD DATA ---
    df_master = pd.read_csv(MASTER_FILE, encoding='utf-8-sig')
    df_links = pd.read_csv(LINKS_FILE, encoding='utf-8-sig')
    df_sku_list = pd.read_csv(SKU_FILE, encoding='utf-8-sig')

    # --- CLEAN MAPPING HEADERS ---
    df_sku_list.columns = [c.strip() for c in df_sku_list.columns]
    # Standardize the Cladding header to fix the double-space bug
    df_sku_list.rename(columns={'Cladding Assy Kit  Description': 'Cladding Assy Kit Description'}, inplace=True)

    # --- CLEAN MASTER & LINKS ---
    df_master['Part No.'] = df_master['Part No.'].astype(str).str.strip()
    df_master['Unit Cost'] = df_master['Unit Cost'].apply(clean_currency)
    item_details = df_master.set_index('Part No.').to_dict('index')

    df_links.columns = ['Parent Part', 'Child Part', 'Qty Per'] + list(df_links.columns[3:])
    df_links['Parent Part'] = df_links['Parent Part'].astype(str).str.strip()
    df_links['Child Part'] = df_links['Child Part'].astype(str).str.strip()
    df_links['Qty Per'] = pd.to_numeric(df_links['Qty Per'], errors='coerce').fillna(1.0)

    # --- BUILD HIERARCHY MAP ---
    parent_map = {}
    for _, row in df_links.iterrows():
        p, c, q = row['Parent Part'], row['Child Part'], row['Qty Per']
        if p not in parent_map: parent_map[p] = []
        parent_map[p].append((c, q))

    # --- UI SIDEBAR ---
    st.sidebar.header("Select UI Option")
    ui_option = st.sidebar.radio(
        "Choose Assembly Category:",
        ["Option 1: Saleable SKUs (0 Prefix)", "Option 2: Base Assemblies", 
         "Option 3: Countertop Assemblies", "Option 4: Cladding Assemblies", "Option 5: Finish Kits"]
    )

    mapping = {
        "Option 1: Saleable SKUs (0 Prefix)": ("Saleable Sku", "Saleable Sku Description"),
        "Option 2: Base Assemblies": ("Base Assy Kit", "Base Assy Kit Description"),
        "Option 3: Countertop Assemblies": ("Countertop Assy Kit", "Countertop Assy Kit Description"),
        "Option 4: Cladding Assemblies": ("Cladding Assy Kit", "Cladding Assy Kit Description"),
        "Option 5: Finish Kits": ("Finish Kit", "Finish Kit Description")
    }

    id_col, desc_col = mapping[ui_option]
    
    # Generate Dropdown Options
    sku_options = []
    unique_rows = df_sku_list.drop_duplicates(subset=[id_col])
    for _, row in unique_rows.iterrows():
        p_id = str(row[id_col]).strip()
        p_desc = str(row[desc_col]).strip()
        if p_id and p_id.lower() != "nan":
            sku_options.append(f"{p_id} | {p_desc}")

    selected_label = st.selectbox(f"Select from {ui_option}", ["-- Select --"] + sorted(sku_options))

    if selected_label != "-- Select --":
        selected_sku = selected_label.split(" | ")[0].strip()
        selected_name = selected_label.split(" | ")[1].strip()

        # --- HEADER DISPLAY ---
        st.markdown("---")
        st.header(f"BOM Breakdown: {selected_sku}")
        st.subheader(f"Description: {selected_name}")
        st.markdown("---")

        # --- EXPLODE BOM ---
        waterfall = []
        def explode(parent, depth=0, mult=1):
            for child, qty in parent_map.get(parent, []):
                total_qty = mult * qty
                det = item_details.get(child, {})
                u_cost = det.get('Unit Cost', 0.0)
                waterfall.append({
                    'Level': f"{'..' * depth}↳ {child}",
                    'Part No.': child,
                    'Description': det.get('Part Description', 'N/A'),
                    'Qty Per': qty,
                    'Total Req.': total_qty,
                    'Unit Cost': f"${u_cost:,.2f}",
                    'Ext. Cost': u_cost * total_qty
                })
                explode(child, depth + 1, total_qty)

        explode(selected_sku)

        if waterfall:
            df_wf = pd.DataFrame(waterfall)
            
            # Summary Metrics
            m1, m2 = st.columns(2)
            total_cost = df_wf['Ext. Cost'].sum()
            m1.metric("Total Roll-up Cost", f"${total_cost:,.2f}")
            m2.metric("Total Components", f"{int(df_wf['Total Req.'].sum())}")

            # Data Table
            df_display = df_wf.copy()
            df_display['Ext. Cost'] = df_display['Ext. Cost'].apply(lambda x: f"${x:,.2f}")
            st.dataframe(df_display, use_container_width=True, hide_index=True)
            
            # --- RESTORED DOWNLOAD BUTTON ---
            csv_data = df_wf.to_csv(index=False).encode('utf-8')
            st.download_button(
                label=f"📥 Download {selected_sku} BOM as CSV",
                data=csv_data,
                file_name=f"BOM_{selected_sku}.csv",
                mime="text/csv",
            )
        else:
            st.warning("⚠️ No components found for this ID in the BOM Links file.")

except Exception as e:
    st.error(f"Critical System Error: {e}")
