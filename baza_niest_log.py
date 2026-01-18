import streamlit as st
import pandas as pd
from supabase import create_client, Client
import io

# Konfiguracja połączenia z Supabase
url: str = st.secrets["SUPABASE_URL"]
key: str = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

st.set_page_config(page_title="Magazyn PRO", layout="wide", page_icon="📦")

# --- STYLIZACJA ---
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

# --- FUNKCJE POŁĄCZENIA ---
@st.cache_data(ttl=60)  # Odświeżaj dane co minutę lub po ręcznym restarcie
def get_categories():
    response = supabase.table("kategorie").select("*").execute()
    return pd.DataFrame(response.data)

def get_products():
    response = supabase.table("produkty").select("*, kategorie(nazwa)").execute()
    data = response.data
    # Mapowanie zagnieżdżonej nazwy kategorii na płaską kolumnę
    for item in data:
        if item.get('kategorie'):
            item['nazwa_kategorii'] = item['kategorie']['nazwa']
        else:
            item['nazwa_kategorii'] = "Brak"
    return pd.DataFrame(data)

# --- MENU BOCZNE ---
st.sidebar.title("🎮 Panel Sterowania")
page = st.sidebar.radio("Przejdź do:", ["📊 Dashboard", "🍎 Produkty", "📂 Kategorie"])

# --- MODUŁ 1: DASHBOARD ---
if page == "📊 Dashboard":
    st.title("📊 Analiza Magazynu")
    
    products_df = get_products()
    categories_df = get_categories()
    
    if not products_df.empty:
        # Metryki
        total_products = len(products_df)
        total_value = (products_df['cena'] * products_df['liczba']).sum()
        low_stock = products_df[products_df['liczba'] < 5].shape[0]
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Wszystkie Produkty", total_products)
        m2.metric("Wartość Magazynu", f"{total_value:,.2f} zł")
        m3.metric("Niski stan (<5 szt.)", low_stock, delta_color="inverse")
        
        st.divider()
        
        col_left, col_right = st.columns(2)
        with col_left:
            st.subheader("Podział wartości wg kategorii")
            # Prosty wykres słupkowy wartości
            chart_data = products_df.groupby('nazwa_kategorii').apply(lambda x: (x['cena'] * x['liczba']).sum())
            st.bar_chart(chart_data)
            
        with col_right:
            st.subheader("Produkty wymagające zamówienia")
            urgent = products_df[products_df['liczba'] < 5][['nazwa', 'liczba']]
            if not urgent.empty:
                st.warning("Uzupełnij zapasy poniższych produktów:")
                st.table(urgent)
            else:
                st.success("Wszystkie stany magazynowe są w normie.")

# --- MODUŁ 2: PRODUKTY ---
elif page == "🍎 Produkty":
    st.title("🍎 Zarządzanie Asortymentem")
    
    categories_df = get_categories()
    products_df = get_products()
    
    # Filtry i wyszukiwarka
    c1, c2, c3 = st.columns([2, 1, 1])
    search = c1.text_input("🔍 Szukaj produktu...", "")
    cat_filter = c2.selectbox("Filtruj kategorię", ["Wszystkie"] + list(categories_df['nazwa'].unique()) if not categories_df.empty else ["Wszystkie"])
    
    # Logika filtrowania
    filtered_df = products_df.copy()
    if search:
        filtered_df = filtered_df[filtered_df['nazwa'].str.contains(search, case=False)]
    if cat_filter != "Wszystkie":
        filtered_df = filtered_df[filtered_df['nazwa_kategorii'] == cat_filter]

    # Widok tabeli i operacje
    tab1, tab2 = st.tabs(["📋 Lista i Edycja", "➕ Dodaj Nowy"])
    
    with tab1:
        if not filtered_df.empty:
            # Edytowalna tabela (Streamlit Data Editor)
            st.info("Możesz edytować dane bezpośrednio w tabeli poniżej.")
            edited_df = st.data_editor(
                filtered_df[['id', 'nazwa', 'liczba', 'cena', 'nazwa_kategorii']],
                key="prod_editor",
                disabled=["id", "nazwa_kategorii"], # Blokujemy edycję ID i nazwy kategorii przez join
                hide_index=True,
                use_container_width=True
            )
            
            if st.button("Zapisz zmiany w tabeli"):
                # Logika aktualizacji zmienionych wierszy (uproszczona)
                for index, row in edited_df.iterrows():
                    supabase.table("produkty").update({
                        "nazwa": row['nazwa'],
                        "liczba": row['liczba'],
                        "cena": float(row['cena'])
                    }).eq("id", row['id']).execute()
                st.success("Zapisano zmiany!")
                st.cache_data.clear()
                st.rerun()

            # Usuwanie
            st.divider()
            del_id = st.selectbox("Wybierz produkt do usunięcia", options=filtered_df['id'].tolist(), format_func=lambda x: filtered_df[filtered_df['id']==x]['nazwa'].values[0])
            if st.button("Usuń wybrany produkt", type="primary"):
                supabase.table("produkty").delete().eq("id", del_id).execute()
                st.success("Produkt usunięty.")
                st.cache_data.clear()
                st.rerun()
            
            # Eksport do CSV
            csv = filtered_df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Pobierz listę jako CSV", data=csv, file_name="magazyn_produkty.csv", mime="text/csv")
        else:
            st.warning("Nie znaleziono produktów spełniających kryteria.")

    with tab2:
        if categories_df.empty:
            st.error("Musisz najpierw dodać kategorię!")
        else:
            with st.form("new_product"):
                n_name = st.text_input("Nazwa produktu*")
                n_count = st.number_input("Ilość", min_value=0)
                n_price = st.number_input("Cena (zł)", min_value=0.0)
                n_cat = st.selectbox("Kategoria", options=categories_df['id'].tolist(), format_func=lambda x: categories_df[categories_df['id']==x]['nazwa'].values[0])
                if st.form_submit_button("Dodaj do bazy"):
                    if n_name:
                        supabase.table("produkty").insert({"nazwa": n_name, "liczba": n_count, "cena": n_price, "kategoria_id": n_cat}).execute()
                        st.success("Dodano!")
                        st.cache_data.clear()
                        st.rerun()

# --- MODUŁ 3: KATEGORIE ---
elif page == "📂 Kategorie":
    st.title("📂 Zarządzanie Kategoriami")
    
    col_a, col_b = st.columns([1, 2])
    
    with col_a:
        st.subheader("Nowa kategoria")
        with st.form("add_cat"):
            c_name = st.text_input("Nazwa")
            c_desc = st.text_area("Opis")
            if st.form_submit_button("Dodaj"):
                if c_name:
                    supabase.table("kategorie").insert({"nazwa": c_name, "opis": c_desc}).execute()
                    st.cache_data.clear()
                    st.rerun()
                    
    with col_b:
        st.subheader("Istniejące kategorie")
        cats = get_categories()
        if not cats.empty:
            st.dataframe(cats[['nazwa', 'opis']], use_container_width=True, hide_index=True)
            
            cat_to_del = st.selectbox("Usuń kategorię", cats['id'].tolist(), format_func=lambda x: cats[cats['id']==x]['nazwa'].values[0])
            if st.button("Usuń kategorię", help="Można usunąć tylko pustą kategorię"):
                try:
                    supabase.table("kategorie").delete().eq("id", cat_to_del).execute()
                    st.cache_data.clear()
                    st.rerun()
                except:
                    st.error("Błąd: Ta kategoria zawiera produkty!")
