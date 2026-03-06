import streamlit as st
import pandas as pd
import re
import os

st.set_page_config(page_title="BOM Tool v7.3", layout="wide")

# --- 1. SETTINGS ---
SKU_FILE = "L0&L1 Skus..xlsx - Sheet1.csv" 
MASTER_FILE = "Item_Master_v4_Template.csv" 
LINKS_FILE = "BOM_Links_v4_Template.csv"

def clean_currency(value):
    """Deep cleans currency strings like '$1.11' or ' $- '."""
    if pd.isna(value) or value == "": return 0.0
    s = str(value).strip()
    if s in ["-", "$-", "$ -", "0", "0.0"]: return 0.0
    cleaned = re.sub(r'[^\d.]', '', s)
    try:
        return float(cleaned) if cleaned else 0.0
    except:
        return 0.0

def load_and_scrub(file_path):
    """Loads CSV and aggressively removes extra spaces and ghost columns."""
    if not os.path.exists(file_path):
        return None
    # Load with utf-8-sig to handle Excel artifacts
    df = pd.read_csv(file_path, encoding='utf-8-sig', on_bad_lines='skip')
    
    # Remove columns that have no name or are just 'Unnamed'
    df = df.loc[:, ~df.columns.str.contains('^Unnamed|^$')]
    
    # Strip spaces from column headers
    df.columns = [str(c).strip() for c in df.columns]
    # Standardize column headers (remove double spaces)
    df.columns = [" ".join(str(c).split()) for c in df.columns]
    
    # Strip spaces from all text cells
    # Use 'map' for newer pandas, fallback to 'applymap' for older
    try:
        df = df.map(lambda x: x.strip() if isinstance(x, str) else x)
    except AttributeError:
        df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)
    
    return df

# --- 2. START APPLICATION ---
st.title("📦 BOM Explorer v7.3")

try:
    # --- 3. DATA LOADING ---
    df_m = load_and_scrub(MASTER_FILE)
    df_l = load_and_scrub(LINKS_FILE)
    df_s = load_and_scrub(SKU_FILE)

    # --- DIAGNOSTICS EXPANDER (Use this to troubleshoot) ---
    with st.expander("🔍 File Health & Diagnostics"):
        if df_m is not None:
            st.write(f"✅ **Item Master:** {len(df_m)} rows. Found columns: `{list(df_m.columns)}`")
        else: st.error("❌ Item Master file not found.")
        
        if df_l is not None:
            st.write(f"✅ **BOM Links:** {len(df_l)} rows. Found columns: `{list(df_l.columns)}`")
        else: st.error("❌ BOM Links file not found.")

    if df_m is None or df_l is None or df_s is None:
        st.stop()

    # --- 4. DATA PROCESSING ---
    # Find the Cost column even if it has slightly different naming
    cost_col = next((c for c in df_m.columns if "Cost" in c), None)
    if cost_col:
        df_m['Price'] = df_m[cost_col].apply(clean_currency)
    else:
        df_m['Price'] = 0.0

    # Create Master Lookup Dictionary
    # We use 'Part No.' as the key. If it's missing, use the first column.
    p_no_col = 'Part No.' if 'Part No.' in df_m.columns else df_m.columns[0]
    master_lookup = df_m.set_index(p_no_col).to_dict('index')

    # Build Structure Map from Links
    # Using indices to avoid "UM" vs "UOM" vs "Qty Per" naming issues
    structure = {}
    for _, row in df_l.iterrows():
        parent = str(row.iloc[0]) # Column 1
        child = str(row.iloc[1])  # Column 2
        qty = pd.to_numeric(row.iloc[2], errors='coerce') or 1.0
        uom = str(row.iloc[3]) if len(row) > 3 else "Ea."
        
        if parent not in structure: structure[parent] = []
        structure[parent].append({'child': child, 'qty': qty, 'uom': uom})

    # --- 5. UI SELECTION ---
    categories = {
        "Saleable SKUs": ("Saleable Sku", "Saleable Sku Description"),
        "Base Assemblies": ("Base Assy Kit", "Base Assy Kit Description"),
        "Countertop Assemblies": ("Countertop Assy Kit", "Countertop Assy Kit Description"),
        "Cladding Assemblies": ("Cladding Assy Kit", "Cladding Assy Kit Description"),
        "Finish Kits": ("Finish Kit", "Finish Kit Description")
    }
    
    choice = st.sidebar.radio("Navigation", list(categories.keys()))
    id_key, desc_key = categories[choice]

    # Populate Selection Dropdown
    sku_options = []
    if id_key in df_s.columns:
        valid_df = df_s[df_s[id_key].notna() & (df_s[id_key] != "")]
        for _, row in valid_df.drop_duplicates(subset=[id_key]).iterrows():
            sku_options.append(f"{row[id_key]} | {row.get(desc_key, 'No Description')}")

    selected = st.selectbox(f"Select {choice}", ["-- Select --"] + sorted(sku_options))

    if selected != "-- Select --":
        sel_id = selected.split(" | ")[0].strip()
        sel_desc = selected.split(" | ")[1].strip() if "|" in selected else ""

        # --- 6. BOM EXPLOSION ---
        bom_output = []
        def explode_bom(pid, depth=1, mult=1):
            if depth > 15: return # Stop infinite loops
            for comp in structure.get(pid, []):
                cid = comp['child']
                total = mult * comp['qty']
                item = master_lookup.get(cid, {})
                
                bom_output.append({
                    'Level': depth,
                    'Parent': pid,
                    'Part No.': cid,
                    'Description': item.get('Part Description', 'N/A'),
                    'Category': item.get('Category', 'N/A'),
                    'Qty': comp['qty'],
                    'Total Req': total,
                    'UOM': comp['uom'],
                    'Unit Cost': item.get('Price', 0.0),
                    'Ext. Cost': item.get('Price', 0.0) * total
                })
                explode_bom(cid, depth + 1, total)

        explode_bom(sel_id)

        if bom_output:
            final_df = pd.DataFrame(bom_output)
            st.metric("Total Roll-up Cost", f"${final_df['Ext. Cost'].sum():,.2f}")
            
            # Show Table
            df_disp = final_df.copy()
            df_disp['Unit Cost'] = df_disp['Unit Cost'].apply(lambda x: f"${x:,.2f}")
            df_disp['Ext. Cost'] = df_disp['Ext. Cost'].apply(lambda x: f"${x:,.2f}")
            st.dataframe(df_disp, use_container_width=True, hide_index=True)

            # --- 7. EXPORT ---
            header = f"Assembly Number:, {sel_id}\nDescription:, {sel_desc}\n\n"
            csv_str = header + final_df.to_csv(index=False)
            st.download_button("📥 Download Export CSV", csv_str.encode('utf-8-sig'), f"BOM_{sel_id}.csv")
        else:
            st.warning(f"No parts found for {sel_id}. Check if this ID is in the 'Parent' column of your Links file.")

except Exception as e:
    st.error(f"Something went wrong: {e}")
