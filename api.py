from fastapi import FastAPI
import uvicorn
import requests
from bs4 import BeautifulSoup
import json
from supabase import create_client, Client
import os
from dotenv import load_dotenv

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
ANON_KEY = os.getenv("ANON_KEY")
supabase: Client = create_client(SUPABASE_URL, ANON_KEY)

# Define the Drama table fields (assuming Supabase table creation via SQL or dashboard)
# For example, the table 'Drama' could have fields based on the scraped data:
# - id (primary key, auto-increment or UUID)
# - book_id (text)
# - book_name (text)
# - book_name_en (text)
# - book_name_lower (text)
# - cover_wap (text)
# - introduction (text)
# - click_num (integer)
# - chapter_id (text)

# If you need to insert data into the table, you can modify the search function accordingly.
# For instance, add this inside the search function loop:
# supabase.table('Drama').insert({
#     'book_id': detail['bookId'],
#     'book_name': detail['bookName'],
#     'book_name_en': detail['bookNameEn'],
#     'book_name_lower': detail['bookNameLower'],
#     'cover_wap': detail['coverWap'],
#     'introduction': detail['introduction'],
#     'click_num': detail['clickNum'],
#     'chapter_id': detail['chapterId']
# }).execute()

app = FastAPI()

@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.get("/search/{name}")
def search(name: str):
    url = f'https://www.dramaboxdb.com/in/search?searchValue={name}'
    print(f"Searching for: {url}")
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    script = soup.find('script', id='__NEXT_DATA__')
    data = json.loads(script.string)
    list_details = data['props']['pageProps']['bookList']
    list_response = []
    for detail in list_details:
        temp = {
            'id': detail['bookId'],
            'book_name': detail['bookName'],
            'book_name_en': detail['bookNameEn'],
            'book_name_lower': detail['bookNameLower'],
            'cover': detail['coverWap'],
            'chapter_id': detail['chapterId']
        }
        supabase.table('Drama').upsert(temp).execute()
        list_response.append(temp)
    return {"results": list_response}
    


if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)