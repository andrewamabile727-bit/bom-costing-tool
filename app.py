import streamlit as st
import pandas as pd
import re
import os
import io

st.set_page_config(page_title="BOM Tool v7.2", layout="wide")

# --- 1. SETTINGS & FILENAMES ---
SKU_FILE = "L0&L1 Skus..xlsx - Sheet1.csv" 
MASTER_FILE = "Item_Master_v4_Template.csv" 
LINKS_FILE = "BOM_Links_v4_Template.csv"
MAX_BOM_DEPTH = 20  # Circuit breaker for infinite loops

def clean_val(x):
    """Deep cleans every cell: removes spaces, newlines, and quotes."""
    if pd.isna(x): return ""
    return str(x).replace('\n', ' ').replace('\r', '').strip()

def clean_currency(value):
    """Converts strings like '$1.11' or ' $- ' into 0.0 or a float."""
    s = clean_val(value)
    if not s or s in ["-", "$-"]: return 0.0
    cleaned = re.sub(r'[^\d.]', '', s)
    try:
        return float(cleaned) if cleaned else 0.0
    except:
        return 0.0

def load_and_sanitize(filename):
    """Loads CSV and removes 'Ghost Columns' caused by trailing commas."""
    if not os.path.exists(filename):
        return None
    df = pd.read_csv(filename, encoding='utf-8-sig', on_bad_lines='skip')
    # Remove columns that have no name (Unnamed)
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    # Clean headers and data
    df.columns = [" ".join(str(c).split()) for c in df.columns]
    df = df.applymap(clean_val)
    return df

# --- 2. DATA INITIALIZATION ---
try:
    df_m = load_and_sanitize(MASTER_FILE)
    df_l = load_and_sanitize(LINKS_FILE)
    df_s = load_and_sanitize(SKU_FILE)

    if df_m is None or df_l is None or df_s is None:
        st.error("🚨 Missing files on GitHub. Please ensure filenames match exactly.")
        st.stop()

    # Identify the Cost column (handles 'Unit Cost' or ' Unit Cost ')
    cost_col = next((c for c in df_m.columns if "Cost" in c), None)
    if cost_col:
        df_m['Cost_Num'] = df_m[cost_col].apply(clean_currency)
    else:
        df_m['Cost_Num'] = 0.0

    # Build Master Lookup
    item_master = df_m.set_index('Part No.').to_dict('index')

    # Build Links Map (Using column indices to stay robust)
    # 0:Parent, 1:Child, 2:Qty, 3:UOM
    links_dict = {}
    for _, row in df_l.iterrows():
        p = row.iloc[0]
        if p not in links_dict: links_dict[p] = []
        links_dict[p].append({
            'child': row.iloc[1],
            'qty': pd.to_numeric(row.iloc[2], errors='coerce') or 1.0,
            'uom': row.iloc[3] if len(row) > 3 else "Ea."
        })

    # --- 3. UI SIDEBAR ---
    st.sidebar.title("BOM Explorer")
    cat_map = {
        "Saleable SKUs": ("Saleable Sku", "Saleable Sku Description"),
        "Base Assemblies": ("Base Assy Kit", "Base Assy Kit Description"),
        "Countertop Assemblies": ("Countertop Assy Kit", "Countertop Assy Kit Description"),
        "Cladding Assemblies": ("Cladding Assy Kit", "Cladding Assy Kit Description"),
        "Finish Kits": ("Finish Kit", "Finish Kit Description")
    }
    mode = st.sidebar.selectbox("Category", list(cat_map.keys()))
    id_col, desc_col = cat_map[mode]

    # Create Dropdown
    sku_list = []
    if id_col in df_s.columns:
        valid = df_s[df_s[id_col] != ""]
        for _, row in valid.drop_duplicates(subset=[id_col]).iterrows():
            sku_list.append(f"{row[id_col]} | {row.get(desc_col, 'N/A')}")
    
    target = st.selectbox(f"Select {mode}", ["-- Select --"] + sorted(sku_list))

    if target != "-- Select --":
        sel_id = target.split(" | ")[0].strip()
        sel_desc = target.split(" | ")[1].strip()

        # --- 4. BOM EXPLOSION (With Loop Protection) ---
        bom_data = []
        def explode(parent_id, depth=1, multiplier=1):
            if depth > MAX_BOM_DEPTH: return # Stop infinite loops
            
            for component in links_dict.get(parent_id, []):
                c_id = component['child']
                t_qty = multiplier * component['qty']
                meta = item_master.get(c_id, {})
                
                bom_data.append({
                    'Level': depth,
                    'Parent': parent_id,
                    'Part No.': c_id,
                    'Description': meta.get('Part Description', 'N/A'),
                    'Qty Per': component['qty'],
                    'Total Req': t_qty,
                    'UOM': component['uom'],
                    'Unit Cost': meta.get('Cost_Num', 0.0),
                    'Ext. Cost': meta.get('Cost_Num', 0.0) * t_qty,
                    'Make/Buy': meta.get('Make/Buy', 'N/A')
                })
                explode(c_id, depth + 1, t_qty)

        explode(sel_id)

        if bom_data:
            final_df = pd.DataFrame(bom_data)
            
            # Metrics
            st.metric("Total Cost", f"${final_df['Ext. Cost'].sum():,.2f}")

            # Display Table
            disp_df = final_df.copy()
            disp_df['Unit Cost'] = disp_df['Unit Cost'].map("${:,.2f}".format)
            disp_df['Ext. Cost'] = disp_df['Ext. Cost'].map("${:,.2f}".format)
            st.dataframe(disp_df, use_container_width=True, hide_index=True)

            # --- 5. EXPORT ---
            header = f"Assembly Number:, {sel_id}\nDescription:, {sel_desc}\n\n"
            csv_body = final_df.to_csv(index=False)
            st.download_button(
                "📥 Download BOM Report", 
                (header + csv_body).encode('utf-8-sig'), 
                f"BOM_{sel_id}.csv", 
                "text/csv"
            )
        else:
            st.warning(f"No components found for {sel_id}. Double-check the ID in the BOM Links file.")

except Exception as e:
    st.error(f"Critical Error: {e}")
    st.info("Check your CSV files for empty rows at the bottom or duplicate headers.")
