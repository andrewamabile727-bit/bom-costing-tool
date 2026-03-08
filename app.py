import streamlit as st
import pandas as pd
import re
import os

st.set_page_config(page_title="BOM Pro v9.0", layout="wide")

# --- 1. CACHED DATA ENGINE (Makes it 10x Faster) ---
@st.cache_data(ttl=3600)
def load_all_data():
    def get_file(pattern):
        return next((f for f in os.listdir('.') if pattern.lower() in f.lower() and f.endswith('.csv')), None)
    
    files = {
        "master": get_file("Item_Master"),
        "links": get_file("BOM_Links"),
        "skus": get_file("L0&L1 Skus")
    }
    
    if None in files.values():
        return None, None, None

    # Load & Clean
    df_m = pd.read_csv(files["master"], encoding='utf-8-sig', on_bad_lines='skip')
    df_l = pd.read_csv(files["links"], encoding='utf-8-sig', on_bad_lines='skip')
    df_s = pd.read_csv(files["skus"], encoding='utf-8-sig', on_bad_lines='skip')

    for df in [df_m, df_l, df_s]:
        df.columns = [str(c).strip() for c in df.columns]
        # Remove ghost columns
        df.drop(columns=[c for c in df.columns if 'Unnamed' in c or c == ''], inplace=True)
        # Strip all text
        for col in df.select_dtypes(include=['object']):
            df[col] = df[col].str.strip()

    # Pre-clean Costs
    def to_num(val):
        if pd.isna(val) or str(val).strip() in ["", "-", "$-"]: return 0.0
        n = re.sub(r'[^\d.]', '', str(val))
        return float(n) if n else 0.0

    cost_col = next((c for c in df_m.columns if "Cost" in c), "Unit Cost")
    df_m['Math_Cost'] = df_m[cost_col].apply(to_num)
    
    return df_m, df_l, df_s

# --- 2. INITIALIZATION ---
st.title("🚀 BOM Professional v9.0")
df_m, df_l, df_s = load_all_data()

if df_m is None:
    st.error("🚨 Missing core files in GitHub. Check filenames.")
    st.stop()

# Build dictionaries
master_map = df_m.set_index('Part No.').to_dict('index')
bom_tree = {}
for _, row in df_l.iterrows():
    p = str(row.iloc[0])
    if p not in bom_tree: bom_tree[p] = []
    bom_tree[p].append({
        'c': str(row.iloc[1]), 
        'q': pd.to_numeric(row.iloc[2], errors='coerce') or 1.0,
        'u': str(row.iloc[3]) if len(row) > 3 else "Ea."
    })

# --- 3. NAVIGATION (Fixed Categories) ---
st.sidebar.header("Navigation")
# Dynamically check for columns in your L0&L1 file
available_cols = df_s.columns.tolist()
cat_config = {
    "Saleable SKUs": ("Saleable Sku", "Saleable Sku Description"),
    "Base Assemblies": ("Base Assy Kit", "Base Assy Kit Description"),
    "Countertops": ("Countertop Assy Kit", "Countertop Assy Kit Description"),
    "Cladding": ("Cladding Assy Kit", "Cladding Assy Kit Description"),
    "Finish Kits": ("Finish Kit", "Finish Kit Description") # Added this
}

# Create a "Sub-Assemblies" mode for parts not in the SKU list
nav_mode = st.sidebar.radio("Select Level", ["Top Level (SKU List)", "Sub-Assemblies (All Parents)"])

if nav_mode == "Top Level (SKU List)":
    view = st.selectbox("Category", [k for k in cat_config.keys() if cat_config[k][0] in available_cols])
    id_f, desc_f = cat_config[view]
    options = []
    subset = df_s[df_s[id_f].notna() & (df_s[id_f] != "")]
    for _, r in subset.drop_duplicates(subset=[id_f]).iterrows():
        options.append(f"{r[id_f]} | {r.get(desc_f, 'N/A')}")
    choice = st.selectbox(f"Select {view}", ["-- Select --"] + sorted(options))
else:
    # Allows viewing BOMs for items that aren't "Saleable" (Sub-assemblies)
    all_parents = sorted(list(bom_tree.keys()))
    choice = st.selectbox("Select Any Sub-Assembly ID", ["-- Select --"] + all_parents)

# --- 4. ENGINE & OUTPUT ---
if choice != "-- Select --":
    sel_id = choice.split(" | ")[0].strip()
    # Find description from Master if not in SKU list
    sel_desc = choice.split(" | ")[1].strip() if " | " in choice else master_map.get(sel_id, {}).get('Part Description', 'Unknown Sub-Assembly')

    results = []
    def explode(pid, depth=1, mult=1):
        if depth > 10: return
        for item in bom_tree.get(pid, []):
            cid = item['c']
            total = mult * item['q']
            meta = master_lookup = master_map.get(cid, {})
            results.append({
                'Level': depth, 'Part No.': cid, 
                'Description': meta.get('Part Description', 'N/A'),
                'Qty': item['q'], 'Total Req': total, 'UOM': item['u'],
                'Unit Cost': meta.get('Math_Cost', 0.0),
                'Ext. Cost': meta.get('Math_Cost', 0.0) * total
            })
            explode(cid, depth + 1, total)

    explode(sel_id)

    if results:
        df_res = pd.DataFrame(results)
        st.metric("Total Roll-up Cost", f"${df_res['Ext. Cost'].sum():,.2f}")
        
        # Display Table
        disp = df_res.copy()
        disp['Unit Cost'] = disp['Unit Cost'].map("${:,.2f}".format)
        disp['Ext. Cost'] = disp['Ext. Cost'].map("${:,.2f}".format)
        st.dataframe(disp, use_container_width=True, hide_index=True)

        # 3) FIXED CSV HEADER (Name then Number)
        csv_header = f"ASSEMBLY NAME: {sel_desc}\nASSEMBLY NUMBER: {sel_id}\n\n"
        csv_body = df_res.to_csv(index=False)
        st.download_button("📥 Download CSV", (csv_header + csv_body).encode('utf-8-sig'), f"BOM_{sel_id}.csv")
    else:
        st.warning(f"No components found for {sel_id}.")
