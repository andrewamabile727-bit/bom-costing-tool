import streamlit as st
import pandas as pd
import re
import os

st.set_page_config(page_title="BOM Tool v6.9", layout="wide")

# --- 1. FILENAME CONFIGURATION ---
SKU_FILE = "L0&L1 Skus..xlsx - Sheet1.csv" 
MASTER_FILE = "Item_Master_v4_Template.csv" 
LINKS_FILE = "BOM_Links_v4_Template.csv"

def clean_currency(value):
    if pd.isna(value) or value == "": return 0.0
    if isinstance(value, str):
        cleaned = re.sub(r'[^\d.]', '', value)
        return float(cleaned) if cleaned else 0.0
    return float(value)

def super_clean_df(df):
    """
    Cleans dataframes by stripping spaces from headers and values.
    This prevents 'Column Not Found' errors caused by Excel formatting.
    """
    df.columns = [str(c).strip() for c in df.columns]
    df.columns = [" ".join(str(c).split()) for c in df.columns]
    # Use map instead of applymap for modern pandas compatibility
    df = df.map(lambda x: x.strip() if isinstance(x, str) else x)
    return df

# --- 2. FILE CHECK ---
if not all(os.path.exists(f) for f in [SKU_FILE, MASTER_FILE, LINKS_FILE]):
    st.error("🚨 Missing source files in GitHub directory. Please ensure all CSVs are uploaded.")
    st.stop()

try:
    # --- 3. DATA LOADING ---
    df_master = super_clean_df(pd.read_csv(MASTER_FILE, encoding='utf-8-sig'))
    df_links = super_clean_df(pd.read_csv(LINKS_FILE, encoding='utf-8-sig'))
    df_sku_list = super_clean_df(pd.read_csv(SKU_FILE, encoding='utf-8-sig'))

    # Clean Costs & Ensure Procurement columns exist (v6.7+ requirement)
    if 'Unit Cost' in df_master.columns:
        df_master['Unit Cost'] = df_master['Unit Cost'].apply(clean_currency)
    else:
        st.error("Column 'Unit Cost' not found in Item Master. Check for spelling/spaces.")
        st.stop()

    for col in ['Fulfillment', 'Supplier']:
        if col not in df_master.columns:
            df_master[col] = ""

    item_details = df_master.set_index('Part No.').to_dict('index')

    # Process Links Data - Handle 'UM' or 'UOM' variations
    # We map by index to ensure stability: 0:Parent, 1:Child, 2:Qty, 3:UOM
    df_links.columns = ['Parent Part', 'Child Part', 'Qty Per', 'UOM'] + list(df_links.columns[4:])
    
    parent_map = {}
    for _, row in df_links.iterrows():
        p = str(row['Parent Part'])
        if p not in parent_map: parent_map[p] = []
        parent_map[p].append({
            'child': str(row['Child Part']),
            'qty': pd.to_numeric(row['Qty Per'], errors='coerce') or 1.0,
            'uom': str(row['UOM']) if pd.notna(row['UOM']) else "Ea."
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
    
    # Filter out empty rows from SKU list
    sku_options = []
    if id_col in df_sku_list.columns:
        filtered_sku = df_sku_list[df_sku_list[id_col].notna()]
        sku_options = [f"{row[id_col]} | {row[desc_col]}" for _, row in filtered_sku.drop_duplicates(subset=[id_col]).iterrows() if str(row[id_col]).lower() != 'nan']

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
                    'Unit Cost': det.get('Unit Cost', 0.0),
                    'Ext. Cost': det.get('Unit Cost', 0.0) * total_qty
                })
                explode(child_id, depth + 1, total_qty)

        explode(selected_sku)

        if waterfall:
            df_wf = pd.DataFrame(waterfall)
            
            # Metrics
            st.metric("Total Roll-up Cost", f"${df_wf['Ext. Cost'].sum():,.2f}")

            # Display Table
            df_disp = df_wf.copy()
            df_disp['Unit Cost'] = df_disp['Unit Cost'].apply(lambda x: f"${x:,.2f}")
            df_disp['Ext. Cost'] = df_disp['Ext. Cost'].apply(lambda x: f"${x:,.2f}")
            st.dataframe(df_disp, use_container_width=True, hide_index=True)
            
            # --- 6. EXPORT WITH HEADER ROWS ---
            export_cols = ['BOM Level', 'Parent', 'Part No.', 'Description', 'Category', 'Make/Buy', 'Fulfillment', 'Supplier', 'Qty Per', 'UOM', 'Total Req.', 'Unit Cost', 'Ext. Cost']
            
            header_str = f"Assembly Number:, {selected_sku}\n"
            header_str += f"Description:, {selected_desc}\n\n"
            
            table_str = df_wf[export_cols].to_csv(index=False)
            full_csv_str = header_str + table_str
            
            csv_data = full_csv_str.encode('utf-8-sig')
            st.download_button(label="📥 Download Extended BOM with Header", data=csv_data, file_name=f"BOM_Export_{selected_sku}.csv", mime="text/csv")
        else:
            st.warning(f"⚠️ No components found for {selected_sku}. Verify this ID exists in the BOM Links file.")

except Exception as e:
    st.error(f"Critical Application Error: {e}")
