import streamlit as st
import pandas as pd
import re
import os

st.set_page_config(page_title="BOM Tool v8.4", layout="wide")

# --- 1. ROBUST NUMERIC CONVERTER ---
def force_numeric(val):
    """Strips $, commas, and spaces to ensure a math-ready float."""
    if pd.isna(val) or str(val).strip() in ["", "-", "$-", "$ -"]:
        return 0.0
    # Remove everything except numbers and the decimal point
    clean_str = re.sub(r'[^\d.]', '', str(val))
    try:
        return float(clean_str) if clean_str else 0.0
    except:
        return 0.0

# --- 2. DATA LOADING ENGINE ---
def load_and_clean_file(pattern):
    fname = next((f for f in os.listdir('.') if pattern.lower() in f.lower() and f.endswith('.csv')), None)
    if not fname:
        return None
    
    # Read with utf-8-sig to handle Excel artifacts
    df = pd.read_csv(fname, encoding='utf-8-sig', on_bad_lines='skip')
    
    # Standardize Headers: Strip spaces and remove 'Unnamed' columns
    df.columns = [str(c).strip() for c in df.columns]
    df = df.loc[:, ~df.columns.str.contains('^Unnamed|^$')]
    
    # Standardize Data: Strip spaces from all text cells
    df = df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)
    return df

# --- 3. MAIN APPLICATION ---
st.title("🛠️ BOM Professional v8.4")

try:
    df_m = load_and_clean_file("Item_Master")
    df_l = load_and_clean_file("BOM_Links")
    df_s = load_and_clean_file("L0&L1 Skus")

    if any(x is None for x in [df_m, df_l, df_s]):
        st.error("🚨 Missing Files! Ensure 'Item_Master', 'BOM_Links', and 'L0&L1 Skus' are in your GitHub folder.")
        st.stop()

    # Pre-process Costs
    cost_col = next((c for c in df_m.columns if "Cost" in c), "Unit Cost")
    df_m['Math_Cost'] = df_m[cost_col].apply(force_numeric)
    
    # Create Lookups
    master_lookup = df_m.set_index('Part No.').to_dict('index')
    
    # Create Parent-Child Tree
    bom_tree = {}
    for _, row in df_l.iterrows():
        p = str(row.iloc[0]) # Parent
        if p not in bom_tree: bom_tree[p] = []
        bom_tree[p].append({
            'child': str(row.iloc[1]),
            'qty': pd.to_numeric(row.iloc[2], errors='coerce') or 1.0,
            'uom': str(row.iloc[3]) if len(row) > 3 else "Ea."
        })

    # --- 4. NAVIGATION ---
    cats = {
        "Saleable SKUs": ("Saleable Sku", "Saleable Sku Description"),
        "Base Assemblies": ("Base Assy Kit", "Base Assy Kit Description"),
        "Countertops": ("Countertop Assy Kit", "Countertop Assy Kit Description"),
        "Cladding": ("Cladding Assy Kit", "Cladding Assy Kit Description")
    }
    view = st.sidebar.selectbox("Category", list(cats.keys()))
    id_f, desc_f = cats[view]

    # Generate Selector
    options = []
    if id_f in df_s.columns:
        valid = df_s[df_s[id_f].notna() & (df_s[id_f] != "")]
        for _, r in valid.drop_duplicates(subset=[id_f]).iterrows():
            options.append(f"{r[id_f]} | {r.get(desc_f, 'N/A')}")

    choice = st.selectbox(f"Select {view}", ["-- Select --"] + sorted(options))

    if choice != "-- Select --":
        sel_id = choice.split(" | ")[0].strip()
        
        # --- 5. EXPLOSION ENGINE ---
        bom_output = []
        def explode(pid, depth=1, mult=1):
            if depth > 12: return
            for item in bom_tree.get(pid, []):
                cid = item['child']
                total_qty = mult * item['qty']
                meta = master_lookup.get(cid, {})
                
                bom_output.append({
                    'Level': depth,
                    'Parent': pid,
                    'Part No.': cid,
                    'Description': meta.get('Part Description', 'N/A'),
                    'Total Qty': total_qty,
                    'UOM': item['uom'],
                    'Unit Cost': meta.get('Math_Cost', 0.0),
                    'Ext. Cost': meta.get('Math_Cost', 0.0) * total_qty
                })
                explode(cid, depth + 1, total_qty)

        explode(sel_id)

        if bom_output:
            res_df = pd.DataFrame(bom_output)
            st.metric("Total Roll-up Cost", f"${res_df['Ext. Cost'].sum():,.2f}")
            
            # Format display
            disp = res_df.copy()
            disp['Unit Cost'] = disp['Unit Cost'].map("${:,.2f}".format)
            disp['Ext. Cost'] = disp['Ext. Cost'].map("${:,.2f}".format)
            st.dataframe(disp, use_container_width=True, hide_index=True)
            
            # Export
            st.download_button("📥 Download BOM", res_df.to_csv(index=False).encode('utf-8-sig'), f"BOM_{sel_id}.csv")
        else:
            st.warning(f"No components found for {sel_id}. Check that this ID exists in the 'Parent Part' column of your Links file.")

except Exception as e:
    st.error(f"System Error: {e}")
    st.info("Technical Detail: Check if your CSV files have duplicate 'Part No.' entries with different data.")
