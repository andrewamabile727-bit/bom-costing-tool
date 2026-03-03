import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="BOM Tool v4.5", layout="wide")

# BACK TO YOUR ORIGINAL FILENAME
MASTER_FILE = "Item_Master_v4_Template.csv" 
LINKS_FILE = "BOM_Links_v4_Template.csv"

def clean_currency(value):
    if pd.isna(value) or value == "": return 0.0
    if isinstance(value, str):
        cleaned = re.sub(r'[^\d.]', '', value)
        return float(cleaned) if cleaned else 0.0
    return float(value)

st.title("📦 Manufacturing BOM & Costing Tool")

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

    # Identify all Roots (Top-Level SKUs)
    all_parents = set(df_links['Parent Part'].unique())
    all_children = set(df_links['Child Part'].unique())
    root_ids = sorted(list(all_parents - all_children))

    # --- DROPDOWN PREPARATION ---
    sku_options = []
    for rid in root_ids:
        # Fetch description from Master
        desc = item_details.get(rid, {}).get('Part Description', "⚠️ NOT IN MASTER")
        sku_options.append(f"{rid} | {desc}")

    # --- UI SELECTION ---
    st.sidebar.header("Navigation")
    search_query = st.sidebar.text_input("Search SKU or Name", "")
    if search_query:
        sku_options = [opt for opt in sku_options if search_query.upper() in opt.upper()]

    selected_label = st.selectbox(f"Select Saleable SKU ({len(sku_options)} Found)", ["-- Select --"] + sku_options)

    if selected_label != "-- Select --":
        selected_sku = selected_label.split(" | ")[0].strip()
        selected_desc = item_details.get(selected_sku, {}).get('Part Description', "N/A")

        # --- HEADER ---
        st.markdown("---")
        st.header(f"BOM Breakdown: {selected_sku}")
        st.subheader(f"Description: {selected_desc}")
        
        # Check if user needs to update the master
        if "TBD" in selected_desc:
            st.warning("ℹ️ Note: This SKU's description and cost are currently placeholders in your Item Master file.")
        
        st.markdown("---")

        # --- WATERFALL CALCULATION ---
        waterfall = []
        def explode(parent, depth=0, mult=1):
            for child, qty in parent_map.get(parent, []):
                total_qty = mult * qty
                det = item_details.get(child, {})
                u_cost = det.get('Unit Cost', 0.0)
                
                waterfall.append({
                    'Level': f"{'  ' * depth}↳ {child}",
                    'Part No.': child,
                    'Description': det.get('Part Description', 'N/A'),
                    'Category': det.get('Category', 'N/A'),
                    'Qty Per': qty,
                    'Total Req.': total_qty,
                    'Unit Cost': f"${u_cost:,.2f}",
                    'Ext. Cost': u_cost * total_qty
                })
                explode(child, depth + 1, total_qty)

        explode(selected_sku)
        
        if waterfall:
            df_wf = pd.DataFrame(waterfall)
            
            # Metrics
            c1, c2 = st.columns(2)
            c1.metric("Total Roll-up Cost", f"${df_wf['Ext. Cost'].sum():,.2f}")
            c2.metric("Component Count", f"{int(df_wf['Total Req.'].sum())} parts")
            
            # Display
            df_display = df_wf.copy()
            df_display['Ext. Cost'] = df_display['Ext. Cost'].apply(lambda x: f"${x:,.2f}")
            st.dataframe(df_display, use_container_width=True, hide_index=True)
            
            # Export
            csv = df_wf.to_csv(index=False).encode('utf-8')
            st.download_button(f"Export {selected_sku} BOM", csv, f"BOM_{selected_sku}.csv", "text/csv")
        else:
            st.warning("⚠️ This SKU has no children defined in the Links file.")

except Exception as e:
    st.error(f"System Error: {e}")
