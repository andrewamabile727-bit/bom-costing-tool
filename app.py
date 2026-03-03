import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="BOM Tool v4.1", layout="wide")

MASTER_FILE = "Item_Master_v4_Template.csv"
LINKS_FILE = "BOM_Links_v4_Template.csv"

def clean_currency(value):
    if pd.isna(value) or value == "": return 0.0
    if isinstance(value, str):
        cleaned = re.sub(r'[^\d.]', '', value)
        return float(cleaned) if cleaned else 0.0
    return float(value)

st.title("📦 Interactive Waterfall BOM & Costing")

try:
    # --- LOAD DATA ---
    df_master = pd.read_csv(MASTER_FILE, encoding='utf-8-sig')
    df_links = pd.read_csv(LINKS_FILE, encoding='utf-8-sig')
    
    # --- CLEANING ---
    df_master['Part No.'] = df_master['Part No.'].astype(str).str.strip()
    df_master['Unit Cost'] = df_master['Unit Cost'].apply(clean_currency)
    item_details = df_master.set_index('Part No.').to_dict('index')

    df_links = df_links.iloc[:, :3] 
    df_links.columns = ['Parent Part', 'Child Part', 'Qty Per']
    df_links['Parent Part'] = df_links['Parent Part'].astype(str).str.strip()
    df_links['Child Part'] = df_links['Child Part'].astype(str).str.strip()
    df_links['Qty Per'] = pd.to_numeric(df_links['Qty Per'], errors='coerce').fillna(1.0)

    # --- HIERARCHY LOGIC ---
    parent_map = {}
    for _, row in df_links.iterrows():
        p, c, q = row['Parent Part'], row['Child Part'], row['Qty Per']
        if p not in parent_map: parent_map[p] = []
        parent_map[p].append((c, q))

    all_parents = set(df_links['Parent Part'].unique())
    all_children = set(df_links['Child Part'].unique())
    
    # POTENTIAL L0s: Parents that are never children
    potential_l0s = all_parents - all_children
    
    # REFINED L0s: Must be in Item Master AND marked as "Make"
    # This removes hardware or raw materials that might be "dangling"
    final_l0_list = [
        sku for sku in potential_l0s 
        if item_details.get(sku, {}).get('Make/Buy') == 'Make'
    ]
    final_l0_list = sorted(final_l0_list)

    # --- SIDEBAR FILTERS ---
    st.sidebar.header("Filter Settings")
    only_make = st.sidebar.checkbox("Show 'Make' Items Only (L0 focus)", value=True)
    search_query = st.sidebar.text_input("Search Part Number", "")

    # Apply Sidebar Filters to the List
    display_list = final_l0_list if only_make else sorted(list(potential_l0s))
    if search_query:
        display_list = [item for item in display_list if search_query.upper() in item.upper()]

    # --- SELECTION ---
    selected_l0 = st.selectbox(f"Select Saleable SKU ({len(display_list)} found)", ["-- Select --"] + display_list)

    if selected_l0 != "-- Select --":
        waterfall = []
        def explode(parent, depth=0, mult=1):
            for child, qty in parent_map.get(parent, []):
                total_qty = mult * qty
                det = item_details.get(child, {})
                u_cost = det.get('Unit Cost', 0.0)
                waterfall.append({
                    'Level': f"{'  ' * depth}↳ {child}",
                    'Description': det.get('Part Description', 'N/A'),
                    'Make/Buy': det.get('Make/Buy', 'N/A'),
                    'Qty Per': qty,
                    'Total Req.': total_qty,
                    'Unit Cost': f"${u_cost:,.2f}",
                    'Ext. Cost': u_cost * total_qty
                })
                explode(child, depth + 1, total_qty)

        explode(selected_l0)
        df_wf = pd.DataFrame(waterfall)
        
        # Display Results
        c1, c2 = st.columns(2)
        c1.metric("Total Roll-up Cost", f"${df_wf['Ext. Cost'].sum():,.2f}")
        c2.metric("Component Count", f"{int(df_wf['Total Req.'].sum())}")
        
        df_display = df_wf.copy()
        df_display['Ext. Cost'] = df_display['Ext. Cost'].apply(lambda x: f"${x:,.2f}")
        st.dataframe(df_display, use_container_width=True, hide_index=True)

except Exception as e:
    st.error(f"Error: {e}")
