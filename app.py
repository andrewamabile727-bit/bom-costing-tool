import streamlit as st
import pandas as pd
import re
import os

st.set_page_config(page_title="BOM Tool v8.1", layout="wide")

# --- 1. ROBUST FILE LOADING ---
def get_clean_df(file_pattern):
    # Find file even with weird naming like "Skus..xlsx"
    target = next((f for f in os.listdir('.') if file_pattern.lower() in f.lower() and f.endswith('.csv')), None)
    if not target: return None
    
    # Load with 'utf-8-sig' to handle Excel's hidden formatting
    df = pd.read_csv(target, encoding='utf-8-sig', on_bad_lines='skip')
    
    # HEAL HEADERS: Remove spaces, newlines, and "Unnamed" ghost columns
    df = df.loc[:, ~df.columns.str.contains('^Unnamed|^$')]
    df.columns = [" ".join(str(c).split()).strip() for c in df.columns]
    
    # HEAL DATA: Strip spaces from every cell in the file
    df = df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)
    return df

def clean_currency(val):
    if pd.isna(val) or str(val).strip() in ["", "-", "$-", "$ -"]: return 0.0
    num_str = re.sub(r'[^\d.]', '', str(val))
    try:
        return float(num_str) if num_str else 0.0
    except:
        return 0.0

# --- 2. DATA INITIALIZATION ---
st.title("🛠️ BOM Professional v8.1")

df_m = get_clean_df("Item_Master")
df_l = get_clean_df("BOM_Links")
df_s = get_clean_df("L0&L1 Skus")

if df_m is None or df_l is None or df_s is None:
    st.error("🚨 Missing Files! Ensure 'Item_Master', 'BOM_Links', and 'L0&L1 Skus' CSVs are on GitHub.")
    st.stop()

# Build dictionaries for fast lookup
# Find Cost column regardless of spaces
cost_col = next((c for c in df_m.columns if "Cost" in c), "Unit Cost")
df_m['Price_Internal'] = df_m[cost_col].apply(clean_currency)
master_lookup = df_m.set_index('Part No.').to_dict('index')

# Build the Links Tree (Parent -> Children)
links_tree = {}
for _, row in df_l.iterrows():
    p = str(row.iloc[0]) # Column 1: Parent
    if p not in links_tree: links_tree[p] = []
    links_tree[p].append({
        'c': str(row.iloc[1]), # Column 2: Child
        'q': pd.to_numeric(row.iloc[2], errors='coerce') or 1.0, # Column 3: Qty
        'u': str(row.iloc[3]) if len(row) > 3 else "Ea." # Column 4: UOM
    })

# --- 3. UI SIDEBAR ---
cat_map = {
    "Saleable SKUs": ("Saleable Sku", "Saleable Sku Description"),
    "Base Assemblies": ("Base Assy Kit", "Base Assy Kit Description"),
    "Countertop Assemblies": ("Countertop Assy Kit", "Countertop Assy Kit Description"),
    "Cladding Kits": ("Cladding Assy Kit", "Cladding Assy Kit Description")
}
mode = st.sidebar.selectbox("View Category", list(cat_map.keys()))
id_col, desc_col = cat_map[mode]

# Dropdown generation
drop_options = []
if id_col in df_s.columns:
    valid_skus = df_s[df_s[id_col].notna() & (df_s[id_col] != "")]
    for _, row in valid_skus.drop_duplicates(subset=[id_col]).iterrows():
        drop_options.append(f"{row[id_col]} | {row.get(desc_col, 'N/A')}")

selection = st.selectbox(f"Select {mode}", ["-- Choose --"] + sorted(drop_options))

if selection != "-- Choose --":
    sel_id = selection.split(" | ")[0].strip()
    sel_desc = selection.split(" | ")[1].strip()

    # --- 4. EXPLOSION ENGINE ---
    final_bom = []
    def explode(parent_id, depth=1, multiplier=1):
        if depth > 10: return # Safety cap
        for component in links_tree.get(parent_id, []):
            cid = component['c']
            qty = multiplier * component['q']
            info = master_lookup.get(cid, {})
            
            final_bom.append({
                'Level': depth,
                'Parent': parent_id,
                'Part No.': cid,
                'Description': info.get('Part Description', 'N/A'),
                'Total Qty': qty,
                'UOM': component['u'],
                'Unit Cost': info.get('Price_Internal', 0.0),
                'Ext. Cost': info.get('Price_Internal', 0.0) * qty,
                'Make/Buy': info.get('Make/Buy', 'N/A')
            })
            # Recursive call
            explode(cid, depth + 1, qty)

    explode(sel_id)

    if final_bom:
        res_df = pd.DataFrame(final_bom)
        st.metric("Total Assembly Cost", f"${res_df['Ext. Cost'].sum():,.2f}")
        
        # Format for display
        disp_df = res_df.copy()
        disp_df['Unit Cost'] = disp_df['Unit Cost'].map("${:,.2f}".format)
        disp_df['Ext. Cost'] = disp_df['Ext. Cost'].map("${:,.2f}".format)
        st.dataframe(disp_df, use_container_width=True, hide_index=True)
        
        # Export
        csv_out = f"Report for: {sel_id}\n\n" + res_df.to_csv(index=False)
        st.download_button("📥 Download BOM", csv_out.encode('utf-8-sig'), f"BOM_{sel_id}.csv")
    else:
        st.warning(f"No components found for '{sel_id}'. Check if this ID is listed in the 'Parent Part' column of your BOM Links file.")
