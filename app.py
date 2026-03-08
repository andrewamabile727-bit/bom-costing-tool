import streamlit as st
import pandas as pd
import re
import os

st.set_page_config(page_title="BOM Pro v9.1", layout="wide")

# --- 1. PERFORMANCE CACHE (Keeps the app fast) ---
@st.cache_data(ttl=3600)
def load_and_prep_data():
    def find_file(p):
        return next((f for f in os.listdir('.') if p.lower() in f.lower() and f.endswith('.csv')), None)
    
    f_m = find_file("Item_Master")
    f_l = find_file("BOM_Links")
    f_s = find_file("L0&L1 Skus")
    
    if not all([f_m, f_l, f_s]):
        return None, None, None

    # Load & Strip spaces
    df_m = pd.read_csv(f_m, encoding='utf-8-sig').apply(lambda x: x.str.strip() if x.dtype == "object" else x)
    df_l = pd.read_csv(f_l, encoding='utf-8-sig').apply(lambda x: x.str.strip() if x.dtype == "object" else x)
    df_s = pd.read_csv(f_s, encoding='utf-8-sig').apply(lambda x: x.str.strip() if x.dtype == "object" else x)

    # Clean Headers
    for df in [df_m, df_l, df_s]:
        df.columns = [str(c).strip() for c in df.columns]
        df.drop(columns=[c for c in df.columns if 'Unnamed' in c or c == ''], inplace=True, errors='ignore')

    # Force Price to Number
    cost_col = next((c for c in df_m.columns if "Cost" in c), "Unit Cost")
    df_m['Math_Cost'] = df_m[cost_col].replace(r'[^\d.]', '', regex=True).replace('', '0').astype(float)
    
    return df_m, df_l, df_s

# --- 2. DATA PROCESSING ---
df_m, df_l, df_s = load_and_prep_data()

if df_m is None:
    st.error("🚨 Missing core CSV files in your GitHub repository.")
    st.stop()

# Maps for fast lookup
master_map = df_m.set_index('Part No.').to_dict('index')
bom_tree = {}
for _, row in df_l.iterrows():
    p = str(row.iloc[0]) # Parent
    if p not in bom_tree: bom_tree[p] = []
    bom_tree[p].append({
        'id': str(row.iloc[1]), 
        'qty': pd.to_numeric(row.iloc[2], errors='coerce') or 1.0,
        'uom': str(row.iloc[3]) if len(row) > 3 else "Ea."
    })

# --- 3. NAVIGATION LOGIC ---
st.sidebar.header("Configuration")
nav_type = st.sidebar.radio("View Depth", ["Top Level (SKU List)", "Sub-Assemblies (Deep Dive)"])

# Define Categories and check if they exist in the file
cols = df_s.columns.tolist()
cat_map = {
    "Saleable SKUs": ("Saleable Sku", "Saleable Sku Description"),
    "Base Assemblies": ("Base Assy Kit", "Base Assy Kit Description"),
    "Countertops": ("Countertop Assy Kit", "Countertop Assy Kit Description"),
    "Cladding": ("Cladding Assy Kit", "Cladding Assy Kit Description"),
    "Finish Kits": ("Finish Kit", "Finish Kit Description")
}

if nav_type == "Top Level (SKU List)":
    # Filter only available categories
    available_cats = [k for k, v in cat_map.items() if v[0] in cols]
    mode = st.selectbox("Category", available_cats)
    id_col, desc_col = cat_map[mode]
    
    # Generate Dropdown with Name | Number
    options = []
    valid_rows = df_s[df_s[id_col].notna() & (df_s[id_col] != "")]
    for _, r in valid_rows.drop_duplicates(subset=[id_col]).iterrows():
        options.append(f"{r[id_col]} | {r.get(desc_col, 'N/A')}")
    selection = st.selectbox(f"Select {mode}", ["-- Select --"] + sorted(options))

else:
    # 1) FIXED: Sub-Assemblies now show Name and Number
    sub_options = []
    for p_id in sorted(bom_tree.keys()):
        p_desc = master_map.get(p_id, {}).get('Part Description', 'Description Not in Master')
        sub_options.append(f"{p_id} | {p_desc}")
    selection = st.selectbox("Select Sub-Assembly", ["-- Select --"] + sub_options)

# --- 4. CALCULATION & OUTPUT ---
if selection != "-- Select --":
    sel_id = selection.split(" | ")[0].strip()
    sel_name = selection.split(" | ")[1].strip()

    final_bom = []
    def explode(pid, depth=1, mult=1):
        if depth > 12: return
        for child in bom_tree.get(pid, []):
            cid = child['id']
            t_qty = mult * child['qty']
            meta = master_map.get(cid, {})
            
            final_bom.append({
                'Level': depth,
                'Part No.': cid,
                'Description': meta.get('Part Description', 'N/A'),
                'Total Qty': t_qty,
                'UOM': child['uom'],
                'Unit Cost': meta.get('Math_Cost', 0.0),
                'Ext. Cost': meta.get('Math_Cost', 0.0) * t_qty
            })
            explode(cid, depth + 1, t_qty)

    explode(sel_id)

    if final_bom:
        res_df = pd.DataFrame(final_bom)
        st.metric("Total Roll-up Cost", f"${res_df['Ext. Cost'].sum():,.2f}")
        
        # Display Table
        disp = res_df.copy()
        disp['Unit Cost'] = disp['Unit Cost'].map("${:,.2f}".format)
        disp['Ext. Cost'] = disp['Ext. Cost'].map("${:,.2f}".format)
        st.dataframe(disp, use_container_width=True, hide_index=True)
        
        # 3) CSV HEADER: Name then Number
        csv_header = f"ASSEMBLY NAME: {sel_name}\nASSEMBLY NUMBER: {sel_id}\n\n"
        csv_body = res_df.to_csv(index=False)
        st.download_button("📥 Download CSV", (csv_header + csv_body).encode('utf-8-sig'), f"BOM_{sel_id}.csv")
    else:
        st.warning(f"No components found for {sel_id}. Ensure it is listed as a 'Parent' in BOM Links.")
