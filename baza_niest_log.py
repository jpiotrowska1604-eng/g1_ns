import streamlit as st
import pandas as pd
from supabase import create_client, Client
from fpdf import FPDF
from datetime import datetime
import io

# --- KONFIGURACJA SUPABASE ---
url: str = st.secrets["SUPABASE_URL"]
key: str = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

st.set_page_config(page_title="System Magazynowo-Sprzedażowy", layout="wide", page_icon="🧾")

# --- FUNKCJE BAZODANOWE ---
@st.cache_data(ttl=10)
def get_categories():
    res = supabase.table("kategorie").select("*").execute()
    return pd.DataFrame(res.data)

def get_products():
    res = supabase.table("produkty").select("*, kategorie(nazwa)").execute()
    data = res.data
    for item in data:
        item['nazwa_kategorii'] = item['kategorie']['nazwa'] if item.get('kategorie') else "Brak"
    return pd.DataFrame(data)

# --- FUNKCJA GENEROWANIA PARAGONU ---
def generate_receipt(cart_items, total_price):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "PARAGON FISKALNY (SYMULACJA)", ln=True, align="C")
    pdf.set_font("Arial", "", 10)
    pdf.cell(0, 10, f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ln=True, align="C")
    pdf.ln(10)
    
    # Nagłówki tabeli
    pdf.set_font("Arial", "B", 12)
    pdf.cell(80, 10, "Produkt", border=1)
    pdf.cell(30, 10, "Ilosc", border=1)
    pdf.cell(40, 10, "Cena jedn.", border=1)
    pdf.cell(40, 10, "Suma", border=1, ln=True)
    
    # Treść
    pdf.set_font("Arial", "", 12)
    for item in cart_items:
        suma_item = item['cena'] * item['ilosc_sprzedaz']
        pdf.cell(80, 10, item['nazwa'], border=1)
        pdf.cell(30, 10, str(item['ilosc_sprzedaz']), border=1)
        pdf.cell(40, 10, f"{item['cena']:.2f} zl", border=1)
        pdf.cell(40, 10, f"{suma_item:.2f} zl", border=1, ln=True)
    
    pdf.ln(5)
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, f"DO ZAPLATY: {total_price:.2f} zl", ln=True, align="R")
    
    return pdf.output(dest='S').encode('latin-1')

# --- INICJALIZACJA KOSZYKA ---
if 'cart' not in st.session_state:
    st.session_state.cart = []

# --- PANEL BOCZNY ---
st.sidebar.title("🏢 Menu Główne")
page = st.sidebar.radio("Przejdź do:", ["📊 Dashboard", "🛒 Sprzedaż", "🍎 Magazyn", "📂 Kategorie"])

# --- MODUŁ SPRZEDAŻY (NOWOŚĆ) ---
if page == "🛒 Sprzedaż":
    st.title("🛒 Panel Sprzedaży")
    
    products_df = get_products()
    
    col_sell, col_cart = st.columns([2, 1])
    
    with col_sell:
        st.subheader("Wybierz produkty")
        selected_prod_name = st.selectbox("Produkt", options=products_df['nazwa'].tolist())
        prod_info = products_df[products_df['nazwa'] == selected_prod_name].iloc[0]
        
        st.info(f"Dostępna ilość: **{prod_info['liczba']}** | Cena: **{prod_info['cena']} zł**")
        
        amount = st.number_input("Ilość do sprzedaży", min_value=1, max_value=int(prod_info['liczba']), step=1)
        
        if st.button("Dodaj do koszyka ➕"):
            item = {
                "id": prod_info['id'],
                "nazwa": selected_prod_name,
                "cena": float(prod_info['cena']),
                "ilosc_sprzedaz": amount
            }
            st.session_state.cart.append(item)
            st.toast(f"Dodano {selected_prod_name} do koszyka!")

    with col_cart:
        st.subheader("Twój Koszyk")
        if st.session_state.cart:
            total = 0
            for i, item in enumerate(st.session_state.cart):
                total += item['cena'] * item['ilosc_sprzedaz']
                st.write(f"{item['nazwa']} x{item['ilosc_sprzedaz']} - {item['cena']*item['ilosc_sprzedaz']:.2f} zł")
            
            st.divider()
            st.write(f"### Suma: {total:.2f} zł")
            
            if st.button("🔴 Wyczyść koszyk"):
                st.session_state.cart = []
                st.rerun()
            
            if st.button("✅ Sfinalizuj i pobierz paragon"):
                # 1. Aktualizacja bazy (zdejmij stany)
                for item in st.session_state.cart:
                    new_qty = int(products_df[products_df['id'] == item['id']]['liczba'].values[0]) - item['ilosc_sprzedaz']
                    supabase.table("produkty").update({"liczba": new_qty}).eq("id", item['id']).execute()
                
                # 2. Generowanie PDF
                pdf_data = generate_receipt(st.session_state.cart, total)
                
                st.download_button(
                    label="📥 Pobierz Paragon PDF",
                    data=pdf_data,
                    file_name=f"paragon_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                    mime="application/pdf"
                )
                
                st.success("Transakcja zakończona pomyślnie! Stany magazynowe zaktualizowane.")
                st.session_state.cart = [] # Czyścimy koszyk po sprzedaży
        else:
            st.write("Koszyk jest pusty.")

# --- RESZTA MODUŁÓW (Podobnie jak wcześniej, ale z poprawkami) ---
elif page == "📊 Dashboard":
    st.title("📊 Statystyki")
    df = get_products()
    if not df.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("Wartość towaru", f"{(df['cena'] * df['liczba']).sum():.2f} zł")
        c2.metric("Liczba pozycji", len(df))
        c3.metric("Brakujące towary", len(df[df['liczba'] == 0]))
        st.bar_chart(df.set_index('nazwa')['liczba'])

elif page == "🍎 Magazyn":
    st.title("🍎 Zarządzanie Magazynem")
    df = get_products()
    cats = get_categories()
    
    # Szybka edycja stanów
    edited_df = st.data_editor(df[['id', 'nazwa', 'liczba', 'cena', 'nazwa_kategorii']], 
                               hide_index=True, use_container_width=True, disabled=["id", "nazwa_kategorii"])
    
    if st.button("Zapisz zmiany w magazynie"):
        for _, row in edited_df.iterrows():
            supabase.table("produkty").update({"liczba": row['liczba'], "cena": row['cena']}).eq("id", row['id']).execute()
        st.success("Zaktualizowano dane!")
        st.cache_data.clear()

    st.divider()
    with st.expander("➕ Dodaj nowy produkt"):
        with st.form("new_p"):
            n = st.text_input("Nazwa")
            l = st.number_input("Ilość", min_value=0)
            c = st.number_input("Cena", min_value=0.0)
            k = st.selectbox("Kategoria", options=cats['id'].tolist(), format_func=lambda x: cats[cats['id']==x]['nazwa'].values[0])
            if st.form_submit_button("Dodaj"):
                supabase.table("produkty").insert({"nazwa": n, "liczba": l, "cena": c, "kategoria_id": k}).execute()
                st.cache_data.clear()
                st.rerun()

elif page == "📂 Kategorie":
    st.title("📂 Kategorie")
    # Tutaj zostaje kod z poprzedniej wersji (dodawanie/usuwanie kategorii)
    # ...
