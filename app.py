import streamlit as st
import pandas as pd
import re
import os

st.set_page_config(page_title="BOM Tool v7.1", layout="wide")

# --- 1. FILENAME CONFIGURATION ---
SKU_FILE = "L0&L1 Skus..xlsx - Sheet1.csv" 
MASTER_FILE = "Item_Master_v4_Template.csv" 
LINKS_FILE = "BOM_Links_v4_Template.csv"

def clean_currency(value):
    """Safely converts currency strings (like '$0.82' or ' $- ') to floats."""
    if pd.isna(value) or value == "": return 0.0
    val_str = str(value).strip()
    if val_str == "-" or val_str == "$-": return 0.0
    # Strip everything except numbers and decimal points
    cleaned = re.sub(r'[^\d.]', '', val_str)
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0

def universal_clean(df):
    """The 'Brute Force' cleaner: Handles headers and cell data across all versions."""
    # 1. Clean Headers (Remove newlines and extra spaces)
    df.columns = [" ".join(str(c).split()) for c in df.columns]
    
    # 2. Clean Cells (Remove leading/trailing spaces from every single cell)
    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].fillna("").astype(str).str.strip()
    return df

# --- 2. LOAD DATA ---
if not all(os.path.exists(f) for f in [SKU_FILE, MASTER_FILE, LINKS_FILE]):
    st.error("🚨 Missing Files on GitHub. Please check filenames.")
    st.stop()

try:
    # Load and immediately clean
    df_master = universal_clean(pd.read_csv(MASTER_FILE, encoding='utf-8-sig', on_bad_lines='skip'))
    df_links = universal_clean(pd.read_csv(LINKS_FILE, encoding='utf-8-sig', on_bad_lines='skip'))
    df_sku_list = universal_clean(pd.read_csv(SKU_FILE, encoding='utf-8-sig', on_bad_lines='skip'))

    # Process Item Master Cost
    if 'Unit Cost' in df_master.columns:
        df_master['Unit Cost Cleaned'] = df_master['Unit Cost'].apply(clean_currency)
    else:
        # If the header cleaning failed, use the 5th column by position
        df_master['Unit Cost Cleaned'] = df_master.iloc[:, 4].apply(clean_currency)

    # Dictionary for fast lookup
    item_details = df_master.set_index('Part No.').to_dict('index')

    # Process Links by column position to avoid "Header Not Found" errors
    # 0:Parent, 1:Child, 2:Qty, 3:UOM
    parent_map = {}
    for _, row in df_links.iterrows():
        p_id = str(row.iloc[0])
        if p_id not in parent_map: parent_map[p_id] = []
        parent_map[p_id].append({
            'child': str(row.iloc[1]),
            'qty': pd.to_numeric(row.iloc[2], errors='coerce') or 1.0,
            'uom': str(row.iloc[3]) if pd.notna(row.iloc[3]) else "Ea."
        })

    # --- 3. UI ---
    st.sidebar.header("Navigation")
    ui_map = {
        "Saleable SKUs": ("Saleable Sku", "Saleable Sku Description"),
        "Base Assemblies": ("Base Assy Kit", "Base Assy Kit Description"),
        "Countertop Assemblies": ("Countertop Assy Kit", "Countertop Assy Kit Description"),
        "Cladding Assemblies": ("Cladding Assy Kit", "Cladding Assy Kit Description"),
        "Finish Kits": ("Finish Kit", "Finish Kit Description")
    }
    
    choice = st.sidebar.selectbox("Select View:", list(ui_map.keys()))
    id_col, desc_col = ui_map[choice]

    # Create dropdown list
    sku_dropdown = []
    if id_col in df_sku_list.columns:
        valid_rows = df_sku_list[df_sku_list[id_col] != ""]
        for _, row in valid_rows.drop_duplicates(subset=[id_col]).iterrows():
            sku_dropdown.append(f"{row[id_col]} | {row.get(desc_col, 'No Description')}")
    
    selection = st.selectbox(f"Choose {choice}:", ["-- Select --"] + sorted(sku_dropdown))

    if selection != "-- Select --":
        sel_id = selection.split(" | ")[0].strip()
        sel_desc = selection.split(" | ")[1].strip() if "|" in selection else ""

        # --- 4. BOM EXPLOSION ---
        results = []
        def explode_bom(parent, depth=1, multiplier=1):
            for component in parent_map.get(parent, []):
                c_id = component['child']
                total_qty = multiplier * component['qty']
                info = item_details.get(c_id, {})
                
                results.append({
                    'Level': depth,
                    'Parent': parent,
                    'Part No.': c_id,
                    'Description': info.get('Part Description', 'N/A'),
                    'Qty': component['qty'],
                    'Total Req': total_qty,
                    'UOM': component['uom'],
                    'Make/Buy': info.get('Make/Buy', 'N/A'),
                    'Fulfillment': info.get('Fulfillment', 'N/A'),
                    'Supplier': info.get('Supplier', 'N/A'),
                    'Unit Cost': info.get('Unit Cost Cleaned', 0.0),
                    'Ext. Cost': info.get('Unit Cost Cleaned', 0.0) * total_qty
                })
                explode_bom(c_id, depth + 1, total_qty)

        explode_bom(sel_id)

        if results:
            df_final = pd.DataFrame(results)
            st.metric("Total Assembly Cost", f"${df_final['Ext. Cost'].sum():,.2f}")
            
            # Formatted display
            df_show = df_final.copy()
            df_show['Unit Cost'] = df_show['Unit Cost'].map("${:,.2f}".format)
            df_show['Ext. Cost'] = df_show['Ext. Cost'].map("${:,.2f}".format)
            st.dataframe(df_show, use_container_width=True, hide_index=True)

            # --- 5. EXPORT ---
            csv_header = f"Assembly:,{sel_id}\nDescription:,{sel_desc}\n\n"
            csv_body = df_final.to_csv(index=False)
            st.download_button("📥 Download CSV Report", (csv_header + csv_body).encode('utf-8-sig'), f"BOM_{sel_id}.csv")
        else:
            st.warning(f"No components found for {sel_id}. Check if this ID exists in your BOM Links file.")

except Exception as e:
    st.error(f"Unexpected Error: {e}")
