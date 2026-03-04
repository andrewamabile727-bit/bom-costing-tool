import streamlit as st
import pandas as pd
import re
import altair as alt
import os

st.set_page_config(page_title="BOM Tool v6.0", layout="wide")

# --- 1. FILENAME CONFIGURATION ---
SKU_FILE = "L0&L1 Skus..xlsx - Sheet1.csv" 
MASTER_FILE = "Item_Master_v4_Template.csv" 
LINKS_FILE = "BOM_Links_v4_Template.csv" # Ensure this file is uploaded!

def clean_currency(value):
    if pd.isna(value) or value == "": return 0.0
    if isinstance(value, str):
        cleaned = re.sub(r'[^\d.]', '', value)
        return float(cleaned) if cleaned else 0.0
    return float(value)

def super_clean_df(df):
    df.columns = [" ".join(str(c).split()) for c in df.columns]
    df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)
    return df

# --- 2. FILE CHECK ---
missing_files = []
for f in [SKU_FILE, MASTER_FILE, LINKS_FILE]:
    if not os.path.exists(f):
        missing_files.append(f)

if missing_files:
    st.error(f"🚨 Missing Files: {', '.join(missing_files)}")
    st.info("Please ensure all 3 CSV files are uploaded to the same folder as this app.")
    st.stop()

try:
    # --- 3. DATA LOADING ---
    df_master = super_clean_df(pd.read_csv(MASTER_FILE, encoding='utf-8-sig'))
    df_links = super_clean_df(pd.read_csv(LINKS_FILE, encoding='utf-8-sig'))
    df_sku_list = super_clean_df(pd.read_csv(SKU_FILE, encoding='utf-8-sig'))

    df_master['Unit Cost'] = df_master['Unit Cost'].apply(clean_currency)
    df_master['Category'] = df_master['Category'].fillna('Uncategorized')
    item_details = df_master.set_index('Part No.').to_dict('index')

    df_links.columns = ['Parent Part', 'Child Part', 'Qty Per'] + list(df_links.columns[3:])
    df_links['Qty Per'] = pd.to_numeric(df_links['Qty Per'], errors='coerce').fillna(1.0)

    parent_map = {}
    for _, row in df_links.iterrows():
        p, c, q = str(row['Parent Part']), str(row['Child Part']), row['Qty Per']
        if p not in parent_map: parent_map[p] = []
        parent_map[p].append((c, q))

    # --- 4. UI SIDEBAR ---
    st.sidebar.header("Navigation")
    ui_option = st.sidebar.radio(
        "Choose Assembly Category:",
        ["Option 1: Saleable SKUs", "Option 2: Base Assemblies", 
         "Option 3: Countertop Assemblies", "Option 4: Cladding Assemblies", "Option 5: Finish Kits"]
    )

    mapping = {
        "Option 1: Saleable SKUs": ("Saleable Sku", "Saleable Sku Description"),
        "Option 2: Base Assemblies": ("Base Assy Kit", "Base Assy Kit Description"),
        "Option 3: Countertop Assemblies": ("Countertop Assy Kit", "Countertop Assy Kit Description"),
        "Option 4: Cladding Assemblies": ("Cladding Assy Kit", "Cladding Assy Kit Description"),
        "Option 5: Finish Kits": ("Finish Kit", "Finish Kit Description")
    }

    id_col, desc_col = mapping[ui_option]
    
    sku_options = []
    if id_col in df_sku_list.columns:
        unique_rows = df_sku_list.drop_duplicates(subset=[id_col])
        for _, row in unique_rows.iterrows():
            p_id = str(row[id_col])
            p_desc = str(row[desc_col])
            if p_id and p_id.lower() != "nan":
                sku_options.append(f"{p_id} | {p_desc}")

    selected_label = st.selectbox(f"Select from {ui_option}", ["-- Select --"] + sorted(sku_options))

    if selected_label != "-- Select --":
        selected_sku = selected_label.split(" | ")[0].strip()
        
        st.markdown("---")
        st.header(f"BOM Breakdown: {selected_sku}")
        
        # --- 5. BOM EXPLOSION ---
        waterfall = []
        def explode(parent, depth=0, mult=1):
            for child, qty in parent_map.get(parent, []):
                total_qty = mult * qty
                det = item_details.get(child, {})
                u_cost = det.get('Unit Cost', 0.0)
                waterfall.append({
                    'Level': f"{'..' * depth}↳ {child}",
                    'Part No.': child,
                    'Description': det.get('Part Description', 'N/A'),
                    'Category': det.get('Category', 'Uncategorized'),
                    'Qty Per': qty,
                    'Total Req.': total_qty,
                    'Unit Cost': u_cost, 
                    'Ext. Cost': u_cost * total_qty
                })
                explode(child, depth + 1, total_qty)

        explode(selected_sku)

        if waterfall:
            df_wf = pd.DataFrame(waterfall)
            total_val = df_wf['Ext. Cost'].sum()
            
            # --- 6. METRICS ---
            m1, m2, m3 = st.columns(3)
            m1.metric("Total Roll-up Cost", f"${total_val:,.2f}")
            m2.metric("Total Parts Count", int(df_wf['Total Req.'].sum()))
            m3.metric("Unique Items", len(df_wf))

            # --- 7. VISUAL ANALYTICS ---
            if total_val > 0:
                c1, c2 = st.columns(2)
                with c1:
                    st.write("### 📊 Spend by Category")
                    df_cat = df_wf.groupby('Category')['Ext. Cost'].sum().reset_index()
                    chart1 = alt.Chart(df_cat).mark_arc(innerRadius=50).encode(
                        theta="Ext. Cost:Q", color="Category:N", tooltip=['Category', alt.Tooltip('Ext. Cost', format="$,.2f")]
                    ).properties(height=300)
                    st.altair_chart(chart1, use_container_width=True)
                with c2:
                    st.write("### 📈 Top 10 Cost Drivers")
                    df_dr = df_wf.groupby(['Part No.', 'Description'])['Ext. Cost'].sum().reset_index().nlargest(10, 'Ext. Cost')
                    chart2 = alt.Chart(df_dr).mark_bar().encode(
                        x=alt.X('Ext. Cost:Q', title="Total Cost"),
                        y=alt.Y('Part No.:N', sort='-x'),
                        tooltip=['Description', alt.Tooltip('Ext. Cost', format="$,.2f")]
                    ).properties(height=300)
                    st.altair_chart(chart2, use_container_width=True)
            else:
                st.info("💡 No cost data available to graph. Total cost is $0.00.")

            # --- 8. DATA TABLE ---
            st.write("### 📑 Detailed Component List")
            st.dataframe(df_wf, use_container_width=True, hide_index=True)
        else:
            st.warning("⚠️ No components found. Is the Part Number in the BOM Links file exactly the same?")

except Exception as e:
    st.error(f"Critical Error: {e}")
