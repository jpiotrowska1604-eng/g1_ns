import streamlit as st
import pandas as pd
from supabase import create_client, Client
from fpdf import FPDF
from datetime import datetime
import io

# --- 1. KONFIGURACJA POŁĄCZENIA ---
try:
    url: str = st.secrets["SUPABASE_URL"]
    key: str = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)
except Exception as e:
    st.error("Błąd konfiguracji Secrets! Upewnij się, że podałeś SUPABASE_URL i SUPABASE_KEY.")
    st.stop()

st.set_page_config(page_title="Magazyn & Sprzedaż PRO", layout="wide", page_icon="🏢")

# --- 2. FUNKCJE DANYCH (Z CACHE) ---
@st.cache_data(ttl=5)
def fetch_categories():
    res = supabase.table("kategorie").select("*").execute()
    return pd.DataFrame(res.data)

@st.cache_data(ttl=5)
def fetch_products():
    res = supabase.table("produkty").select("*, kategorie(nazwa)").execute()
    data = res.data
    for item in data:
        # Płaskie mapowanie nazwy kategorii dla łatwiejszego filtrowania
        item['nazwa_kategorii'] = item['kategorie']['nazwa'] if item.get('kategorie') else "Brak"
    return pd.DataFrame(data)

# --- 3. GENERATOR PDF ---
def create_pdf_receipt(cart, total):
    pdf = FPDF()
    pdf.add_page()
    # fpdf2 używa standardowych fontów, jeśli nie dodasz własnych .ttf (obsługa polskich znaków wymaga dodania fontu)
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 10, "POTWIERDZENIE SPRZEDAZY", ln=True, align="C")
    pdf.set_font("helvetica", "", 10)
    pdf.cell(0, 10, f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ln=True, align="C")
    pdf.ln(10)
    
    # Nagłówki
    pdf.set_font("helvetica", "B", 11)
    pdf.cell(80, 10, "Produkt", 1)
    pdf.cell(25, 10, "Ilosc", 1)
    pdf.cell(35, 10, "Cena jedn.", 1)
    pdf.cell(40, 10, "Suma", 1, ln=True)
    
    # Pozycje
    pdf.set_font("helvetica", "", 11)
    for item in cart:
        pdf.cell(80, 10, str(item['nazwa']), 1)
        pdf.cell(25, 10, str(item['ilosc']), 1)
        pdf.cell(35, 10, f"{item['cena']:.2f}", 1)
        pdf.cell(40, 10, f"{item['suma']:.2f}", 1, ln=True)
    
    pdf.ln(5)
    pdf.set_font("helvetica", "B", 14)
    pdf.cell(0, 10, f"DO ZAPLATY: {total:.2f} PLN", ln=True, align="R")
    return pdf.output()

# --- 4. STAN SESJI (KOSZYK) ---
if 'cart' not in st.session_state:
    st.session_state.cart = []

# --- 5. NAWIGACJA ---
menu = st.sidebar.radio("Menu Główne", ["📊 Dashboard", "🛒 Sprzedaż (POS)", "🍎 Magazyn", "📂 Kategorie"])

# ==========================================
# MODUŁ: DASHBOARD
# ==========================================
if menu == "📊 Dashboard":
    st.title("📊 Statystyki Magazynowe")
    prods = fetch_products()
    
    if not prods.empty:
        c1, c2, c3 = st.columns(3)
        total_value = (prods['cena'] * prods['liczba']).sum()
        c1.metric("Wartość magazynu", f"{total_value:,.2f} zł")
        c2.metric("Liczba produktów", len(prods))
        c3.metric("Niskie stany (<5)", len(prods[prods['liczba'] < 5]))
        
        st.subheader("Ilość towarów na stanie")
        st.bar_chart(prods.set_index('nazwa')['liczba'])
    else:
        st.info("Baza danych jest pusta. Dodaj produkty w zakładce Magazyn.")

# ==========================================
# MODUŁ: SPRZEDAŻ (POS)
# ==========================================
elif menu == "🛒 Sprzedaż (POS)":
    st.title("🛒 Punkt Sprzedaży")
    prods = fetch_products()
    
    if prods.empty:
        st.warning("Najpierw dodaj produkty do magazynu!")
    else:
        col_in, col_out = st.columns([1, 1])
        
        with col_in:
            st.subheader("Wybierz produkt")
            p_sel = st.selectbox("Produkt", prods['nazwa'].tolist())
            p_data = prods[prods['nazwa'] == p_sel].iloc[0]
            
            # Wymuszamy typ int dla bezpieczeństwa obliczeń
            current_stock = int(p_data['liczba'])
            
            st.info(f"Stan: {current_stock} | Cena: {p_data['cena']} zł")
            
            qty = st.number_input("Sztuk", min_value=1, max_value=max(1, current_stock), step=1)
            
            if st.button("➕ Dodaj do paragonu"):
                if current_stock <= 0:
                    st.error("Brak produktu na stanie!")
                else:
                    st.session_state.cart.append({
                        "id": int(p_data['id']), 
                        "nazwa": p_sel, 
                        "cena": float(p_data['cena']), 
                        "ilosc": int(qty), 
                        "suma": float(p_data['cena'] * qty)
                    })
                    st.toast(f"Dodano {p_sel}")

        with col_out:
            st.subheader("Paragon")
            if st.session_state.cart:
                cart_df = pd.DataFrame(st.session_state.cart)
                st.dataframe(cart_df[['nazwa', 'ilosc', 'suma']], hide_index=True, use_container_width=True)
                total_sum = cart_df['suma'].sum()
                st.write(f"### Razem: {total_sum:.2f} zł")
                
                c_del, c_fin = st.columns(2)
                if c_del.button("🗑️ Wyczyść", use_container_width=True):
                    st.session_state.cart = []
                    st.rerun()
                
                if c_fin.button("✅ FINALIZUJ", type="primary", use_container_width=True):
                    try:
                        for item in st.session_state.cart:
                            # 1. Pobierz aktualny stan z bazy (świeży)
                            db_res = supabase.table("produkty").select("liczba").eq("id", item['id']).execute()
                            stock_now = int(db_res.data[0]['liczba'])
                            
                            # 2. Oblicz i zaktualizuj
                            new_val = stock_now - item['ilosc']
                            supabase.table("produkty").update({"liczba": new_val}).eq("id", item['id']).execute()
                        
                        # 3. Generuj PDF
                        receipt_pdf = create_pdf_receipt(st.session_state.cart, total_sum)
                        
                        st.success("Transakcja zakończona!")
                        st.download_button("📥 Pobierz Paragon PDF", data=receipt_pdf, file_name="paragon.pdf", mime="application/pdf")
                        
                        st.session_state.cart = []
                        st.cache_data.clear()
                    except Exception as e:
                        st.error(f"Błąd transakcji: {e}")
            else:
                st.info("Koszyk jest pusty.")

# ==========================================
# MODUŁ: MAGAZYN
# ==========================================
elif menu == "🍎 Magazyn":
    st.title("🍎 Zarządzanie Magazynem")
    prods = fetch_products()
    cats = fetch_categories()
    
    tab_list, tab_add = st.tabs(["📋 Lista i Edycja", "🆕 Nowy Produkt"])
    
    with tab_list:
        st.info("Kliknij w komórkę 'liczba' lub 'cena', aby szybko edytować i kliknij Zapisz poniżej.")
        edited = st.data_editor(prods[['id', 'nazwa', 'liczba', 'cena', 'nazwa_kategorii']], 
                                hide_index=True, disabled=["id", "nazwa_kategorii"], use_container_width=True)
        
        if st.button("💾 Zapisz zmiany w bazie"):
            for _, row in edited.iterrows():
                supabase.table("produkty").update({"liczba": int(row['liczba']), "cena": float(row['cena'])}).eq("id", row['id']).execute()
            st.success("Zaktualizowano magazyn!")
            st.cache_data.clear()
            st.rerun()

    with tab_add:
        if cats.empty:
            st.error("Najpierw musisz dodać kategorię!")
        else:
            with st.form("new_product_form"):
                n = st.text_input("Nazwa produktu")
                l = st.number_input("Ilość", min_value=0)
                c = st.number_input("Cena", min_value=0.0)
                k = st.selectbox("Kategoria", options=cats['id'].tolist(), format_func=lambda x: cats[cats['id']==x]['nazwa'].values[0])
                if st.form_submit_button("Dodaj produkt"):
                    if n:
                        supabase.table("produkty").insert({"nazwa": n, "liczba": l, "cena": c, "kategoria_id": k}).execute()
                        st.success("Dodano produkt!")
                        st.cache_data.clear()
                        st.rerun()

# ==========================================
# MODUŁ: KATEGORIE (PEŁNY I POPRAWIONY)
# ==========================================
elif menu == "📂 Kategorie":
    st.title("📂 Zarządzanie Kategoriami")
    cats = fetch_categories()
    
    c_add, c_list = st.columns([1, 2])
    
    with c_add:
        st.subheader("Nowa kategoria")
        with st.form("form_category", clear_on_submit=True):
            new_cat_name = st.text_input("Nazwa")
