import streamlit as st
import pandas as pd
import re
import altair as alt

st.set_page_config(page_title="BOM Tool v5.8", layout="wide")

# --- FILE CONFIGURATION ---
# Note: Ensure these filenames match your GitHub exactly.
SKU_FILE = "L0&L1 Skus..xlsx - Sheet1.csv" 
MASTER_FILE = "Item_Master_v4_Template.csv" 
LINKS_FILE = "BOM_Links_v4_Template.csv"

def clean_currency(value):
    if pd.isna(value) or value == "": return 0.0
    if isinstance(value, str):
        cleaned = re.sub(r'[^\d.]', '', value)
        return float(cleaned) if cleaned else 0.0
    return float(value)

def super_clean_headers(df):
    # This removes all double spaces and trailing spaces from column names
    df.columns = [" ".join(str(c).split()) for c in df.columns]
    return df

try:
    # --- 1. DATA LOADING ---
    df_master = super_clean_headers(pd.read_csv(MASTER_FILE, encoding='utf-8-sig'))
    df_links = super_clean_headers(pd.read_csv(LINKS_FILE, encoding='utf-8-sig'))
    df_sku_list = super_clean_headers(pd.read_csv(SKU_FILE, encoding='utf-8-sig'))

    # --- 2. DATA PREP ---
    df_master['Part No.'] = df_master['Part No.'].astype(str).str.strip()
    df_master['Unit Cost'] = df_master['Unit Cost'].apply(clean_currency)
    df_master['Category'] = df_master['Category'].fillna('Uncategorized')
    item_details = df_master.set_index('Part No.').to_dict('index')

    # Ensure links columns are standard
    df_links.columns = ['Parent Part', 'Child Part', 'Qty Per'] + list(df_links.columns[3:])
    df_links['Parent Part'] = df_links['Parent Part'].astype(str).str.strip()
    df_links['Child Part'] = df_links['Child Part'].astype(str).str.strip()
    df_links['Qty Per'] = pd.to_numeric(df_links['Qty Per'], errors='coerce').fillna(1.0)

    # Build Hierarchy
    parent_map = {}
    for _, row in df_links.iterrows():
        p, c, q = row['Parent Part'], row['Child Part'], row['Qty Per']
        if p not in parent_map: parent_map[p] = []
        parent_map[p].append((c, q))

    # --- 3. UI SIDEBAR ---
    st.sidebar.header("Navigation")
    ui_option = st.sidebar.radio(
        "Choose Assembly Category:",
        ["Option 1: Saleable SKUs (0 Prefix)", "Option 2: Base Assemblies", 
         "Option 3: Countertop Assemblies", "Option 4: Cladding Assemblies", "Option 5: Finish Kits"]
    )

    mapping = {
        "Option 1: Saleable SKUs (0 Prefix)": ("Saleable Sku", "Saleable Sku Description"),
        "Option 2: Base Assemblies": ("Base Assy Kit", "Base Assy Kit Description"),
        "Option 3: Countertop Assemblies": ("Countertop Assy Kit", "Countertop Assy Kit Description"),
        "Option 4: Cladding Assemblies": ("Cladding Assy Kit", "Cladding Assy Kit Description"),
        "Option 5: Finish Kits": ("Finish Kit", "Finish Kit Description")
    }

    id_col, desc_col = mapping[ui_option]
    
    sku_options = []
    # Using drop_duplicates on the cleaned id_col
    unique_rows = df_sku_list.drop_duplicates(subset=[id_col])
    for _, row in unique_rows.iterrows():
        p_id = str(row[id_col]).strip()
        p_desc = str(row[desc_col]).strip()
        if p_id and p_id.lower() != "nan":
            sku_options.append(f"{p_id} | {p_desc}")

    selected_label = st.selectbox(f"Select from {ui_option}", ["-- Select --"] + sorted(sku_options))

    if selected_label != "-- Select --":
        selected_sku = selected_label.split(" | ")[0].strip()
        selected_name = selected_label.split(" | ")[1].strip()

        st.markdown("---")
        st.header(f"BOM Breakdown: {selected_sku}")
        st.subheader(f"Description: {selected_name}")

        # --- 4. BOM EXPLOSION ---
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
            total_cost = df_wf['Ext. Cost'].sum()
            
            # --- 5. METRICS ---
            m1, m2, m3 = st.columns(3)
            m1.metric("Total Roll-up Cost", f"${total_cost:,.2f}")
            m2.metric("Total Parts Count", int(df_wf['Total Req.'].sum()))
            m3.metric("Unique Line Items", len(df_wf))

            # --- 6. VISUAL ANALYTICS ---
            if total_cost > 0:
                col_chart1, col_chart2 = st.columns(2)

                with col_chart1:
                    st.write("### 📊 Spend by Category")
                    df_cat = df_wf.groupby('Category')['Ext. Cost'].sum().reset_index()
                    pie = alt.Chart(df_cat).mark_arc(innerRadius=60).encode(
                        theta=alt.Theta(field="Ext. Cost", type="quantitative"),
                        color=alt.Color(field="Category", type="nominal"),
                        tooltip=['Category', alt.Tooltip('Ext. Cost', format="$,.2f")]
                    ).properties(height=350)
                    st.altair_chart(pie, use_container_width=True)

                with col_chart2:
                    st.write("### 📈 Top 10 Cost Drivers")
                    df_drivers = df_wf.groupby(['Part No.', 'Description'])['Ext. Cost'].sum().reset_index()
                    df_drivers = df_drivers.sort_values(by='Ext. Cost', ascending=False).head(10)
                    bar = alt.Chart(df_drivers).mark_bar().encode(
                        x=alt.X('Ext. Cost:Q', title="Total Cost"),
                        y=alt.Y('Part No.:N', sort='-x', title="Part No"),
                        tooltip=['Part No.', 'Description', alt.Tooltip('Ext. Cost', format="$,.2f")]
                    ).properties(height=350)
                    st.altair_chart(bar, use_container_width=True)
            else:
                st.info("💡 Charts are hidden because the total cost is $0. Check if Part Numbers in Item Master match the BOM Links file.")

            # --- 7. DATA TABLE ---
            st.write("### 📑 Detailed Component List")
            df_display = df_wf.copy()
            df_display['Unit Cost'] = df_display['Unit Cost'].apply(lambda x: f"${x:,.2f}")
            df_display['Ext. Cost'] = df_display['Ext. Cost'].apply(lambda x: f"${x:,.2f}")
            st.dataframe(df_display, use_container_width=True, hide_index=True)
            
            # --- 8. EXPORT ---
            csv_data = df_wf.to_csv(index=False).encode('utf-8')
            st.download_button(label=f"📥 Download {selected_sku} BOM", data=csv_data, file_name=f"BOM_{selected_sku}.csv", mime="text/csv")
        else:
            st.warning("⚠️ No components found. Verify that the selected ID exists as a 'Parent Part' in your Links file.")

except Exception as e:
    st.error(f"System Error: {e}")
