import streamlit as st
import pandas as pd
from supabase import create_client, Client
from fpdf import FPDF
from datetime import datetime
import io

# --- KONFIGURACJA ---
url: str = st.secrets["SUPABASE_URL"]
key: str = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

st.set_page_config(page_title="Magazyn & POS PRO", layout="wide", page_icon="🏢")

# --- FUNKCJE POBIERANIA DANYCH (Z NAPRAWIONYM CACHE) ---
@st.cache_data(ttl=5) # Odświeżanie co 5 sekund dla płynności
def fetch_categories():
    res = supabase.table("kategorie").select("*").execute()
    return pd.DataFrame(res.data)

@st.cache_data(ttl=5)
def fetch_products():
    res = supabase.table("produkty").select("*, kategorie(nazwa)").execute()
    data = res.data
    for item in data:
        item['nazwa_kategorii'] = item['kategorie']['nazwa'] if item.get('kategorie') else "Brak"
    return pd.DataFrame(data)

# --- GENERATOR PARAGONÓW (PDF) ---
def create_pdf_receipt(cart, total):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 10, "POTWIERDZENIE SPRZEDAZY", ln=True, align="C")
    pdf.set_font("helvetica", "", 10)
    pdf.cell(0, 10, f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ln=True, align="C")
    pdf.ln(10)
    
    # Nagłówki
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(90, 10, "Produkt", 1)
    pdf.cell(30, 10, "Ilosc", 1)
    pdf.cell(30, 10, "Cena", 1)
    pdf.cell(40, 10, "Suma", 1, ln=True)
    
    pdf.set_font("helvetica", "", 12)
    for item in cart:
        pdf.cell(90, 10, str(item['nazwa']), 1)
        pdf.cell(30, 10, str(item['ilosc']), 1)
        pdf.cell(30, 10, f"{item['cena']:.2f}", 1)
        pdf.cell(40, 10, f"{item['suma']:.2f}", 1, ln=True)
    
    pdf.ln(5)
    pdf.set_font("helvetica", "B", 14)
    pdf.cell(0, 10, f"RAZEM: {total:.2f} PLN", ln=True, align="R")
    return pdf.output()

# --- STAN SESJI (KOSZYK) ---
if 'cart' not in st.session_state:
    st.session_state.cart = []

# --- MENU ---
menu = st.sidebar.radio("Nawigacja", ["📊 Dashboard", "🛒 Sprzedaż (POS)", "🍎 Magazyn", "📂 Kategorie"])

# ==========================================
# MODUŁ: DASHBOARD
# ==========================================
if menu == "📊 Dashboard":
    st.title("📊 Analiza Biznesowa")
    prods = fetch_products()
    if not prods.empty:
        c1, c2, c3, c4 = st.columns(4)
        total_val = (prods['cena'] * prods['liczba']).sum()
        c1.metric("Wartość magazynu", f"{total_val:,.2f} zł")
        c2.metric("Liczba produktów", len(prods))
        c3.metric("Niskie stany (<5)", len(prods[prods['liczba'] < 5]))
        c4.metric("Brak na stanie", len(prods[prods['liczba'] == 0]))
        
        st.subheader("Stan magazynowy (wykres)")
        st.bar_chart(prods.set_index('nazwa')['liczba'])

# ==========================================
# MODUŁ: SPRZEDAŻ (POS)
# ==========================================
elif menu == "🛒 Sprzedaż (POS)":
    st.title("🛒 Punkt Sprzedaży")
    prods = fetch_products()
    
    col_in, col_out = st.columns([1, 1])
    
    with col_in:
        st.subheader("Dodaj do paragonu")
        p_sel = st.selectbox("Wybierz produkt", prods['nazwa'].tolist())
        p_data = prods[prods['nazwa'] == p_sel].iloc[0]
        
        st.write(f"Dostępne: {p_data['liczba']} | Cena: {p_data['cena']} zł")
        qty = st.number_input("Ilość", min_value=1, max_value=int(p_data['liczba']) if p_data['liczba'] > 0 else 1)
        
        if st.button("➕ Dodaj"):
            if p_data['liczba'] >= qty:
                st.session_state.cart.append({
                    "id": p_data['id'], "nazwa": p_sel, "cena": float(p_data['cena']), 
                    "ilosc": qty, "suma": float(p_data['cena'] * qty)
                })
                st.toast("Dodano do koszyka")
            else:
                st.error("Brak wystarczającej ilości!")

    with col_out:
        st.subheader("Paragon")
        if st.session_state.cart:
            cart_df = pd.DataFrame(st.session_state.cart)
            st.table(cart_df[['nazwa', 'ilosc', 'suma']])
            razem = cart_df['suma'].sum()
            st.write(f"### Razem: {razem:.2f} zł")
            
            if st.button("🔥 Wyczyść"):
                st.session_state.cart = []
                st.rerun()
                
            if st.button("✅ Finalizuj Sprzedaż"):
                # Aktualizacja bazy
                for item in st.session_state.cart:
                    new_qty = int(prods[prods['id'] == item['id']]['liczba'].values[0]) - item['ilosc']
                    supabase.table("produkty").update({"liczba": new_qty}).eq("id", item['id']).execute()
                
                # Generowanie PDF
                pdf_bytes = create_pdf_receipt(st.session_state.cart, razem)
                st.download_button("📥 Pobierz Paragon PDF", data=pdf_bytes, file_name="paragon.pdf", mime="application/pdf")
                
                st.session_state.cart = []
                st.success("Sprzedano i zaktualizowano magazyn!")
                st.cache_data.clear()

# ==========================================
# MODUŁ: MAGAZYN
# ==========================================
elif menu == "🍎 Magazyn":
    st.title("🍎 Zarządzanie Towarem")
    prods = fetch_products()
    cats = fetch_categories()
    
    st.subheader("Szybka edycja")
    edited = st.data_editor(prods[['id', 'nazwa', 'liczba', 'cena', 'nazwa_kategorii']], hide_index=True, disabled=["id", "nazwa_kategorii"])
    
    if st.button("💾 Zapisz zmiany"):
        for i, row in edited.iterrows():
            supabase.table("produkty").update({"liczba": row['liczba'], "cena": row['cena']}).eq("id", row['id']).execute()
        st.success("Zapisano!")
        st.cache_data.clear()
        st.rerun()

    with st.expander("🆕 Dodaj nowy produkt"):
        with st.form("new_p_form"):
            name = st.text_input("Nazwa")
            stock = st.number_input("Ilość początkowa", min_value=0)
            price = st.number_input("Cena", min_value=0.0)
            c_id = st.selectbox("Kategoria", options=cats['id'].tolist(), format_func=lambda x: cats[cats['id']==x]['nazwa'].values[0])
            if st.form_submit_button("Dodaj produkt"):
                supabase.table("produkty").insert({"nazwa": name, "liczba": stock, "cena": price, "kategoria_id": c_id}).execute()
                st.cache_data.clear()
                st.rerun()

# ==========================================
# MODUŁ: KATEGORIE (NAPRAWIONY)
# ==========================================
elif menu == "📂 Kategorie":
    st.title("📂 Zarządzanie Kategoriami")
    cats = fetch_categories()
    
    col_left, col_right = st.columns([1, 2])
    
    with col_left:
        st.subheader("Dodaj kategorię")
        with st.form("add_cat_fixed", clear_on_submit=True):
            cat_n = st.text_input("Nazwa kategorii")
            cat_o = st.text_area("Opis")
            if st.form_submit_button("Zatwierdź"):
                if cat_n:
                    supabase.table("kategorie").insert({"nazwa": cat_n, "opis": cat_o}).execute()
                    st.success(f"Dodano: {cat_n}")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.warning("Podaj nazwę!")

    with col_right:
        st.subheader("Lista kategorii")
        if not cats.empty:
            st.dataframe(cats[['id', 'nazwa', 'opis']], use_container_width=True, hide_index=True)
            
            st.divider()
            st.subheader("Usuwanie")
            cat_to_del = st.selectbox("Wybierz do usunięcia", cats['id'].tolist(), format_func=lambda x: cats[cats['id']==x]['nazwa'].values[0])
            if st.button("❌ Usuń wybraną kategorię"):
                try:
                    supabase.table("kategorie").delete().eq("id", cat_to_del).execute()
                    st.success("Usunięto!")
                    st.cache_data.clear()
                    st.rerun()
                except:
                    st.error("Błąd: Nie można usunąć kategorii, która ma przypisane produkty!")
        else:
            st.info("Brak kategorii. Dodaj pierwszą po lewej stronie.")
