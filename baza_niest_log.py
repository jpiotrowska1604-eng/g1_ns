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
    st.error("Błąd konfiguracji Secrets! Sprawdź SUPABASE_URL i SUPABASE_KEY w ustawieniach Streamlit.")
    st.stop()

st.set_page_config(page_title="Magazyn & POS PRO", layout="wide", page_icon="🏢")

# --- 2. FUNKCJE DANYCH ---
@st.cache_data(ttl=2)
def fetch_categories():
    res = supabase.table("kategorie").select("*").execute()
    return pd.DataFrame(res.data)

@st.cache_data(ttl=2)
def fetch_products():
    res = supabase.table("produkty").select("*, kategorie(nazwa)").execute()
    data = res.data
    for item in data:
        item['nazwa_kategorii'] = item['kategorie']['nazwa'] if item.get('kategorie') else "Brak"
    return pd.DataFrame(data)

# --- 3. NAPRAWIONY GENERATOR PDF ---
def create_pdf_receipt(cart, total):
    pdf = FPDF()
    pdf.add_page()
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
    pdf.cell(0, 10, f"RAZEM: {total:.2f} PLN", ln=True, align="R")
    
    # Zwracamy dane jako czyste bajty (rozwiązuje błąd bytearray)
    return bytes(pdf.output())

# --- 4. STAN SESJI ---
if 'cart' not in st.session_state:
    st.session_state.cart = []

# --- 5. MENU ---
menu = st.sidebar.radio("Nawigacja", ["📊 Dashboard", "🛒 Sprzedaż (POS)", "🍎 Magazyn", "📂 Kategorie"])

# ==========================================
# MODUŁ: DASHBOARD
# ==========================================
if menu == "📊 Dashboard":
    st.title("📊 Statystyki")
    prods = fetch_products()
    if not prods.empty:
        c1, c2, c3 = st.columns(3)
        total_v = (prods['cena'] * prods['liczba']).sum()
        c1.metric("Wartość magazynu", f"{total_v:,.2f} zł")
        c2.metric("Pozycje", len(prods))
        c3.metric("Niskie stany (<5)", len(prods[prods['liczba'] < 5]))
        st.bar_chart(prods.set_index('nazwa')['liczba'])

# ==========================================
# MODUŁ: SPRZEDAŻ (POS) - PEŁNA POPRAWKA
# ==========================================
elif menu == "🛒 Sprzedaż (POS)":
    st.title("🛒 Punkt Sprzedaży")
    prods = fetch_products()
    
    if prods.empty:
        st.warning("Dodaj produkty w zakładce Magazyn.")
    else:
        col_in, col_out = st.columns([1, 1])
        with col_in:
            st.subheader("Dodaj do koszyka")
            p_sel = st.selectbox("Produkt", prods['nazwa'].tolist())
            p_data = prods[prods['nazwa'] == p_sel].iloc[0]
            max_qty = int(p_data['liczba'])
            
            st.info(f"Stan: {max_qty} | Cena: {p_data['cena']} zł")
            qty = st.number_input("Ilość", min_value=1, max_value=max(1, max_qty), step=1)
            
            if st.button("➕ Dodaj"):
                if max_qty > 0:
                    st.session_state.cart.append({
                        "id": int(p_data['id']), "nazwa": p_sel, 
                        "cena": float(p_data['cena']), "ilosc": int(qty), 
                        "suma": float(p_data['cena'] * qty)
                    })
                    st.rerun()
                else:
                    st.error("Brak towaru!")

        with col_out:
            st.subheader("Paragon")
            if st.session_state.cart:
                df_cart = pd.DataFrame(st.session_state.cart)
                st.dataframe(df_cart[['nazwa', 'ilosc', 'suma']], use_container_width=True, hide_index=True)
                total_sum = df_cart['suma'].sum()
                st.write(f"### Suma: {total_sum:.2f} zł")
                
                if st.button("🗑️ Wyczyść koszyk"):
                    st.session_state.cart = []
                    st.rerun()
                
                if st.button("✅ FINALIZUJ I POBIERZ PDF", type="primary"):
                    try:
                        # Aktualizacja bazy danych
                        for item in st.session_state.cart:
                            res = supabase.table("produkty").select("liczba").eq("id", item['id']).execute()
                            new_val = int(res.data[0]['liczba']) - item['ilosc']
                            supabase.table("produkty").update({"liczba": new_val}).eq("id", item['id']).execute()
                        
                        # Generowanie PDF
                        pdf_data = create_pdf_receipt(st.session_state.cart, total_sum)
                        
                        st.success("Sprzedaż zakończona!")
                        st.download_button("📥 Pobierz Paragon", data=pdf_data, file_name="paragon.pdf", mime="application/pdf")
                        
                        st.session_state.cart = []
                        st.cache_data.clear()
                    except Exception as e:
                        st.error(f"Błąd transakcji: {str(e)}")
            else:
                st.info("Koszyk jest pusty.")

# ==========================================
# MODUŁ: MAGAZYN
# ==========================================
elif menu == "🍎 Magazyn":
    st.title("🍎 Zarządzanie Magazynem")
    prods = fetch_products()
    cats = fetch_categories()
    
    t1, t2 = st.tabs(["📋 Lista i Edycja", "➕ Dodaj Produkt"])
    
    with t1:
        st.write("Edytuj dane bezpośrednio w tabeli i kliknij Zapisz.")
        edited = st.data_editor(prods[['id', 'nazwa', 'liczba', 'cena', 'nazwa_kategorii']], 
                               hide_index=True, disabled=["id", "nazwa_kategorii"])
        if st.button("💾 Zapisz zmiany"):
            for _, row in edited.iterrows():
                supabase.table("produkty").update({"liczba": int(row['liczba']), "cena": float(row['cena'])}).eq("id", row['id']).execute()
            st.cache_data.clear()
            st.rerun()

    with t2:
        with st.form("new_p"):
            n = st.text_input("Nazwa")
            l = st.number_input("Ilość", min_value=0)
            c = st.number_input("Cena", min_value=0.0)
            k = st.selectbox("Kategoria", options=cats['id'].tolist(), format_func=lambda x: cats[cats['id']==x]['nazwa'].values[0])
            if st.form_submit_button("Zatwierdź"):
                supabase.table("produkty").insert({"nazwa": n, "liczba": l, "cena": c, "kategoria_id": k}).execute()
                st.cache_data.clear()
                st.rerun()

# ==========================================
# MODUŁ: KATEGORIE - POPRAWIONY
# ==========================================
elif menu == "📂 Kategorie":
    st.title("📂 Zarządzanie Kategoriami")
    cats = fetch_categories()
    
    c1, c2 = st.columns([1, 2])
    with c1:
        st.subheader("Nowa kategoria")
        with st.form("add_c", clear_on_submit=True):
            name = st.text_input("Nazwa")
            desc = st.text_area("Opis")
            if st.form_submit_button("Dodaj"):
                if name:
                    supabase.table("kategorie").insert({"nazwa": name, "opis": desc}).execute()
                    st.cache_data.clear()
                    st.rerun()
    with c2:
        st.subheader("Lista")
        st.dataframe(cats[['id', 'nazwa', 'opis']], hide_index=True, use_container_width=True)
        cat_del = st.selectbox("Usuń kategorię", cats['id'].tolist(), format_func=lambda x: cats[cats['id']==x]['nazwa'].values[0])
        if st.button("❌ Usuń"):
            try:
                supabase.table("kategorie").delete().eq("id", cat_del).execute()
                st.cache_data.clear()
                st.rerun()
            except:
                st.error("Nie można usunąć kategorii z produktami!")
