import streamlit as st
from supabase import create_client, Client
 
# Server-side only. The service key bypasses RLS; the anon key is locked out.
supabase: Client = create_client(
    st.secrets["SUPABASE_URL"],
    st.secrets["SUPABASE_SERVICE_KEY"],
)
