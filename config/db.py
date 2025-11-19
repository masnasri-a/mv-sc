from supabase import create_client, Client

import os
from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
ANON_KEY = os.getenv("ANON_KEY")

supabase: Client = create_client(SUPABASE_URL, ANON_KEY)
def get_supabase_client() -> Client:
    return supabase