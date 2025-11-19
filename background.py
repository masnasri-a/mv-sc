from config.db import get_supabase_client
from services.utils import generate_url
from services.scraper import scrape_by_url
import os, shutil

if __name__ == "__main__":
    for item in os.listdir('.'):
        if item.startswith('browser_data') and os.path.isdir(item):
            shutil.rmtree(item)
            print(f"Removed directory: {item}")
    supabase = get_supabase_client()
    list_drama = supabase.table('Drama').select('*').eq('has_downloaded', False).limit(10).execute()
    for drama in list_drama.data:
        print(drama)
        url = generate_url(drama['id'])
        scrape_by_url(url, drama['id'])



    pass  # The listing and upload code has been commented out for now