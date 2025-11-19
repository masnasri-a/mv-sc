from config.db import get_supabase_client
from pydantic import BaseModel

class URLGenerator(BaseModel):
    url: str
    book_name: str

def generate_url(book_id: str) :
    detail = get_supabase_client().table('Drama').select('book_name').eq('id', book_id).execute().data
    if detail and len(detail) > 0:
        print(detail)
        url = f"https://dramaboss.online/movie/{book_id}/{detail[0]['book_name']}"
        return url
    return ""