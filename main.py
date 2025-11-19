#!/usr/bin/env python3
"""
Main script to open https://dramaboss.online/ in Playwright with persistent browser context (non-incognito)
"""

import time
from playwright.sync_api import sync_playwright
import os
import requests
from bs4 import BeautifulSoup
import random
import uuid
import json
import argparse
import re
import shutil

# List of user agents for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/119.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/119.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
]

def get_random_user_agent():
    """Get a random user agent from the list"""
    return random.choice(USER_AGENTS)

def generate_random_uuid():
    """Generate a random UUID in the format similar to 90f6243fe90a4c8fe6ed952f69e7fc97"""
    return str(uuid.uuid4()).replace('-', '')

def setup_request_interception(page):
    """Setup request interception to modify API payloads"""
    
    def handle_request(route, request):
        # Check if this is one of the target API endpoints
        if (request.url == "https://dramaboss.online/api/dramabox/v2/in/check_watched_count" or 
            request.url == "https://dramaboss.online/api/dramabox/v2/in/increment_watched_count"):
            
            # Generate new random UUID
            new_uid = generate_random_uuid()
            print(f"Intercepting {request.method} request to: {request.url}")
            print(f"Original payload: {request.post_data}")
            
            # Create new payload with random UUID
            new_payload = {"uid": new_uid}
            print(f"Modified payload: {json.dumps(new_payload)}")
            
            # Modify the request with new payload
            route.continue_(
                method=request.method,
                headers=request.headers,
                post_data=json.dumps(new_payload)
            )
        else:
            # Let other requests pass through normally
            route.continue_()
    
    # Enable request interception
    page.route("**/*", handle_request)

def get_items_with_requests(url):
    """
    Fetch and parse the webpage using requests and BeautifulSoup
    to extract items from class 'mt-3 grid grid-cols-3 lg:grid-cols-5 gap-3'
    """
    try:
        print("Fetching page with requests...")
        response = requests.get(url)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find the container with the specified class
        grid_container = soup.find('div', class_='mt-3 grid grid-cols-3 lg:grid-cols-5 gap-3')
        
        if grid_container:
            # Get all direct child elements (list items)
            items = grid_container.find_all(recursive=False)
            print(f"Found {len(items)} items using requests + BeautifulSoup:")
            
            for i, item in enumerate(items, 1):
                # Extract basic info from each item
                text_content = item.get_text(strip=True)
                if text_content:
                    print(f"Item {i}: {text_content[:100]}...")
                
                # Extract any links
                links = item.find_all('a')
                for link in links:
                    href = link.get('href')
                    if href:
                        print(f"  Link: {href}")
            
            return items
        else:
            print("Container with class 'mt-3 grid grid-cols-3 lg:grid-cols-5 gap-3' not found")
            return []
            
    except Exception as e:
        print(f"Error fetching with requests: {e}")
        return []
    
def get_items_from_url_with_playwright(url, p):
    browser = p.chromium.launch_persistent_context(
        user_data_dir=os.path.join(os.path.dirname(__file__), "browser_data_temp"),
        headless=True,
        viewport={"width": 1280, "height": 720},
        user_agent=get_random_user_agent(),
        args=[  
            "--no-first-run",
            "--disable-blink-features=AutomationControlled"
        ]
    )
    page = browser.new_page()
    
    while True:
        try:
            setup_request_interception(page)
            page.goto(url, timeout=20000)
            page.wait_for_selector('h3.text-xl', timeout=30000)
            title = page.query_selector('meta[property="og:title"]').get_attribute('content')
            page.wait_for_timeout(5000)  # wait for 2 seconds to ensure full load
            if '(' in title:
                title = title.split('(')[0].strip()
            title = ''.join(c for c in title if c.isalpha() or c.isspace())
            print(f"Page title: {title}")
            eps = page.query_selector('span.text-slate-500.text-xs')
            eps_text = eps.text_content()
            print(f"Episodes text: {eps_text}")
            eps_num = int(''.join(filter(str.isdigit, eps_text)))
            print(f"Total episodes: {eps_num}")
            eps_url = url.replace('/movie/','/ep/')
            content_dir = "content"
            title_dir = os.path.join(content_dir, title.replace('/', '_').replace('\\', '_'))  # Sanitize title for folder name
            if not os.path.exists(title_dir):
                os.makedirs(title_dir, exist_ok=True)
            

            for ep in range(1, eps_num + 1):
                episode_url = f"{eps_url}/{ep}"
                print(f"  Episode {ep} URL: {episode_url}")
                user_agent = get_random_user_agent()
                print(f"  Using User-Agent: {user_agent[:50]}...")
                
                br = p.chromium.launch_persistent_context(
                    user_data_dir=os.path.join(os.path.dirname(__file__), "browser_data_"+str(ep)),
                    headless=True,
                    viewport={"width": 1280, "height": 720},
                    user_agent=user_agent,
                    args=[
                        "--no-first-run",
                        "--disable-blink-features=AutomationControlled"
                    ]
                )
                new_page = br.new_page()
                while True:
                # Setup request interception for API calls
                    try:
                        setup_request_interception(new_page)
                        
                        new_page.goto(episode_url)
                        new_page.wait_for_selector('video', timeout=30000)
                        new_page.wait_for_timeout(2000)  # wait for 2 seconds to ensure video loads
                        
                        video_element = new_page.query_selector('video')
                        if video_element:
                            src = video_element.get_attribute('src')
                            if src:
                                print(f"    Video src: {src}")
                                item_title = title
                                title_dir = os.path.join(content_dir, item_title.replace('/', '_').replace('\\', '_'))
                                if not os.path.exists(title_dir):
                                    os.makedirs(title_dir, exist_ok=True)
                                    print(f"Created folder: {title_dir}")

                                filename = f"{item_title} Ep.{ep}.mp4"
                                filepath = os.path.join(title_dir, filename)
                                response = requests.get(src)
                                with open(filepath, 'wb') as f:
                                    f.write(response.content)
                                print(f"Downloaded {filename}")
                                break
                    except Exception as e:
                        print(f"    Error loading episode page: {e}. Retrying in 10 seconds...")
                        time.sleep(10)
                        pass
                br.close()
            
                print(f"Episode {ep} URL: {episode_url}")


        except Exception as e:
            print(f"Error loading page {url}: {e}. Retrying in 10 seconds...")
            time.sleep(10)
            continue


def get_items_with_playwright(page, p):
    """
    Extract items using Playwright from the same class
    """
    try:
        print("Extracting items with Playwright...")
        
        # Wait for the grid container to load
        page.wait_for_selector('.group', timeout=30000)
        
        # Get all items in the grid container
        items = page.query_selector_all('a.group')

        title = page.query_selector('h2.text-sm').text_content()
        if '(' in title:
            title = title.split('(')[0].strip()
        title = ''.join(c for c in title if c.isalpha() or c.isspace())

        # Create a folder inside 'content' with the title
        content_dir = "content"
        title_dir = os.path.join(content_dir, title.replace('/', '_').replace('\\', '_'))  # Sanitize title for folder name
        if not os.path.exists(title_dir):
            os.makedirs(title_dir, exist_ok=True)
        print(f"Created folder: {title_dir}")
        
        print(f"Found {len(items)} items using Playwright:")
        urls = []
        
        for i, item in enumerate(items, 1):
            total_eps_str = item.query_selector('.prevent-switch').text_content()
            print(f"  Total episodes text: {total_eps_str}")
            total_eps_str = item.query_selector('.prevent-switch').text_content()
            print(f"  Total episodes text: {total_eps_str}")
            total_eps = int(''.join(filter(str.isdigit, total_eps_str)))
            # Extract text content
            # Extract href from the link
            print(f"Item {i}:" , item)
            href:str = item.get_attribute('href')
            temp = {}
            if href.startswith('/'):
                href = page.url.rstrip('/') + href
                temp['url'] = href
            if href:
                print(f"Item {i} href: {href}")
                ep_url = href.replace('/movie/','/ep/')
                temp['episodes'] = []
                temp['video_srcs'] = []
                for ep in range(1, total_eps+1):
                    episode_url = f"{ep_url}/{ep}"
                    print(f"  Episode {ep} URL: {episode_url}")
                    
                    user_agent = get_random_user_agent()
                    print(f"  Using User-Agent: {user_agent[:50]}...")
                    
                    br = p.chromium.launch_persistent_context(
                        user_data_dir=os.path.join(os.path.dirname(__file__), "browser_data_"+str(i)+"_"+str(ep)),
                        headless=True,
                        viewport={"width": 1280, "height": 720},
                        user_agent=user_agent,
                        args=[
                            "--no-first-run",
                            "--disable-blink-features=AutomationControlled"
                        ]
                    )
                    new_page = br.new_page()
                    while True:
                    # Setup request interception for API calls
                        try:
                            setup_request_interception(new_page)
                            
                            new_page.goto(episode_url)
                            new_page.wait_for_selector('video', timeout=30000)
                            new_page.wait_for_timeout(2000)  # wait for 2 seconds to ensure video loads
                            
                            video_element = new_page.query_selector('video')
                            if video_element:
                                src = video_element.get_attribute('src')
                                if src:
                                    print(f"    Video src: {src}")
                                    temp['video_srcs'].append(src)
                                    item_title = title
                                    title_dir = os.path.join(content_dir, item_title.replace('/', '_').replace('\\', '_'))
                                    if not os.path.exists(title_dir):
                                        os.makedirs(title_dir, exist_ok=True)
                                        print(f"Created folder: {title_dir}")

                                    filename = f"{item_title} Ep.{ep}.mp4"
                                    filepath = os.path.join(title_dir, filename)
                                    response = requests.get(src)
                                    with open(filepath, 'wb') as f:
                                        f.write(response.content)
                                    print(f"Downloaded {filename}")
                                    break
                        except Exception as e:
                            print(f"    Error loading episode page: {e}. Retrying in 10 seconds...")
                            time.sleep(10)
                            pass
                    br.close()

                    temp['episodes'].append(episode_url)
            urls.append(temp)
            
        return urls
        
    except Exception as e:
        print(f"Error extracting with Playwright: {e}")
        return []
    

def main():
    url = "https://dramaboss.online/"
    
    # First, try with requests + BeautifulSoup
    requests_items = get_items_with_requests(url)
    
    # Then use Playwright
    with sync_playwright() as p:
        # Create a persistent browser context (non-incognito) with user data directory
        user_data_dir = os.path.join(os.path.dirname(__file__), "browser_data")
        main_user_agent = get_random_user_agent()
        print(f"Main browser User-Agent: {main_user_agent}")

        url_input = input("Enter the URL to process with Playwright (or press Enter to use the main page): ").strip()
        if url_input:
            get_items_from_url_with_playwright(url_input, p)

        else:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=True,  # Set to True if you don't want to see the browser
                viewport={"width": 1280, "height": 720},
                user_agent=main_user_agent,
                args=[
                    "--no-first-run",
                    "--disable-blink-features=AutomationControlled"
                ]
            )
            
            # Get or create a page
            if len(browser.pages) > 0:
                page = browser.pages[0]
            else:
                page = browser.new_page()
            
            # Setup request interception for the main page
            setup_request_interception(page)
            
            # Navigate to the website
            print("Opening https://dramaboss.online/...")
            page.goto(url)
            page.wait_for_selector('.text-lg', timeout=30000)
            print("Website loaded successfully!")
            
            # Extract items using Playwright
            playwright_items = get_items_with_playwright(page, p)
            
            with open("playwright_items.json", "w") as f:
                f.write(json.dumps(playwright_items, indent=2))
            
            print("\n" + "="*50)
            print("SUMMARY:")
            print(f"Items found with requests + BeautifulSoup: {len(requests_items)}")
            print(f"Items found with Playwright: {len(playwright_items)}")
            print("="*50)
            
            print("Browser will remain open. Close it manually or press Ctrl+C to exit.")
        browser.close()

if __name__ == "__main__":
    # Remove all directories starting with "browser"
    for item in os.listdir('.'):
        if item.startswith('browser_data') and os.path.isdir(item):
            shutil.rmtree(item)
            print(f"Removed directory: {item}")
    main()