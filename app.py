import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="Waterfall BOM & Costing", layout="wide")

st.title("Interactive Waterfall BOM & Costing Tool")
st.markdown("Upload your updated **Item Master** and **BOM Links** (v4) to see the full roll-up.")

# File uploaders
col1, col2 = st.columns(2)
with col1:
    master_file = st.file_uploader("Upload Item Master (v4)", type=["csv"])
with col2:
    links_file = st.file_uploader("Upload BOM Links (v4)", type=["csv"])

def clean_currency(value):
    """Helper to clean '$' and commas from the Unit Cost strings."""
    if isinstance(value, str):
        return float(re.sub(r'[^\d.]', '', value))
    return float(value)

if master_file and links_file:
    # Load Data
    df_master = pd.read_csv(master_file)
    df_links = pd.read_csv(links_file)

    # Clean Data
    df_master['Part No.'] = df_master['Part No.'].astype(str).str.strip()
    df_master['Unit Cost'] = df_master['Unit Cost'].apply(clean_currency)
    
    df_links['Parent Part'] = df_links['Parent Part'].astype(str).str.strip()
    df_links['Child Part'] = df_links['Child Part'].astype(str).str.strip()
    # Fill missing Qty with 1
    df_links['Qty Per'] = pd.to_numeric(df_links['Qty Per'], errors='coerce').fillna(1.0)
    
    # Dictionaries for lookup
    item_details = df_master.set_index('Part No.').to_dict('index')
    
    # Map Parent to its children: { 'ParentID': [(ChildID, Qty), ...] }
    parent_map = {}
    for _, row in df_links.iterrows():
        p, c, q = row['Parent Part'], row['Child Part'], row['Qty Per']
        if p not in parent_map:
            parent_map[p] = []
        parent_map[p].append((c, q))

    # Identify Top-Level (L0) SKUs
    all_parents = set(df_links['Parent Part'].unique())
    all_children = set(df_links['Child Part'].unique())
    l0_skus = sorted(list(all_parents - all_children))

    selected_l0 = st.selectbox("Select L0 Saleable SKU", ["-- Select SKU --"] + l0_skus)

    if selected_l0 != "-- Select SKU --":
        waterfall = []

        def explode_bom(parent_id, current_depth=0, multiplier=1):
            children = parent_map.get(parent_id, [])
            for child_id, qty_per in children:
                # Calculate total qty needed based on parent multiplier
                total_qty = multiplier * qty_per
                
                # Fetch details from Item Master
                details = item_details.get(child_id, {})
                desc = details.get('Part Description', "UNKNOWN")
                u_cost = details.get('Unit Cost', 0.0)
                category = details.get('Category', "N/A")
                ext_cost = u_cost * total_qty
                
                # Visual hierarchy string
                indent = "    " * current_depth
                
                waterfall.append({
                    'Visual Tree': f"{indent}↳ {child_id}",
                    'Part No.': child_id,
                    'Description': desc,
                    'Category': category,
                    'Qty Per': qty_per,
                    'Total Req.': total_qty,
                    'Unit Cost': f"${u_cost:,.2f}",
                    'Ext. Cost': ext_cost
                })
                
                # Recurse if the child is also a parent
                explode_bom(child_id, current_depth + 1, total_qty)

        # Trigger the waterfall
        explode_bom(selected_l0)
        
        if waterfall:
            wf_df = pd.DataFrame(waterfall)
            
            # Summary Metrics
            total_sku_cost = wf_df['Ext. Cost'].sum()
            total_parts = wf_df['Total Req.'].sum()
            
            m1, m2 = st.columns(2)
            m1.metric("Total Roll-up Cost", f"${total_sku_cost:,.2f}")
            m2.metric("Total Component Count", f"{int(total_parts)} units")
            
            # Formatting for display
            display_df = wf_df.copy()
            display_df['Ext. Cost'] = display_df['Ext. Cost'].apply(lambda x: f"${x:,.2f}")
            
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            # CSV Download
            csv_data = wf_df.to_csv(index=False).encode('utf-8')
            st.download_button(f"Export {selected_l0} Waterfall", csv_data, f"BOM_{selected_l0}.csv", "text/csv")
        else:
            st.warning("No children found for this SKU in the BOM Links.")