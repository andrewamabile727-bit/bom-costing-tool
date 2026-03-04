import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="BOM Costing Tool v5.0", layout="wide")

# --- FILE CONFIGURATION ---
MASTER_FILE = "Item_Master_v4_Template.csv" 
LINKS_FILE = "BOM_Links_v4_Template.csv"
SKU_FILE = "SKU_Mapping.csv"

def clean_currency(value):
    if pd.isna(value) or value == "": return 0.0
    if isinstance(value, str):
        cleaned = re.sub(r'[^\d.]', '', value)
        return float(cleaned) if cleaned else 0.0
    return float(value)

st.title("📦 Manufacturing BOM & Costing Tool")

try:
    # --- LOAD ALL DATA ---
    df_master = pd.read_csv(MASTER_FILE, encoding='utf-8-sig')
    df_links = pd.read_csv(LINKS_FILE, encoding='utf-8-sig')
    df_sku_list = pd.read_csv(SKU_FILE, encoding='utf-8-sig')
    
    # --- DATA CLEANING ---
    df_master['Part No.'] = df_master['Part No.'].astype(str).str.strip()
    df_master['Unit Cost'] = df_master['Unit Cost'].apply(clean_currency)
    item_details = df_master.set_index('Part No.').to_dict('index')

    df_links = df_links.iloc[:, :3] 
    df_links.columns = ['Parent Part', 'Child Part', 'Qty Per']
    df_links['Parent Part'] = df_links['Parent Part'].astype(str).str.strip()
    df_links['Child Part'] = df_links['Child Part'].astype(str).str.strip()
    df_links['Qty Per'] = pd.to_numeric(df_links['Qty Per'], errors='coerce').fillna(1.0)

    # --- HIERARCHY MAPPING ---
    parent_map = {}
    for _, row in df_links.iterrows():
        p, c, q = row['Parent Part'], row['Child Part'], row['Qty Per']
        if p not in parent_map: parent_map[p] = []
        parent_map[p].append((c, q))

    # --- UI CATEGORY SELECTOR ---
    st.sidebar.header("Select UI Option")
    ui_option = st.sidebar.radio(
        "Choose Assembly Category:",
        [
            "Option 1: Saleable SKUs (0 Prefix)",
            "Option 2: Base Assemblies",
            "Option 3: Countertop Assemblies",
            "Option 4: Cladding Assemblies",
            "Option 5: Finish Kits"
        ]
    )

    # Define Column Mappings based on the SKU file
    mapping = {
        "Option 1: Saleable SKUs (0 Prefix)": ("Saleable Sku", "Saleable Sku Description"),
        "Option 2: Base Assemblies": ("Base Assy Kit", "Base Assy Kit Description"),
        "Option 3: Countertop Assemblies": ("Countertop Assy Kit", "Countertop Assy Kit Description"),
        "Option 4: Cladding Assemblies": ("Cladding Assy Kit", "Cladding Assy Kit  Description"),
        "Option 5: Finish Kits": ("Finish Kit", "Finish Kit Description")
    }

    id_col, desc_col = mapping[ui_option]
    
    # Build list of options for the dropdown
    sku_options = []
    unique_skus = df_sku_list.drop_duplicates(subset=[id_col])
    for _, row in unique_skus.iterrows():
        part_id = str(row[id_col]).strip()
        part_desc = str(row[desc_col]).strip()
        if part_id and part_id != "nan":
            sku_options.append(f"{part_id} | {part_desc}")

    sku_options = sorted(sku_options)

    # --- SEARCH & SELECTION ---
    search_query = st.sidebar.text_input("Search within this list", "")
    if search_query:
        sku_options = [opt for opt in sku_options if search_query.upper() in opt.upper()]

    selected_label = st.selectbox(f"Select from {ui_option}", ["-- Select --"] + sku_options)

    if selected_label != "-- Select --":
        selected_sku = selected_label.split(" | ")[0].strip()
        # Find description from SKU list or Master
        selected_desc = selected_label.split(" | ")[1].strip()

        # --- HEADER ---
        st.markdown("---")
        st.header(f"BOM Breakdown: {selected_sku}")
        st.subheader(f"Description: {selected_desc}")
        st.markdown("---")

        # --- WATERFALL CALCULATION ---
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
                    'Category': det.get('Category', 'N/A'),
                    'Qty Per': qty,
                    'Total Req.': total_qty,
                    'Unit Cost': f"${u_cost:,.2f}",
                    'Ext. Cost': u_cost * total_qty
                })
                explode(child, depth + 1, total_qty)

        explode(selected_sku)
        
        if waterfall:
            df_wf = pd.DataFrame(waterfall)
            
            # Metrics
            c1, c2 = st.columns(2)
            c1.metric("Total Roll-up Cost", f"${df_wf['Ext. Cost'].sum():,.2f}")
            c2.metric("Total Components", f"{int(df_wf['Total Req.'].sum())} parts")
            
            # Formatting table for view
            df_display = df_wf.copy()
            df_display['Ext. Cost'] = df_display['Ext. Cost'].apply(lambda x: f"${x:,.2f}")
            st.dataframe(df_display, use_container_width=True, hide_index=True)
            
            # Export CSV button
            csv = df_wf.to_csv(index=False).encode('utf-8')
            st.download_button(f"Export {selected_sku} BOM", csv, f"BOM_{selected_sku}.csv", "text/csv")
        else:
            st.warning("⚠️ No children found for this assembly in the BOM Links file. Please ensure this Part Number is listed as a Parent in the Links file.")

except Exception as e:
    st.error(f"Critical System Error: {e}")
    st.info("Check that all files (Item Master, BOM Links, and SKU List) are uploaded to GitHub correctly.")
