import streamlit as st
import pandas as pd
import re
import os

st.set_page_config(page_title="BOM Tool v8.5", layout="wide")

# --- 1. THE "CLEANING" ENGINE ---
def load_and_sanitize(pattern):
    # Locate the file even with double dots or extra extensions
    fname = next((f for f in os.listdir('.') if pattern.lower() in f.lower() and f.endswith('.csv')), None)
    if not fname:
        return None
    
    # Read with utf-8-sig to clear Excel's hidden BOM markers
    df = pd.read_csv(fname, encoding='utf-8-sig', on_bad_lines='skip')
    
    # TRAP 1: Strip invisible spaces from column headers
    df.columns = [str(c).strip() for c in df.columns]
    
    # TRAP 2: Delete "Ghost Columns" caused by trailing commas in CSV
    df = df.loc[:, ~df.columns.str.contains('^Unnamed|^$')]
    
    # TRAP 3: Strip invisible spaces from all text cells
    df = df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)
    return df

def to_float(val):
    """Converts strings like '$0.82' or '0' into 0.0 or a number."""
    if pd.isna(val) or str(val).strip() in ["", "-", "$-", "$ -"]:
        return 0.0
    # Keep only numbers and decimal points
    clean_str = re.sub(r'[^\d.]', '', str(val))
    try:
        return float(clean_str) if clean_str else 0.0
    except:
        return 0.0

# --- 2. LOAD DATA ---
st.title("🛠️ BOM Professional v8.5")

try:
    df_m = load_and_sanitize("Item_Master")
    df_l = load_and_sanitize("BOM_Links")
    df_s = load_and_sanitize("L0&L1 Skus")

    if any(x is None for x in [df_m, df_l, df_s]):
        st.error("🚨 Missing Files! Ensure CSVs are uploaded to GitHub with correct names.")
        st.stop()

    # --- 3. BUILD LOOKUP TABLES ---
    # Find the Unit Cost column regardless of hidden characters
    cost_col = next((c for c in df_m.columns if "Cost" in c), "Unit Cost")
    df_m['Clean_Price'] = df_m[cost_col].apply(to_float)
    
    master_dict = df_m.set_index('Part No.').to_dict('index')

    # Build the BOM Tree (Parent -> List of Children)
    bom_tree = {}
    for _, row in df_l.iterrows():
        parent = str(row.iloc[0]) # Column 1: Parent Part
        if parent not in bom_tree: bom_tree[parent] = []
        bom_tree[parent].append({
            'child_id': str(row.iloc[1]), # Column 2: Child Part
            'qty_per': pd.to_numeric(row.iloc[2], errors='coerce') or 1.0, # Column 3
            'uom': str(row.iloc[3]) if len(row) > 3 else "Ea." # Column 4
        })

    # --- 4. NAVIGATION & SELECTION ---
    categories = {
        "Saleable SKUs": ("Saleable Sku", "Saleable Sku Description"),
        "Base Assemblies": ("Base Assy Kit", "Base Assy Kit Description"),
        "Countertops": ("Countertop Assy Kit", "Countertop Assy Kit Description"),
        "Cladding": ("Cladding Assy Kit", "Cladding Assy Kit Description")
    }
    mode = st.sidebar.selectbox("Category View", list(categories.keys()))
    id_key, desc_key = categories[mode]

    sku_options = []
    if id_key in df_s.columns:
        df_valid = df_s[df_s[id_key].notna() & (df_s[id_key] != "")]
        for _, row in df_valid.drop_duplicates(subset=[id_key]).iterrows():
            sku_options.append(f"{row[id_key]} | {row.get(desc_key, 'N/A')}")

    target_sku = st.selectbox(f"Select {mode}", ["-- Select --"] + sorted(sku_options))

    if target_sku != "-- Select --":
        sel_id = target_sku.split(" | ")[0].strip()
        sel_desc = target_sku.split(" | ")[1].strip()

        # --- 5. EXPLOSION ENGINE ---
        exploded_data = []
        
        def explode(parent_id, depth=1, current_mult=1):
            if depth > 12: return # Safety break
            
            components = bom_tree.get(parent_id, [])
            for comp in components:
                cid = comp['child_id']
                total_req = current_mult * comp['qty_per']
                meta = master_dict.get(cid, {})
                
                exploded_data.append({
                    'Level': depth,
                    'Parent': parent_id,
                    'Part No.': cid,
                    'Description': meta.get('Part Description', 'N/A'),
                    'Category': meta.get('Category', 'N/A'),
                    'Qty Per': comp['qty_per'],
                    'Total Req': total_req,
                    'UOM': comp['uom'],
                    'Unit Cost': meta.get('Clean_Price', 0.0),
                    'Ext. Cost': meta.get('Clean_Price', 0.0) * total_req
                })
                # Check if this child is also a parent
                explode(cid, depth + 1, total_req)

        explode(sel_id)

        # --- 6. DISPLAY RESULTS ---
        if exploded_data:
            res_df = pd.DataFrame(exploded_data)
            
            st.metric("Total Roll-up Cost", f"${res_df['Ext. Cost'].sum():,.2f}")

            disp_df = res_df.copy()
            disp_df['Unit Cost'] = disp_df['Unit Cost'].map("${:,.2f}".format)
            disp_df['Ext. Cost'] = disp_df['Ext. Cost'].map("${:,.2f}".format)
            st.dataframe(disp_df, use_container_width=True, hide_index=True)

            csv_buffer = f"BOM REPORT\nTarget: {sel_id}\n\n" + res_df.to_csv(index=False)
            st.download_button("📥 Download This BOM", csv_buffer.encode('utf-8-sig'), f"BOM_{sel_id}.csv")
        else:
            st.warning(f"No components found for '{sel_id}' in the BOM Links file.")

except Exception as e:
    st.error(f"Critical Error: {e}")
