import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="BOM Costing Tool v4", layout="wide")

# EXACT filenames from your GitHub
MASTER_FILE = "Item_Master_v4_Template.csv"
LINKS_FILE = "BOM_Links_v4_Template.csv"

def clean_currency(value):
    """Handles '$', spaces, and commas in currency strings."""
    if pd.isna(value) or value == "": return 0.0
    if isinstance(value, str):
        # Remove everything except numbers and decimals
        cleaned = re.sub(r'[^\d.]', '', value)
        return float(cleaned) if cleaned else 0.0
    return float(value)

st.title("Interactive Waterfall BOM & Costing")
st.info("System Status: Reading Version 4.0 Data Sheets")

# --- LOAD DATA ---
try:
    # Use utf-8-sig to handle hidden Excel formatting characters
    df_master = pd.read_csv(MASTER_FILE, encoding='utf-8-sig')
    df_links = pd.read_csv(LINKS_FILE, encoding='utf-8-sig')
    
    # 1. Clean Master Data
    df_master['Part No.'] = df_master['Part No.'].astype(str).str.strip()
    df_master['Unit Cost'] = df_master['Unit Cost'].apply(clean_currency)
    item_details = df_master.set_index('Part No.').to_dict('index')

    # 2. Clean Links Data (Keeping only first 3 columns to ignore the 'Unnamed' ones)
    df_links = df_links.iloc[:, :3] 
    df_links.columns = ['Parent Part', 'Child Part', 'Qty Per']
    df_links['Parent Part'] = df_links['Parent Part'].astype(str).str.strip()
    df_links['Child Part'] = df_links['Child Part'].astype(str).str.strip()
    df_links['Qty Per'] = pd.to_numeric(df_links['Qty Per'], errors='coerce').fillna(1.0)

    # 3. Build Parent Map
    parent_map = {}
    for _, row in df_links.iterrows():
        p, c, q = row['Parent Part'], row['Child Part'], row['Qty Per']
        if p not in parent_map: parent_map[p] = []
        parent_map[p].append((c, q))

    # 4. Identify Top-Level SKUs
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
                ext_cost = u_cost * total_qty
                
                waterfall.append({
                    'Level': f"{'  ' * depth}↳ {child}",
                    'Description': det.get('Part Description', 'N/A'),
                    'Category': det.get('Category', 'N/A'),
                    'Qty Per': qty,
                    'Total Req.': total_qty,
                    'Unit Cost': f"${u_cost:,.2f}",
                    'Ext. Cost': ext_cost
                })
                explode(child, depth + 1, total_qty)

        explode(selected_l0)
        df_wf = pd.DataFrame(waterfall)
        
        # Display Totals
        st.metric("Total Roll-up Cost", f"${df_wf['Ext. Cost'].sum():,.2f}")
        
        # Format for Display
        df_display = df_wf.copy()
        df_display['Ext. Cost'] = df_display['Ext. Cost'].apply(lambda x: f"${x:,.2f}")
        st.dataframe(df_display, use_container_width=True, hide_index=True)

except Exception as e:
    st.error(f"Error Loading Data: {e}")
    st.warning("Ensure filenames on GitHub match EXACTLY: Item_Master_v4_Template.csv and BOM_Links_v4_Template.csv")
