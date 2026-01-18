import streamlit as st
from supabase import create_client, Client

# Konfiguracja połączenia z Supabase
# Dane zostaną pobrane ze Streamlit Secrets po wdrożeniu
url: str = st.secrets["SUPABASE_URL"]
key: str = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

st.set_page_config(page_title="Zarządzanie Magazynem", layout="wide")

st.title("📦 System Zarządzania Produktami")

# --- NAWIGACJA W SIDEBARZE ---
choice = st.sidebar.selectbox("Menu", ["Produkty", "Kategorie"])

# --- FUNKCJE POMOCNICZE ---
def get_categories():
    response = supabase.table("kategorie").select("*").execute()
    return response.data

def get_products():
    # Pobieramy produkty wraz z nazwą kategorii (join)
    response = supabase.table("produkty").select("*, kategorie(nazwa)").execute()
    return response.data

# --- MODUŁ KATEGORIE ---
if choice == "Kategorie":
    st.header("📂 Zarządzanie Kategoriami")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("Dodaj kategorię")
        with st.form("add_category_form", clear_on_submit=True):
            cat_name = st.text_input("Nazwa kategorii")
            cat_desc = st.text_area("Opis")
            submit_cat = st.form_submit_button("Dodaj")
            
            if submit_cat and cat_name:
                data = {"nazwa": cat_name, "opis": cat_desc}
                supabase.table("kategorie").insert(data).execute()
                st.success(f"Dodano kategorię: {cat_name}")
                st.rerun()

    with col2:
        st.subheader("Lista kategorii")
        categories = get_categories()
        if categories:
            for cat in categories:
                col_c1, col_c2 = st.columns([3, 1])
                col_c1.write(f"**{cat['nazwa']}** - {cat['opis']}")
                if col_c2.button("Usuń", key=f"del_cat_{cat['id']}"):
                    try:
                        supabase.table("kategorie").delete().eq("id", cat['id']).execute()
                        st.rerun()
                    except:
                        st.error("Nie można usunąć kategorii, do której przypisane są produkty!")
        else:
            st.info("Brak kategorii w bazie.")

# --- MODUŁ PRODUKTY ---
elif choice == "Produkty":
    st.header("🍎 Zarządzanie Produktami")
    
    # Pobranie kategorii do selectboxa
    categories = get_categories()
    cat_options = {c['nazwa']: c['id'] for c in categories}
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("Dodaj produkt")
        if not categories:
            st.warning("Najpierw dodaj przynajmniej jedną kategorię!")
        else:
            with st.form("add_product_form", clear_on_submit=True):
                p_name = st.text_input("Nazwa produktu")
                p_count = st.number_input("Liczba", min_value=0, step=1)
                p_price = st.number_input("Cena", min_value=0.0, format="%.2f")
                p_cat_name = st.selectbox("Kategoria", options=list(cat_options.keys()))
                
                submit_prod = st.form_submit_button("Dodaj produkt")
                
                if submit_prod and p_name:
                    prod_data = {
                        "nazwa": p_name,
                        "liczba": p_count,
                        "cena": p_price,
                        "kategoria_id": cat_options[p_cat_name]
                    }
                    supabase.table("produkty").insert(prod_data).execute()
                    st.success(f"Dodano produkt: {p_name}")
                    st.rerun()

    with col2:
        st.subheader("Aktualny asortyment")
        products = get_products()
        if products:
            for p in products:
                # Obsługa join - nazwa kategorii może być w słowniku 'kategorie'
                cat_display = p.get('kategorie', {}).get('nazwa', 'Brak')
                
                col_p1, col_p2 = st.columns([3, 1])
                col_p1.markdown(f"**{p['nazwa']}** | Ilość: {p['liczba']} | Cena: {p['cena']} zł | Kat: *{cat_display}*")
                
                if col_p2.button("Usuń", key=f"del_prod_{p['id']}"):
                    supabase.table("produkty").delete().eq("id", p['id']).execute()
                    st.rerun()
        else:
            st.info("Brak produktów w bazie.")
