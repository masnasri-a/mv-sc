import requests, os, shutil
from services.download import upload_to_s3
from config.db import get_supabase_client
from bs4 import BeautifulSoup

supabase = get_supabase_client()
content_dir = "content"
while True:
# get drama list from supabase where has_downloaded is false limit 10 desc order by id
    drama_list = supabase.table('Drama').select('*').eq('has_downloaded', False).order('id', desc=True).limit(10).execute()
    if not drama_list.data or len(drama_list.data) == 0:
        print("All dramas have been processed. Exiting.")
        break
    for drama in drama_list.data:
        url = "https://dramasubs.com/in/movie/{}/{}".format(drama['id'], drama['book_name_lower'])
        print(f"Fetching URL: {url}")
        response = requests.get(url)
        if response.status_code != 200:
            print(f"Failed to fetch drama page for ID {drama['id']}. Status code: {response.status_code}")
            continue
        soup = BeautifulSoup(response.text, 'html.parser')
        div_element = soup.find('div', class_='row row-cols-2 row-cols-md-4 row-cols-lg-6 g-1')
        if not div_element:
            print(f"No episode list found for drama ID {drama['id']}")
            continue
        episode_links = div_element.find_all('a', class_='ep-item')
        total_episodes = len(episode_links) - 1
        print(f"Total episodes found: {total_episodes}")
        for index, episode in enumerate(episode_links, start=1):
            if '#' not in episode.get('href'):
                episode_href = episode.get('href')
                episode_title = episode.find('img').get('alt')
                print(f"Episode Title: {episode_title}, Link: {episode_href}")
                response_ep = requests.get(episode_href)
                if response_ep.status_code != 200:
                    print(f"  Failed to fetch episode page: {episode_href}. Status code: {response_ep.status_code}")
                    continue
                soup_ep = BeautifulSoup(response_ep.text, 'html.parser')
                video_element = soup_ep.find('video')
                if video_element:
                    source_element = video_element.find('source')
                    if source_element and source_element.get('src'):
                        video_url = source_element.get('src')
                        print(f"  Video URL: {video_url}")
                        # upload to s3
                        item_title = episode_title.lower().replace(' ','_')
                        title_dir = os.path.join(content_dir, item_title.replace('/', '_').replace('\\', '_'))
                        if not os.path.exists(title_dir):
                            os.makedirs(title_dir, exist_ok=True)
                            print(f"Created folder: {title_dir}")
                        filename = f"{item_title}_ep_{index}.mp4"
                        filepath = os.path.join(title_dir, filename)
                        response = requests.get(video_url)
                        with open(filepath, 'wb') as f:
                            f.write(response.content)
                        print("Upload data")
                        s3_url = upload_to_s3(index, drama['id'], filepath)
                        print("s3_url : ",s3_url)
                        if s3_url:
                            print(f"Uploaded to S3: {s3_url}")
                            # remove folder after upload
                            if os.path.exists(title_dir):
                                shutil.rmtree(title_dir)
                                print(f"Removed folder: {title_dir}")
                            # update supabase with s3_url for episode
                            idx = int(str(drama['id']) + str(index))
                            supabase.table('episodes').upsert({
                                'id': idx,
                                'drama_id': drama['id'],
                                'episode': index,
                                'key': s3_url}).execute()
                            print(f"Updated database for drama ID {drama['id']} episode {index}")
                        else:
                            print("Failed to upload to S3")
                    else:
                        print(f"  No source found in video on episode page: {episode_href}")
                else:
                    print(f"  No video found on episode page: {episode_href}")

            if index >= total_episodes:
                print(f"All episodes processed for drama ID {drama['id']}. Updating has_downloaded to True.")
                supabase.table('Drama').update({'has_downloaded': True}).eq('id', drama['id']).execute()
                break

        # example = "https://dramasubs.com/in/movie/41000102839/aku-melintas-dari-duniamu"

        # response = requests.get(example)
        # print(response.status_code)
        # with open("dramasubs.html", "w", encoding="utf-8") as f:
        #     f.write(response.text)

        # example_1 = "https://dramasubs.com/in/ep/41000102839_aku-melintas-dari-duniamu/568203144_Episode-1"
        # response_1 = requests.get(example_1)
        # print(response_1.status_code)
        # with open("dramasubs_ep.html", "w", encoding="utf-8") as f:
        #     f.write(response_1.text)