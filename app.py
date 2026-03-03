import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="BOM Tool v4", layout="wide")

# Filenames based on your v4 upload
MASTER_FILE = "Item_Master_v4_Template.csv"
LINKS_FILE = "BOM_Links_v4_Template.csv"

def clean_currency(value):
    if isinstance(value, str):
        return float(re.sub(r'[^\d.]', '', value))
    try:
        return float(value)
    except:
        return 0.0

st.title("Interactive Waterfall BOM & Costing")

# Attempt to load files automatically from GitHub
try:
    df_master = pd.read_csv(MASTER_FILE)
    df_links = pd.read_csv(LINKS_FILE)
    st.success("✅ Successfully loaded v4 data from GitHub.")
except FileNotFoundError:
    st.error(f"Could not find {MASTER_FILE} or {LINKS_FILE} in GitHub.")
    st.info("Please upload them manually below:")
    master_upload = st.file_uploader("Upload Item Master", type="csv")
    links_upload = st.file_uploader("Upload BOM Links", type="csv")
    if master_upload and links_upload:
        df_master = pd.read_csv(master_upload)
        df_links = pd.read_csv(links_upload)
    else:
        st.stop()

# --- DATA CLEANING ---
df_master['Part No.'] = df_master['Part No.'].astype(str).str.strip()
df_master['Unit Cost'] = df_master['Unit Cost'].apply(clean_currency)
df_links['Parent Part'] = df_links['Parent Part'].astype(str).str.strip()
df_links['Child Part'] = df_links['Child Part'].astype(str).str.strip()
df_links['Qty Per'] = pd.to_numeric(df_links['Qty Per'], errors='coerce').fillna(1.0)

# Create lookup maps
item_details = df_master.set_index('Part No.').to_dict('index')
parent_map = {}
for _, row in df_links.iterrows():
    p, c, q = row['Parent Part'], row['Child Part'], row['Qty Per']
    if p not in parent_map: parent_map[p] = []
    parent_map[p].append((c, q))

# Identify L0 SKUs
all_parents = set(df_links['Parent Part'].unique())
all_children = set(df_links['Child Part'].unique())
l0_skus = sorted(list(all_parents - all_children))

selected_l0 = st.selectbox("Select Saleable SKU (L0)", ["-- Select --"] + l0_skus)

if selected_l0 != "-- Select --":
    waterfall = []
    def explode(parent, depth=0, mult=1):
        for child, qty in parent_map.get(parent, []):
            total_qty = mult * qty
            det = item_details.get(child, {})
            u_cost = det.get('Unit Cost', 0.0)
            waterfall.append({
                'Level': f"{'..' * depth}↳ {child}",
                'Description': det.get('Part Description', 'N/A'),
                'Qty Per': qty,
                'Total Qty': total_qty,
                'Unit Cost': f"${u_cost:,.2f}",
                'Ext Cost': u_cost * total_qty
            })
            explode(child, depth + 1, total_qty)

    explode(selected_l0)
    df_wf = pd.DataFrame(waterfall)
    st.metric("Total SKU Cost", f"${df_wf['Ext Cost'].sum():,.2f}")
    st.dataframe(df_wf, use_container_width=True)
