import streamlit as st
import pandas as pd
import re
import os

st.set_page_config(page_title="BOM Tool v7.0", layout="wide")

# --- 1. FILENAME CONFIGURATION ---
SKU_FILE = "L0&L1 Skus..xlsx - Sheet1.csv" 
MASTER_FILE = "Item_Master_v4_Template.csv" 
LINKS_FILE = "BOM_Links_v4_Template.csv"

def clean_currency(value):
    """Handles $, commas, spaces, and the '$-' placeholder found in your CSV."""
    if pd.isna(value) or value == "": return 0.0
    if isinstance(value, str):
        # Remove everything except numbers and decimals
        cleaned = re.sub(r'[^\d.]', '', value)
        try:
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            return 0.0
    return float(value)

def robust_clean(df):
    """Cleans headers and string data safely across all Pandas versions."""
    # Clean headers: remove invisible spaces and newlines
    df.columns = [re.sub(r'\s+', ' ', str(c).strip()) for c in df.columns]
    
    # Clean cell data: strip whitespace from all text columns
    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].astype(str).str.strip()
    return df

# --- 2. FILE CHECK ---
if not all(os.path.exists(f) for f in [SKU_FILE, MASTER_FILE, LINKS_FILE]):
    st.error("🚨 Missing source files. Ensure all CSVs are named correctly on GitHub.")
    st.stop()

try:
    # --- 3. DATA LOADING ---
    df_master = robust_clean(pd.read_csv(MASTER_FILE, encoding='utf-8-sig'))
    df_links = robust_clean(pd.read_csv(LINKS_FILE, encoding='utf-8-sig'))
    df_sku_list = robust_clean(pd.read_csv(SKU_FILE, encoding='utf-8-sig'))

    # Process Master Data
    cost_col = 'Unit Cost' # The robust_clean handles the extra spaces now
    if cost_col not in df_master.columns:
        # Fallback if the header is completely different
        cost_col = df_master.columns[4] 

    df_master['Unit Cost Cleaned'] = df_master[cost_col].apply(clean_currency)
    
    # Ensure Procurement columns exist
    for col in ['Fulfillment', 'Supplier']:
        if col not in df_master.columns:
            df_master[col] = "Not Set"

    item_details = df_master.set_index('Part No.').to_dict('index')

    # Process Links Data - Map by index to handle 'UM' vs 'UOM' variations
    # 0:Parent, 1:Child, 2:Qty, 3:UOM
    parent_map = {}
    for _, row in df_links.iterrows():
        p = str(row.iloc[0]) # Parent Part
        if p not in parent_map: parent_map[p] = []
        parent_map[p].append({
            'child': str(row.iloc[1]), # Child Part
            'qty': pd.to_numeric(row.iloc[2], errors='coerce') or 1.0,
            'uom': str(row.iloc[3]) if pd.notna(row.iloc[3]) else "Ea."
        })

    # --- 4. UI SIDEBAR ---
    ui_option = st.sidebar.radio("Category:", ["Option 1: Saleable SKUs", "Option 2: Base Assemblies", "Option 3: Countertop Assemblies", "Option 4: Cladding Assemblies", "Option 5: Finish Kits"])
    
    mapping = {
        "Option 1: Saleable SKUs": ("Saleable Sku", "Saleable Sku Description"),
        "Option 2: Base Assemblies": ("Base Assy Kit", "Base Assy Kit Description"),
        "Option 3: Countertop Assemblies": ("Countertop Assy Kit", "Countertop Assy Kit Description"),
        "Option 4: Cladding Assemblies": ("Cladding Assy Kit", "Cladding Assy Kit Description"),
        "Option 5: Finish Kits": ("Finish Kit", "Finish Kit Description")
    }

    id_col, desc_col = mapping[ui_option]
    sku_options = []
    if id_col in df_sku_list.columns:
        valid_skus = df_sku_list[df_sku_list[id_col].notna()]
        sku_options = [f"{row[id_col]} | {row[desc_col]}" for _, row in valid_skus.drop_duplicates(subset=[id_col]).iterrows() if str(row[id_col]).lower() != 'nan']

    selected_label = st.selectbox(f"Select {ui_option}", ["-- Select --"] + sorted(sku_options))

    if selected_label != "-- Select --":
        parts = selected_label.split(" | ")
        selected_sku = parts[0].strip()
        selected_desc = parts[1].strip() if len(parts) > 1 else "N/A"
        
        # --- 5. BOM EXPLOSION ---
        waterfall = []
        def explode(parent_id, depth=1, mult=1):
            for item in parent_map.get(parent_id, []):
                child_id = item['child']
                total_qty = mult * item['qty']
                det = item_details.get(child_id, {})
                
                waterfall.append({
                    'BOM Level': depth,
                    'Parent': parent_id,
                    'Part No.': child_id,
                    'Indented': "." * depth + child_id,
                    'Description': det.get('Part Description', 'N/A'),
                    'Category': det.get('Category', 'N/A'),
                    'Make/Buy': det.get('Make/Buy', 'N/A'),
                    'Fulfillment': det.get('Fulfillment', ''),
                    'Supplier': det.get('Supplier', ''),
                    'Qty Per': item['qty'],
                    'UOM': item['uom'],
                    'Total Req.': total_qty,
                    'Unit Cost': det.get('Unit Cost Cleaned', 0.0),
                    'Ext. Cost': det.get('Unit Cost Cleaned', 0.0) * total_qty
                })
                explode(child_id, depth + 1, total_qty)

        explode(selected_sku)

        if waterfall:
            df_wf = pd.DataFrame(waterfall)
            st.metric("Total Roll-up Cost", f"${df_wf['Ext. Cost'].sum():,.2f}")

            # Display Table
            df_disp = df_wf.copy()
            df_disp['Unit Cost'] = df_disp['Unit Cost'].apply(lambda x: f"${x:,.2f}")
            df_disp['Ext. Cost'] = df_disp['Ext. Cost'].apply(lambda x: f"${x:,.2f}")
            st.dataframe(df_disp, use_container_width=True, hide_index=True)
            
            # --- 6. EXPORT ---
            export_cols = ['BOM Level', 'Parent', 'Part No.', 'Description', 'Category', 'Make/Buy', 'Fulfillment', 'Supplier', 'Qty Per', 'UOM', 'Total Req.', 'Unit Cost', 'Ext. Cost']
            header_str = f"Assembly Number:, {selected_sku}\nDescription:, {selected_desc}\n\n"
            table_str = df_wf[export_cols].to_csv(index=False)
            csv_data = (header_str + table_str).encode('utf-8-sig')
            
            st.download_button(label="📥 Download Extended BOM", data=csv_data, file_name=f"BOM_{selected_sku}.csv", mime="text/csv")
        else:
            st.warning(f"⚠️ No components found for {selected_sku}. Check if this ID is in the Parent column of your Links file.")

except Exception as e:
    st.error(f"Application Error: {e}")
