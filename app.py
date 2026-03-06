import streamlit as st
import pandas as pd
import re
import os

st.set_page_config(page_title="BOM Tool v8.2", layout="wide")

# --- 1. SMART FILE LOCATOR ---
def load_data(pattern):
    # Searches for the file even if it has double dots or extra extensions
    fname = next((f for f in os.listdir('.') if pattern.lower() in f.lower() and f.endswith('.csv')), None)
    if not fname:
        return None
    
    # Read with utf-8-sig to strip Excel's hidden BOM characters
    df = pd.read_csv(fname, encoding='utf-8-sig', on_bad_lines='skip')
    
    # CLEAN HEADERS: Remove ghost columns and trim spaces from titles
    df = df.loc[:, ~df.columns.str.contains('^Unnamed|^$')]
    df.columns = [str(c).strip() for c in df.columns]
    
    # CLEAN DATA: Trim spaces from every cell in the spreadsheet
    df = df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)
    return df

def clean_val(val):
    """Converts '$1.11' or ' $- ' into a clean float 0.00"""
    if pd.isna(val) or str(val).strip() in ["", "-", "$-", "$ -"]:
        return 0.0
    text = re.sub(r'[^\d.]', '', str(val))
    try:
        return float(text) if text else 0.0
    except:
        return 0.0

# --- 2. INITIALIZE ---
st.title("🚀 BOM Professional v8.2")

df_m = load_data("Item_Master")
df_l = load_data("BOM_Links")
df_s = load_data("L0&L1 Skus")

if any(x is None for x in [df_m, df_l, df_s]):
    st.error("🚨 Missing Files! Check your GitHub repository for the CSV files.")
    st.stop()

# --- 3. DATA ARCHITECTURE ---
# Find the cost column (handles 'Unit Cost' with or without spaces)
cost_col = next((c for c in df_m.columns if "Cost" in c), df_m.columns[-1])
df_m['Price_Clean'] = df_m[cost_col].apply(clean_val)
master_map = df_m.set_index('Part No.').to_dict('index')

# Build the hierarchy map
tree = {}
for _, row in df_l.iterrows():
    parent = str(row.iloc[0]) # Parent Part
    if parent not in tree: tree[parent] = []
    tree[parent].append({
        'id': str(row.iloc[1]), # Child Part
        'qty': pd.to_numeric(row.iloc[2], errors='coerce') or 1.0,
        'uom': str(row.iloc[3]) if len(row) > 3 else "Ea."
    })

# --- 4. NAVIGATION ---
sections = {
    "Saleable SKUs": ("Saleable Sku", "Saleable Sku Description"),
    "Base Assemblies": ("Base Assy Kit", "Base Assy Kit Description"),
    "Countertops": ("Countertop Assy Kit", "Countertop Assy Kit Description"),
    "Cladding": ("Cladding Assy Kit", "Cladding Assy Kit Description")
}
view = st.sidebar.selectbox("Category", list(sections.keys()))
id_field, desc_field = sections[view]

# Populate list
sku_list = []
if id_field in df_s.columns:
    subset = df_s[df_s[id_field].notna() & (df_s[id_field] != "")]
    for _, r in subset.drop_duplicates(subset=[id_field]).iterrows():
        sku_list.append(f"{r[id_field]} | {r.get(desc_field, 'N/A')}")

target = st.selectbox(f"Select {view}", ["-- Select --"] + sorted(sku_list))

if target != "-- Select --":
    sel_id = target.split(" | ")[0].strip()
    sel_desc = target.split(" | ")[1].strip()

    # --- 5. RECURSIVE ENGINE ---
    results = []
    def dig(pid, level=1, multiplier=1):
        if level > 10: return # Stop infinite loops
        for item in tree.get(pid, []):
            cid = item['id']
            total_qty = multiplier * item['qty']
            meta = master_map.get(cid, {})
            
            results.append({
                'Level': level,
                'Parent': pid,
                'Part No.': cid,
                'Description': meta.get('Part Description', 'N/A'),
                'Qty': item['qty'],
                'Total Req': total_qty,
                'UOM': item['uom'],
                'Unit Cost': meta.get('Price_Clean', 0.0),
                'Ext. Cost': meta.get('Price_Clean', 0.0) * total_qty
            })
            dig(cid, level + 1, total_qty)

    dig(sel_id)

    if results:
        final_df = pd.DataFrame(results)
        
        # Dashboard
        c1, c2 = st.columns(2)
        c1.metric("Total Cost", f"${final_df['Ext. Cost'].sum():,.2f}")
        c2.metric("Components", len(final_df))
        
        # Table
        disp = final_df.copy()
        disp['Unit Cost'] = disp['Unit Cost'].map("${:,.2f}".format)
        disp['Ext. Cost'] = disp['Ext. Cost'].map("${:,.2f}".format)
        st.dataframe(disp, use_container_width=True, hide_index=True)
        
        # Download
        csv = f"BOM REPORT: {sel_id}\n\n" + final_df.to_csv(index=False)
        st.download_button("📥 Download CSV", csv.encode('utf-8-sig'), f"BOM_{sel_id}.csv")
    else:
        st.warning(f"No components found for {sel_id}. Ensure this ID is in the 'Parent Part' column of your BOM Links file.")
