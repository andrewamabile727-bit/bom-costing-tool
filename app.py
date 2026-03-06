import streamlit as st
import pandas as pd
import re
import os

st.set_page_config(page_title="BOM Tool v8.0", layout="wide")

# --- 1. CONFIGURATION (Aggressive Filename Handling) ---
# We use a list to find the file even if the name has extra dots or spaces
def find_file(pattern):
    for f in os.listdir('.'):
        if pattern.lower() in f.lower() and f.endswith('.csv'):
            return f
    return None

SKU_FILE = find_file("L0&L1 Skus") 
MASTER_FILE = find_file("Item_Master") 
LINKS_FILE = find_file("BOM_Links")

def clean_currency(value):
    if pd.isna(value) or str(value).strip() in ["", "-", "$-", "$ -"]: return 0.0
    cleaned = re.sub(r'[^\d.]', '', str(value))
    try:
        return float(cleaned) if cleaned else 0.0
    except:
        return 0.0

def load_and_clean(path):
    if not path or not os.path.exists(path): return None
    # Read with 'python' engine to be more robust with weird line endings
    df = pd.read_csv(path, encoding='utf-8-sig', on_bad_lines='skip', engine='python')
    # Remove "Ghost" columns
    df = df.loc[:, ~df.columns.str.contains('^Unnamed|^$')]
    # Clean headers: remove spaces, dots, and special chars
    df.columns = [" ".join(str(c).split()).strip() for c in df.columns]
    # Clean data: strip all text cells
    df = df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)
    return df

# --- 2. DATA LOAD ---
st.title("🛠️ BOM Professional v8.0")

try:
    df_m = load_and_clean(MASTER_FILE)
    df_l = load_and_clean(LINKS_FILE)
    df_s = load_and_clean(SKU_FILE)

    if any(x is None for x in [df_m, df_l, df_s]):
        st.error("🚨 Missing core files. Ensure CSVs are uploaded to GitHub.")
        st.stop()

    # Create Item Master Lookup
    cost_col = next((c for c in df_m.columns if "Cost" in c), df_m.columns[-1])
    df_m['Clean_Price'] = df_m[cost_col].apply(clean_currency)
    master_dict = df_m.set_index('Part No.').to_dict('index')

    # Create BOM Structure (Parent -> Children)
    # Using position-based indexing to bypass column name shifts
    bom_map = {}
    for _, row in df_l.iterrows():
        parent = str(row.iloc[0])
        if parent not in bom_map: bom_map[parent] = []
        bom_map[parent].append({
            'child': str(row.iloc[1]),
            'qty': pd.to_numeric(row.iloc[2], errors='coerce') or 1.0,
            'uom': str(row.iloc[3]) if len(row) > 3 else "Ea."
        })

    # --- 3. NAVIGATION ---
    st.sidebar.header("Settings")
    cat_opts = {
        "Saleable SKUs": ("Saleable Sku", "Saleable Sku Description"),
        "Base Assemblies": ("Base Assy Kit", "Base Assy Kit Description"),
        "Countertop": ("Countertop Assy Kit", "Countertop Assy Kit Description"),
        "Cladding": ("Cladding Assy Kit", "Cladding Assy Kit Description"),
        "Finish Kits": ("Finish Kit", "Finish Kit Description")
    }
    category = st.sidebar.selectbox("Select View", list(cat_opts.keys()))
    id_col, desc_col = cat_opts[category]

    # Generate selection list
    options = []
    if id_col in df_s.columns:
        # Filter out empty rows
        df_valid = df_s[df_s[id_col].astype(str).str.len() > 2]
        for _, row in df_valid.drop_duplicates(subset=[id_col]).iterrows():
            options.append(f"{row[id_col]} | {row.get(desc_col, 'N/A')}")

    selected_item = st.selectbox(f"Choose {category}", ["-- Select --"] + sorted(options))

    if selected_item != "-- Select --":
        sel_id = selected_item.split(" | ")[0].strip()
        sel_desc = selected_item.split(" | ")[1].strip()

        # --- 4. EXPLOSION ENGINE ---
        bom_results = []
        path_stack = set() # Prevent infinite loops

        def explode(parent, depth=1, mult=1):
            if depth > 12 or parent in path_stack: return
            path_stack.add(parent)
            
            for item in bom_map.get(parent, []):
                c_id = item['child']
                t_qty = mult * item['qty']
                meta = master_dict.get(c_id, {})
                
                bom_results.append({
                    'Level': depth,
                    'Parent': parent,
                    'Part No.': c_id,
                    'Description': meta.get('Part Description', 'N/A'),
                    'Total Qty': t_qty,
                    'UOM': item['uom'],
                    'Unit Cost': meta.get('Clean_Price', 0.0),
                    'Ext. Cost': meta.get('Clean_Price', 0.0) * t_qty,
                    'Category': meta.get('Category', 'N/A')
                })
                explode(c_id, depth + 1, t_qty)
            path_stack.remove(parent)

        explode(sel_id)

        if bom_results:
            df_final = pd.DataFrame(bom_results)
            
            # Summary Metrics
            c1, c2 = st.columns(2)
            c1.metric("Total Roll-up Cost", f"${df_final['Ext. Cost'].sum():,.2f}")
            c2.metric("Total Parts Count", f"{len(df_final)}")

            # Data Display
            df_disp = df_final.copy()
            df_disp['Unit Cost'] = df_disp['Unit Cost'].map("${:,.2f}".format)
            df_disp['Ext. Cost'] = df_disp['Ext. Cost'].map("${:,.2f}".format)
            st.dataframe(df_disp, use_container_width=True, hide_index=True)
            
            # Export
            csv_export = f"BOM REPORT\nAssembly: {sel_id}\nDescription: {sel_desc}\n\n" + df_final.to_csv(index=False)
            st.download_button("📥 Download Report", csv_export.encode('utf-8-sig'), f"BOM_{sel_id}.csv")
        else:
            st.warning(f"⚠️ Data Disconnect: The ID '{sel_id}' exists in your SKU list but has NO matching components in the 'BOM Links' file.")
            st.info("Check if the 'Parent Part' column in your Links CSV uses different ID formatting.")

except Exception as e:
    st.error(f"Critical System Error: {e}")
