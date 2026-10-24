import streamlit as st
from supabase import create_client, Client

_key = st.secrets.get("SUPABASE_SERVICE_KEY") or st.secrets["SUPABASE_KEY"]
if not st.secrets.get("SUPABASE_SERVICE_KEY"):
    print("WARNING: SUPABASE_SERVICE_KEY missing, using anon key. This breaks once RLS is on.")

supabase: Client = create_client(st.secrets["SUPABASE_URL"], _key)
