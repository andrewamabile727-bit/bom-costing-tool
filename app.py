import streamlit as st
import pandas as pd
import re
import os

st.set_page_config(page_title="BOM Tool v6.5", layout="wide")

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
    """Removes hidden spaces in headers and cell values"""
    df.columns = [" ".join(str(c).split()) for c in df.columns]
    df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)
    return df

# --- 2. FILE CHECK ---
missing_files = []
for f in [SKU_FILE, MASTER_FILE, LINKS_FILE]:
    if not os.path.exists(f):
        missing_files.append(f)

if missing_files:
    st.error(f"🚨 Missing Files: {', '.join(missing_files)}")
    st.stop()

try:
    # --- 3. DATA LOADING ---
    df_master = super_clean_df(pd.read_csv(MASTER_FILE, encoding='utf-8-sig'))
    df_links = super_clean_df(pd.read_csv(LINKS_FILE, encoding='utf-8-sig'))
    df_sku_list = super_clean_df(pd.read_csv(SKU_FILE, encoding='utf-8-sig'))

    # Clean Costs
    df_master['Unit Cost'] = df_master['Unit Cost'].apply(clean_currency)
    item_details = df_master.set_index('Part No.').to_dict('index')

    # Assign names to columns based on position
    df_links.columns = ['Parent Part', 'Child Part', 'Qty Per', 'UOM'] + list(df_links.columns[4:])
    df_links['Qty Per'] = pd.to_numeric(df_links['Qty Per'], errors='coerce').fillna(1.0)
    df_links['UOM'] = df_links['UOM'].fillna('Ea.')

    # Build Parent-Child Map
    parent_map = {}
    for _, row in df_links.iterrows():
        p, c, q, uom = str(row['Parent Part']), str(row['Child Part']), row['Qty Per'], str(row['UOM'])
        if p not in parent_map: parent_map[p] = []
        parent_map[p].append((c, q, uom))

    # --- 4. UI SIDEBAR ---
    st.sidebar.header("Navigation")
    ui_option = st.sidebar.radio(
        "Choose Assembly Category:",
        ["Option 1: Saleable SKUs", "Option 2: Base Assemblies", 
         "Option 3: Countertop Assemblies", "Option 4: Cladding Assemblies", "Option 5: Finish Kits"]
    )

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
        unique_rows = df_sku_list.drop_duplicates(subset=[id_col])
        for _, row in unique_rows.iterrows():
            p_id, p_desc = str(row[id_col]), str(row[desc_col])
            if p_id and p_id.lower() != "nan":
                sku_options.append(f"{p_id} | {p_desc}")

    selected_label = st.selectbox(f"Select {ui_option}", ["-- Select --"] + sorted(sku_options))

    if selected_label != "-- Select --":
        selected_sku = selected_label.split(" | ")[0].strip()
        
        st.markdown("---")
        st.header(f"BOM Breakdown: {selected_sku}")
        
        # --- 5. BOM EXPLOSION ---
        waterfall = []
        def explode(parent, depth=0, mult=1):
            for child, qty, uom in parent_map.get(parent, []):
                total_qty = mult * qty
                det = item_details.get(child, {})
                u_cost = det.get('Unit Cost', 0.0)
                
                # --- DOT INDENTATION LOGIC ---
                # Level 1 = .
                # Level 2 = ..
                # Level 3 = ...
                dot_level = "." * (depth + 1)
                
                waterfall.append({
                    'Level': dot_level,            # The visual dots
                    'Part No.': child,             # Clean for searching/exporting
                    'Description': det.get('Part Description', 'N/A'),
                    'Category': det.get('Category', 'Uncategorized'),
                    'Qty Per': qty,
                    'UOM': uom,
                    'Total Req.': total_qty,
                    'Unit Cost': u_cost, 
                    'Ext. Cost': u_cost * total_qty
                })
                explode(child, depth + 1, total_qty)

        explode(selected_sku)

        if waterfall:
            df_wf = pd.DataFrame(waterfall)
            total_val = df_wf['Ext. Cost'].sum()
            
            # --- 6. METRICS ---
            m1, m2, m3 = st.columns(3)
            m1.metric("Total Roll-up Cost", f"${total_val:,.2f}")
            m2.metric("Total Parts Count", int(df_wf['Total Req.'].sum()))
            m3.metric("Unique Line Items", len(df_wf))

            # --- 7. DATA TABLE ---
            st.write("### 📑 Detailed Component List")
            df_display = df_wf.copy()
            df_display['Unit Cost'] = df_display['Unit Cost'].apply(lambda x: f"${x:,.2f}")
            df_display['Ext. Cost'] = df_display['Ext. Cost'].apply(lambda x: f"${x:,.2f}")
            
            # Format the display so Level and Part No. are side-by-side
            st.dataframe(df_display, use_container_width=True, hide_index=True)
            
            # --- 8. CLEAN EXPORT ---
            # We keep the dots in the CSV as it is helpful for hierarchy, 
            # but Part No. remains a clean ID for Excel VLOOKUPs.
            csv_data = df_wf.to_csv(index=False).encode('utf-8-sig')
            
            st.download_button(
                label=f"📥 Download Dot-Indented BOM for {selected_sku}", 
                data=csv_data, 
                file_name=f"BOM_{selected_sku}.csv", 
                mime="text/csv"
            )
        else:
            st.warning("⚠️ No components found for this selection.")

except Exception as e:
    st.error(f"Critical Error: {e}")
