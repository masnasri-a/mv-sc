from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
from supabase import create_client, Client
from config.db import get_supabase_client
from bot_services.config import SUPABASE_URL, SUPABASE_KEY, ADMIN_WHITELIST, s3_client
import boto3

supabase: Client = get_supabase_client()

async def get_user_watch_count(user_id: int) -> Dict[str, int]:
    """Get user's watch count information"""
    # Check if user is in admin whitelist - unlimited access
    if user_id in ADMIN_WHITELIST:
        return {'used': 0, 'limit': 9999}

    if not supabase:
        return {'used': 0, 'limit': 1}

    try:
        result = supabase.table('users').select('free_watches_used, free_watches_limit, reset_time').eq('telegram_id', user_id).execute()
        if result.data:
            user_data = result.data[0]
            current_time = datetime.now(timezone.utc)

            # Check if we need to reset weekly watch count
            last_reset = user_data.get('reset_time')
            if last_reset:
                last_reset_time = datetime.fromisoformat(last_reset.replace('Z', '+00:00'))
                # Reset if more than 7 days have passed
                if (current_time - last_reset_time).days >= 7:
                    # Reset watch count and update reset time
                    supabase.table('users').update({
                        'free_watches_used': 0,
                        'reset_time': datetime.now(timezone.utc).isoformat()
                    }).eq('telegram_id', user_id).execute()
                    return {
                        'used': 0,
                        'limit': user_data['free_watches_limit'] or 1
                    }

            return {
                'used': user_data['free_watches_used'] or 0,
                'limit': user_data['free_watches_limit'] or 1
            }
        return {'used': 0, 'limit': 1}
    except Exception as e:
        print(f"Error getting watch count: {e}")
        return {'used': 0, 'limit': 1}

async def increment_watch_count(user_id: int) -> None:
    """Increment user's watch count"""
    # Skip incrementing for whitelisted users
    if user_id in ADMIN_WHITELIST:
        return

    if not supabase:
        return

    try:
        # First get current watch count
        result = supabase.table('users').select('free_watches_used').eq('telegram_id', user_id).execute()
        if result.data:
            current_count = result.data[0]['free_watches_used'] or 0
            new_count = current_count + 1

            # Update with incremented value
            supabase.table('users').update({
                'free_watches_used': new_count,
                'reset_time': datetime.now(timezone.utc).isoformat(),
                'last_active': datetime.now(timezone.utc).isoformat()
            }).eq('telegram_id', user_id).execute()
    except Exception as e:
        print(f"Error incrementing watch count: {e}")

async def check_user_premium_status(user_id: int) -> bool:
    """Check if user has active premium or is whitelisted"""
    # Check if user is in admin whitelist
    if user_id in ADMIN_WHITELIST:
        return True

    if not supabase:
        return False

    try:
        result = supabase.table('users').select('is_premium, premium_expiry').eq('telegram_id', user_id).execute()
        if result.data:
            user_data = result.data[0]
            if user_data['is_premium'] and user_data['premium_expiry']:
                expiry = datetime.fromisoformat(user_data['premium_expiry'].replace('Z', '+00:00'))
                return expiry > datetime.now(expiry.tzinfo)
        return False
    except Exception as e:
        print(f"Error checking premium status: {e}")
        return False

async def create_or_update_user(user_id: int, username: Optional[str], first_name: str) -> None:
    """Create or update user in database"""
    if not supabase:
        return

    try:
        # Check if user exists
        result = supabase.table('users').select('*').eq('telegram_id', user_id).execute()
        print("User lookup result:", result)
        if not result.data:
            # Create new user
            user_data = {
                'telegram_id': user_id,
                'username': username,
                'first_name': first_name,
                'is_premium': False,
                'free_watches_used': 0,
                'free_watches_limit': 1,
                'reset_time': datetime.now(timezone.utc).isoformat(),
                'created_at': datetime.now(timezone.utc).isoformat(),
                'last_active': datetime.now(timezone.utc).isoformat()
            }
            supabase.table('users').insert(user_data).execute()
        else:
            # Update last active
            supabase.table('users').update({
                'last_active': datetime.now(timezone.utc).isoformat()
            }).eq('telegram_id', user_id).execute()

    except Exception as e:
        print(f"Error creating/updating user: {e}")

async def get_featured_dramas(limit: int = 3) -> List[Dict[str, Any]]:
    """Get featured dramas from Drama table"""
    if not supabase:
        return []

    try:
        # Get random dramas from Drama table, ordered by created_at desc to get newest
        result = supabase.table('Drama').select('id, book_name, book_name_en, cover, chapter_id').eq('has_downloaded', True).order('created_at', desc=True).limit(limit).execute()
        print(result)
        # Format data to match expected structure
        dramas = []
        for drama in result.data:
            total_episodes = await get_total_eps(str(drama['id']))
            dramas.append({
                'id': str(drama['id']),
                'title': drama['book_name'],
                'book_name': drama['book_name'],
                'book_name_en': drama['book_name_en'],
                'cover': drama['cover'],
                'chapter_id': drama['chapter_id'],
                'episodes': total_episodes  # Default episodes, can be calculated if needed
            })


        return dramas
    except Exception as e:
        print(f"Error getting featured dramas: {e}")
        return []

async def get_available_dramas() -> List[Dict[str, Any]]:
    """Get available dramas from Drama table"""
    print("Fetching available dramas...")
    if not supabase:
        return []

    try:
        # Get dramas from actual Drama table
        result = supabase.table('Drama').select('id, book_name, book_name_en, cover, chapter_id').eq('has_downloaded', True).order('created_at', desc=True).limit(20).execute()
        print("Available dramas:", result)
        # Format data to match expected structure
        dramas = []
        for drama in result.data:
            total_episodes = await get_total_eps(str(drama['id']))
            dramas.append({
                'id': str(drama['id']),
                'title': drama['book_name'],
                'book_name': drama['book_name'],
                'book_name_en': drama['book_name_en'],
                'cover': drama['cover'],
                'chapter_id': drama['chapter_id'],
                'episodes': total_episodes,  # Default episodes
                'genre': 'Drama',  # Default genre
                'rating': 9.0  # Default rating
            })

        return dramas
    except Exception as e:
        print(f"Error getting dramas: {e}")
        return []

async def get_drama_details(drama_id: str) -> Optional[Dict[str, Any]]:
    """Get drama details from Drama table"""
    if not supabase:
        return None

    try:
        # Get drama from Drama table by id
        result = supabase.table('Drama').select('*').eq('id', int(drama_id)).execute()

        if result.data:
            drama = result.data[0]
            # Get actual episode count from S3
            actual_episodes = await get_episode_count_from_s3(drama_id)
            return {
                'id': str(drama['id']),
                'title': drama['book_name'],
                'book_name': drama['book_name'],
                'book_name_en': drama['book_name_en'],
                'cover': drama['cover'],
                'chapter_id': drama['chapter_id'],
                'description': f"Drama menarik tentang {drama['book_name']}",
                'episodes': actual_episodes
            }
        return None
    except Exception as e:
        print(f"Error getting drama details: {e}")
        return None

async def search_dramas_by_name(search_query: str) -> List[Dict[str, Any]]:
    """Search dramas by book_name with case-insensitive matching"""
    if not supabase:
        return []
    import requests
    url_search = 'http://202.155.91.194:8000/search/'
    try:
        full_url_search = url_search + search_query.replace(" ", "%20")
        response = requests.get(full_url_search, timeout=10)
        # data = response.json()
        # return data
    except Exception as e:
        print(f"Error searching dramas via external API: {e}")
    try:
        # Clean and prepare search query
        clean_query: str = search_query.strip().lower()

        # Get all available dramas first
        result = supabase.table('Drama').select('id, book_name, book_name_en, cover, chapter_id').eq('has_downloaded', True).execute()

        if not result.data:
            return []

        # Filter results based on case-insensitive search
        filtered_dramas: List[Dict[str, Any]] = []

        for drama in result.data:
            book_name_lower: str = drama['book_name'].lower() if drama['book_name'] else ''
            book_name_en_lower: str = drama['book_name_en'].lower() if drama['book_name_en'] else ''

            # Check if search query is found in either book_name or book_name_en
            if (clean_query in book_name_lower or
                clean_query in book_name_en_lower or
                any(word in book_name_lower for word in clean_query.split()) or
                any(word in book_name_en_lower for word in clean_query.split())):

                # Get episode count for this drama
                episode_count: int = await get_episode_count_from_s3(str(drama['id']))

                filtered_dramas.append({
                    'id': str(drama['id']),
                    'title': drama['book_name'],
                    'book_name': drama['book_name'],
                    'book_name_en': drama['book_name_en'],
                    'cover': drama['cover'],
                    'chapter_id': drama['chapter_id'],
                    'episodes': episode_count,
                    'genre': 'Drama',
                    'rating': 9.0
                })

        # Sort by relevance (exact matches first, then partial matches)
        def relevance_score(drama_item: Dict[str, Any]) -> int:
            score: int = 0
            book_name_lower: str = drama_item['book_name'].lower()

            # Exact match gets highest score
            if clean_query == book_name_lower:
                score += 100
            # Match at beginning gets high score
            elif book_name_lower.startswith(clean_query):
                score += 50
            # Contains match gets medium score
            elif clean_query in book_name_lower:
                score += 25
            # Word match gets lower score
            else:
                score += 10

            return score

        filtered_dramas.sort(key=relevance_score, reverse=True)

        return filtered_dramas[:20]  # Limit to 20 results

    except Exception as e:
        print(f"Error searching dramas: {e}")
        return []

async def get_total_eps(drama_id: str) -> int:
    """Get total episodes for a drama from S3"""
    # Replace these placeholders with your credentials
    # Initialize the S3 client
    _s3_client = boto3.client(
        's3',
        aws_access_key_id=s3_client._request_signer._credentials.access_key,
        aws_secret_access_key=s3_client._request_signer._credentials.secret_key,
        endpoint_url=s3_client.meta.endpoint_url
    )

    bucket_name = 'drama'
    prefix = f"{drama_id}/"
    try:
        response = _s3_client.list_objects_v2(Bucket=bucket_name, Prefix=prefix, Delimiter='/')
        folders = response.get('CommonPrefixes', [])
        total_folders = len(folders)
        return total_folders
    except Exception as e:
        print(f"Error: {e}")

async def get_episode_count_from_s3(drama_id: str) -> int:
    """Get actual episode count from episodes table"""
    try:
        result = supabase.table('episodes').select('episode').eq('drama_id', int(drama_id)).execute()

        if result.data:
            # Get the maximum episode number
            episodes = [int(ep['episode']) for ep in result.data if ep['episode']]
            return max(episodes) if episodes else 0
        else:
            return 0
    except Exception as e:
        print(f"Error getting episode count: {e}")
        return 0

async def generate_payment_code(user_id: int, package_type: str) -> str:
    """Generate unique payment code for user"""
    import hashlib
    import time

    # Generate unique code based on user_id, package_type, and timestamp
    raw_string = f"{user_id}_{package_type}_{int(time.time())}"
    payment_code = hashlib.md5(raw_string.encode()).hexdigest()[:8].upper()

    # Store payment code in database for tracking
    if supabase:
        try:
            payment_data = {
                'user_id': user_id,
                'package_type': package_type,
                'amount': {'1day': 3000, '7day': 10000, '30day': 25000, '1year': 50000}[package_type],
                'status': 'pending',
                'payment_code': payment_code
            }
            supabase.table('payments').insert(payment_data).execute()
        except Exception as e:
            print(f"Error storing payment code: {e}")

    return payment_code

async def create_payment_record(user_id: int, package_type: str) -> Optional[int]:
    """Create payment record for tracking"""
    if not supabase:
        return None

    try:
        package_prices = {
            '1day': 3000,
            '7day': 10000,
            '30day': 25000,
            '1year': 50000
        }

        payment_data = {
            'user_id': user_id,
            'package_type': package_type,
            'amount': package_prices[package_type],
            'status': 'pending'
        }

        result = supabase.table('payments').insert(payment_data).execute()
        return result.data[0]['id'] if result.data else None
    except Exception as e:
        print(f"Error creating payment record: {e}")
        return None

async def get_telegram_file_id(s3_key: str) -> Optional[str]:
    """Get cached Telegram file_id for episode using S3 key"""
    if not supabase:
        return None

    try:
        # Parse drama_id and episode from S3 key (format: drama_id/episode_X/filename)
        parts = s3_key.split('/')
        if len(parts) >= 3:
            drama_id = int(parts[0])
            # Extract episode number from episode_X format
            episode_part = parts[1]  # e.g., "episode_1"
            if episode_part.startswith('episode_'):
                episode_num = int(episode_part.split('_')[1])
            else:
                return None
        else:
            return None

        result = supabase.table('telegram_cache').select('file_id').eq('drama_id', drama_id).eq('episode', episode_num).execute()
        if result.data:
            return result.data[0]['file_id']
        return None
    except Exception as e:
        print(f"Error getting Telegram file_id: {e}")
        return None

async def store_telegram_file_id(s3_key: str, file_id: str) -> None:
    """Store Telegram file_id for episode caching using S3 key"""
    if not supabase:
        return

    try:
        # Parse drama_id and episode from S3 key (format: drama_id/episode_X/filename)
        parts = s3_key.split('/')
        if len(parts) >= 3:
            drama_id = int(parts[0])
            # Extract episode number from episode_X format
            episode_part = parts[1]  # e.g., "episode_1"
            if episode_part.startswith('episode_'):
                episode_num = int(episode_part.split('_')[1])
            else:
                return
        else:
            return

        # Check if record exists
        result = supabase.table('telegram_cache').select('id').eq('drama_id', drama_id).eq('episode', episode_num).execute()

        if result.data:
            # Update existing record
            supabase.table('telegram_cache').update({
                'file_id': file_id,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }).eq('drama_id', drama_id).eq('episode', episode_num).execute()
        else:
            # Create new record
            cache_data = {
                'drama_id': drama_id,
                'episode': episode_num,
                'file_id': file_id,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'updated_at': datetime.now(timezone.utc).isoformat()
            }
            supabase.table('telegram_cache').insert(cache_data).execute()
    except Exception as e:
        print(f"Error storing Telegram file_id: {e}")