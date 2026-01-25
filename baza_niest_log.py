import streamlit as st
import pandas as pd
from supabase import create_client, Client
from fpdf import FPDF
from datetime import datetime
import plotly.express as px
import io

# --- FUNKCJA NAPRAWIAJĄCA POLSKIE ZNAKI DLA PDF ---
def remove_polish_chars(text):
    """Zamienia polskie znaki na ich łacińskie odpowiedniki dla podstawowych czcionek PDF."""
    chars = {
        'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n', 'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z',
        'Ą': 'A', 'Ć': 'C', 'Ę': 'E', 'Ł': 'L', 'Ń': 'N', 'Ó': 'O', 'Ś': 'S', 'Ź': 'Z', 'Ż': 'Z'
    }
    for pol, lat in chars.items():
        text = text.replace(pol, lat)
    return text

# --- 1. KONFIGURACJA POŁĄCZENIA ---
try:
    url: str = st.secrets["SUPABASE_URL"]
    key: str = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)
except Exception as e:
    st.error("Błąd konfiguracji Secrets! Sprawdź SUPABASE_URL i SUPABASE_KEY.")
    st.stop()

st.set_page_config(page_title="Magazyn PRO & Analityka", layout="wide", page_icon="📈")

# --- 2. FUNKCJE POBIERANIA DANYCH ---
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

@st.cache_data(ttl=2)
def fetch_sales_history():
    try:
        res = supabase.table("sprzedaz").select("*").execute()
        df = pd.DataFrame(res.data)
        if not df.empty:
            df['created_at'] = pd.to_datetime(df['created_at'])
        return df
    except:
        return pd.DataFrame()

# --- 3. GENERATOR PDF (NAPRAWIONY - BEZ POLSKICH ZNAKÓW) ---
def create_pdf_receipt(cart, total):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", "B", 16)
    
    # Nagłówek (oczyszczony)
    title = remove_polish_chars("POTWIERDZENIE SPRZEDAZY")
    pdf.cell(0, 10, title, ln=True, align="C")
    
    pdf.set_font("helvetica", "", 10)
    pdf.cell(0, 10, f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ln=True, align="C")
    pdf.ln(10)
    
    # Nagłówki tabeli (oczyszczone)
    pdf.set_font("helvetica", "B", 11)
    pdf.cell(80, 10, "Produkt", 1)
    pdf.cell(25, 10, "Ilosc", 1)
    pdf.cell(35, 10, "Cena", 1)
    pdf.cell(40, 10, "Suma", 1, ln=True)
    
    # Pozycje (oczyszczone)
    pdf.set_font("helvetica", "", 11)
    for item in cart:
        clean_name = remove_polish_chars(str(item['nazwa']))
        pdf.cell(80, 10, clean_name, 1)
        pdf.cell(25, 10, str(item['ilosc']), 1)
        pdf.cell(35, 10, f"{item['cena']:.2f}", 1)
        pdf.cell(40, 10, f"{item['suma']:.2f}", 1, ln=True)
    
    pdf.ln(5)
    pdf.set_font("helvetica", "B", 14)
    footer = remove_polish_chars(f"RAZEM: {total:.2f} PLN")
    pdf.cell(0, 10, footer, ln=True, align="R")
    
    return bytes(pdf.output())

# --- 4. STAN SESJI ---
if 'cart' not in st.session_state:
    st.session_state.cart = []

# --- 5. MENU BOCZNE ---
st.sidebar.title("Zarządzanie Sklepem")
menu = st.sidebar.radio("Nawigacja", ["📊 Dashboard", "🛒 Sprzedaż (POS)", "🍎 Magazyn", "📂 Kategorie"])

# ==========================================
# MODUŁ: DASHBOARD
# ==========================================
if menu == "📊 Dashboard":
    st.title("📊 Analityka i Statystyki")
    prods = fetch_products()
    sales = fetch_sales_history()
    
    if sales.empty:
        st.info("Brak danych o sprzedaży w tabeli 'sprzedaz'. Dokonaj pierwszej sprzedaży!")
    else:
        c1, c2, c3, c4 = st.columns(4)
        total_rev = sales['suma'].sum()
        total_qty = sales['ilosc'].sum()
        inventory_v = (prods['cena'] * prods['liczba']).sum() if not prods.empty else 0
        low_stock_count = len(prods[prods['liczba'] < 5]) if not prods.empty else 0

        c1.metric("Przychód całkowity", f"{total_rev:,.2f} zł")
        c2.metric("Sprzedane sztuki", f"{total_qty} szt.")
        c3.metric("Wartość magazynu", f"{inventory_v:,.2f} zł")
        c4.metric("Niskie stany (<5)", low_stock_count)

        st.divider()
        col_a, col_b = st.columns(2)

        with col_a:
            st.subheader("📈 Wykres sprzedaży dziennej")
            daily = sales.copy()
            daily['data'] = daily['created_at'].dt.date
            daily_chart = daily.groupby('data')['suma'].sum().reset_index()
            fig1 = px.line(daily_chart, x='data', y='suma', markers=True)
            st.plotly_chart(fig1, use_container_width=True)

        with col_b:
            st.subheader("🏆 Top 5 Produktów")
            top = sales.groupby('nazwa_produktu')['ilosc'].sum().sort_values(ascending=False).head(5).reset_index()
            fig2 = px.bar(top, x='ilosc', y='nazwa_produktu', orientation='h', color='ilosc')
            st.plotly_chart(fig2, use_container_width=True)

# ==========================================
# MODUŁ: SPRZEDAŻ (POS)
# ==========================================
elif menu == "🛒 Sprzedaż (POS)":
    st.title("🛒 Punkt Sprzedaży")
    prods = fetch_products()
    
    if prods.empty:
        st.warning("Najpierw dodaj produkty w zakładce Magazyn.")
    else:
        col_l, col_r = st.columns([1, 1])
        with col_l:
            st.subheader("Wybierz produkty")
            p_sel = st.selectbox("Produkt", prods['nazwa'].tolist())
            p_data = prods[prods['nazwa'] == p_sel].iloc[0]
            curr_stock = int(p_data['liczba'])
            
            st.info(f"Dostępne: {curr_stock} | Cena: {p_data['cena']} zł")
            qty = st.number_input("Ilość", min_value=1, max_value=max(1, curr_stock), step=1)
            
            if st.button("➕ Dodaj do koszyka"):
                if curr_stock >= qty:
                    st.session_state.cart.append({
                        "id": int(p_data['id']), "nazwa": p_sel, 
                        "cena": float(p_data['cena']), "ilosc": int(qty), 
                        "suma": float(p_data['cena'] * qty)
                    })
                    st.rerun()
                else:
                    st.error("Brak wystarczającej ilości!")

        with col_r:
            st.subheader("Koszyk / Paragon")
            if st.session_state.cart:
                df_cart = pd.DataFrame(st.session_state.cart)
                st.dataframe(df_cart[['nazwa', 'ilosc', 'suma']], use_container_width=True, hide_index=True)
                total_sum = df_cart['suma'].sum()
                st.write(f"### Suma: {total_sum:.2f} zł")
                
                if st.button("🗑️ Wyczyść"):
                    st.session_state.cart = []
                    st.rerun()
                
                if st.button("✅ FINALIZUJ SPRZEDAŻ", type="primary"):
                    try:
                        for item in st.session_state.cart:
                            # 1. Zapis historii
                            supabase.table("sprzedaz").insert({
                                "produkt_id": item['id'], "nazwa_produktu": item['nazwa'],
                                "ilosc": item['ilosc'], "cena_sprzedazy": item['cena'], "suma": item['suma']
                            }).execute()
                            # 2. Aktualizacja magazynu
                            db_p = supabase.table("produkty").select("liczba").eq("id", item['id']).execute()
                            new_val = int(db_p.data[0]['liczba']) - item['ilosc']
                            supabase.table("produkty").update({"liczba": new_val}).eq("id", item['id']).execute()
                        
                        pdf_receipt = create_pdf_receipt(st.session_state.cart, total_sum)
                        st.success("Transakcja pomyślna!")
                        st.download_button("📥 Pobierz Paragon PDF", data=pdf_receipt, file_name="paragon.pdf", mime="application/pdf")
                        st.session_state.cart = []
                        st.cache_data.clear()
                    except Exception as e:
                        st.error(f"Błąd: {e}")
            else:
                st.info("Koszyk jest pusty.")

# ==========================================
# MODUŁ: MAGAZYN
# ==========================================
elif menu == "🍎 Magazyn":
    st.title("🍎 Magazyn")
    prods = fetch_products()
    cats = fetch_categories()
    
    t1, t2 = st.tabs(["📋 Lista i Edycja", "🆕 Dodaj Produkt"])
    with t1:
        st.info("Edytuj Ilość lub Cenę i kliknij przycisk Zapisz.")
        edited = st.data_editor(prods[['id', 'nazwa', 'liczba', 'cena', 'nazwa_kategorii']], 
                               hide_index=True, disabled=["id", "nazwa_kategorii"])
        if st.button("💾 Zapisz zmiany w magazynie"):
            for _, row in edited.iterrows():
                supabase.table("produkty").update({"liczba": int(row['liczba']), "cena": float(row['cena'])}).eq("id", row['id']).execute()
            st.cache_data.clear()
            st.rerun()
    with t2:
        if cats.empty:
            st.error("Najpierw dodaj kategorię!")
        else:
            with st.form("new_p"):
                n = st.text_input("Nazwa")
                l = st.number_input("Ilość", min_value=0)
                c = st.number_input("Cena", min_value=0.0)
                k = st.selectbox("Kategoria", options=cats['id'].tolist(), format_func=lambda x: cats[cats['id']==x]['nazwa'].values[0])
                if st.form_submit_button("Dodaj do bazy"):
                    if n:
                        supabase.table("produkty").insert({"nazwa": n, "liczba": l, "cena": c, "kategoria_id": k}).execute()
                        st.cache_data.clear()
                        st.rerun()

# ==========================================
# MODUŁ: KATEGORIE
# ==========================================
elif menu == "📂 Kategorie":
    st.title("📂 Kategorie")
    cats = fetch_categories()
    c_l, c_r = st.columns([1, 2])
    with c_l:
        st.subheader("Dodaj nową")
        with st.form("add_c", clear_on_submit=True):
            name = st.text_input("Nazwa")
            desc = st.text_area("Opis")
            if st.form_submit_button("Zapisz kategorię"):
                if name:
                    supabase.table("kategorie").insert({"nazwa": name, "opis": desc}).execute()
                    st.cache_data.clear()
                    st.rerun()
    with c_r:
        st.subheader("Istniejące kategorie")
        st.dataframe(cats[['id', 'nazwa', 'opis']], hide_index=True, use_container_width=True)
        if not cats.empty:
            cat_id = st.selectbox("Usuń kategorię", cats['id'].tolist(), format_func=lambda x: cats[cats['id']==x]['nazwa'].values[0])
            if st.button("❌ Usuń"):
                try:
                    supabase.table("kategorie").delete().eq("id", cat_id).execute()
                    st.cache_data.clear()
                    st.rerun()
                except:
                    st.error("Nie można usunąć kategorii, która zawiera produkty!")
