import streamlit as st
import pandas as pd
from supabase import create_client, Client
from fpdf import FPDF
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go

# --- 1. KONFIGURACJA ---
url: str = st.secrets["SUPABASE_URL"]
key: str = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

st.set_page_config(page_title="Magazyn PRO + Analityka", layout="wide", page_icon="📈")

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

@st.cache_data(ttl=2)
def fetch_sales_history():
    res = supabase.table("sprzedaz").select("*").execute()
    df = pd.DataFrame(res.data)
    if not df.empty:
        df['created_at'] = pd.to_datetime(df['created_at'])
    return df

# --- 3. GENERATOR PDF ---
def create_pdf_receipt(cart, total):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 10, "POTWIERDZENIE SPRZEDAZY", ln=True, align="C")
    pdf.set_font("helvetica", "", 10)
    pdf.cell(0, 10, f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ln=True, align="C")
    pdf.ln(10)
    pdf.set_font("helvetica", "B", 11)
    pdf.cell(80, 10, "Produkt", 1); pdf.cell(25, 10, "Ilosc", 1); pdf.cell(35, 10, "Cena", 1); pdf.cell(40, 10, "Suma", 1, ln=True)
    pdf.set_font("helvetica", "", 11)
    for item in cart:
        pdf.cell(80, 10, str(item['nazwa']), 1)
        pdf.cell(25, 10, str(item['ilosc']), 1)
        pdf.cell(35, 10, f"{item['cena']:.2f}", 1)
        pdf.cell(40, 10, f"{item['suma']:.2f}", 1, ln=True)
    pdf.ln(5)
    pdf.set_font("helvetica", "B", 14)
    pdf.cell(0, 10, f"RAZEM: {total:.2f} PLN", ln=True, align="R")
    return bytes(pdf.output())

# --- 4. STAN SESJI ---
if 'cart' not in st.session_state:
    st.session_state.cart = []

# --- 5. MENU ---
menu = st.sidebar.radio("Nawigacja", ["📊 Dashboard", "🛒 Sprzedaż (POS)", "🍎 Magazyn", "📂 Kategorie"])

# ==========================================
# MODUŁ: DASHBOARD (ROZBUDOWANY)
# ==========================================
if menu == "📊 Dashboard":
    st.title("📊 Analityka i Statystyki")
    
    prods = fetch_products()
    sales = fetch_sales_history()
    
    if sales.empty:
        st.info("Brak danych o sprzedaży. Sfinalizuj pierwszą transakcję, aby zobaczyć statystyki.")
    else:
        # --- METRYKI GŁÓWNE ---
        c1, c2, c3, c4 = st.columns(4)
        total_revenue = sales['suma'].sum()
        total_items_sold = sales['ilosc'].sum()
        avg_order = sales.groupby('created_at')['suma'].sum().mean()
        inventory_val = (prods['cena'] * prods['liczba']).sum()

        c1.metric("Przychód Całkowity", f"{total_revenue:,.2f} zł")
        c2.metric("Sprzedane Produkty", f"{total_items_sold} szt.")
        c3.metric("Średnia Transakcja", f"{avg_order:.2f} zł")
        c4.metric("Wartość Magazynu", f"{inventory_val:,.2f} zł")

        st.divider()

        # --- WYKRESY ---
        col_charts_1, col_charts_2 = st.columns(2)

        with col_charts_1:
            st.subheader("📈 Sprzedaż w czasie")
            # Grupowanie po dacie (dzień)
            sales_daily = sales.copy()
            sales_daily['data'] = sales_daily['created_at'].dt.date
            daily_chart = sales_daily.groupby('data')['suma'].sum().reset_index()
            fig_line = px.line(daily_chart, x='data', y='suma', title="Dzienny Przychód", labels={'suma':'Suma (zł)', 'data':'Data'})
            st.plotly_chart(fig_line, use_container_width=True)

        with col_charts_2:
            st.subheader("🏆 Najlepiej sprzedające się produkty")
            top_products = sales.groupby('nazwa_produktu')['ilosc'].sum().sort_values(ascending=False).head(10).reset_index()
            fig_bar = px.bar(top_products, x='ilosc', y='nazwa_produktu', orientation='h', title="Top 10 Produktów (Ilościowo)", color='ilosc')
            st.plotly_chart(fig_bar, use_container_width=True)

        col_charts_3, col_charts_4 = st.columns(2)

        with col_charts_3:
            st.subheader("📦 Struktura Magazynu (Kategorie)")
            fig_pie = px.pie(prods, names='nazwa_kategorii', values='liczba', title="Udział kategorii w magazynie", hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)

        with col_charts_4:
            st.subheader("⚠️ Alert Niskiego Stanu")
            low_stock = prods[prods['liczba'] < 5][['nazwa', 'liczba']].sort_values(by='liczba')
            if not low_stock.empty:
                st.dataframe(low_stock, use_container_width=True, hide_index=True)
            else:
                st.success("Wszystkie stany są optymalne!")

# ==========================================
# MODUŁ: SPRZEDAŻ (Z ZAPISEM HISTORII)
# ==========================================
elif menu == "🛒 Sprzedaż (POS)":
    st.title("🛒 Punkt Sprzedaży")
    prods = fetch_products()
    
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
            
            if st.button("✅ FINALIZUJ", type="primary"):
                try:
                    for item in st.session_state.cart:
                        # 1. Zapis do historii sprzedaży (NOWOŚĆ)
                        supabase.table("sprzedaz").insert({
                            "produkt_id": item['id'],
                            "nazwa_produktu": item['nazwa'],
                            "ilosc": item['ilosc'],
                            "cena_sprzedazy": item['cena'],
                            "suma": item['suma']
                        }).execute()

                        # 2. Aktualizacja magazynu
                        res = supabase.table("produkty").select("liczba").eq("id", item['id']).execute()
                        new_val = int(res.data[0]['liczba']) - item['ilosc']
                        supabase.table("produkty").update({"liczba": new_val}).eq("id", item['id']).execute()
                    
                    pdf_data = create_pdf_receipt(st.session_state.cart, total_sum)
                    st.success("Sprzedaż zapisana i dodana do historii!")
                    st.download_button("📥 Pobierz Paragon", data=pdf_data, file_name="paragon.pdf", mime="application/pdf")
                    
                    st.session_state.cart = []
                    st.cache_data.clear()
                except Exception as e:
                    st.error(f"Błąd transakcji: {str(e)}")
        else:
            st.info("Koszyk jest pusty.")

# --- MODUŁY MAGAZYN I KATEGORIE ZOSTAJĄ BEZ ZMIAN (JAK W POPRZEDNIM KODZIE) ---
# ... (Tutaj wstaw sekcje 🍎 Magazyn i 📂 Kategorie z poprzedniego kodu)
