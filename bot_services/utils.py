import asyncio
from typing import Optional
from bot_services.config import s3_client
from bot_services.database import supabase

async def get_episode_url(drama_id: str, episode_num: int, drama_title: Optional[str] = None) -> Optional[str]:
    """Get presigned URL for episode video using episodes table"""
    try:
        # Get episode key from episodes table
        result = supabase.table('episodes').select('key').eq('drama_id', int(drama_id)).eq('episode', episode_num).execute()

        if result.data and len(result.data) > 0:
            s3_key = result.data[0]['key']
            return await generate_presigned_url_from_key(s3_key)
        else:
            print(f"Episode not found: drama_id={drama_id}, episode={episode_num}")
            return None
    except Exception as e:
        print(f"Error getting episode URL: {e}")
        return None

async def get_episode_url_with_retry(drama_id: str, episode_num: int, drama_title: Optional[str] = None, max_retries: int = 3) -> Optional[str]:
    """Get episode URL with retry mechanism"""

    for attempt in range(max_retries):
        try:
            episode_url = await get_episode_url(drama_id, episode_num, drama_title)
            if episode_url:
                return episode_url

            if attempt < max_retries - 1:  # Don't sleep on last attempt
                print(f"Attempt {attempt + 1} failed, retrying in 2 seconds...")
                await asyncio.sleep(2)  # Wait 2 seconds before retry

        except Exception as e:
            print(f"Error on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2)

    print(f"Failed to get episode URL after {max_retries} attempts")
    return None

async def generate_presigned_url_from_key(s3_key: str) -> Optional[str]:
    """Generate presigned URL from S3 key"""
    try:
        bucket_name: str = 'drama'
        key: str = s3_key.replace('https://s3.nevaobjects.id/drama/', '')

        # Try direct S3 URL first (more compatible with Telegram)
        # direct_url = f"https://s3.nevaobjects.id/{bucket_name}/{key}"
        # print(f"Using direct S3 URL: {direct_url}")
        # return direct_url

        # Fallback to presigned URL if direct URL doesn't work
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': key},
            ExpiresIn=3600
        )
        print(f"Generated presigned URL for {s3_key}: {presigned_url}")
        return presigned_url

    except Exception as e:
        print(f"Error generating URL: {e}")
        return None

async def generate_presigned_url(drama_id: str, episode_num: int, drama_title: Optional[str]) -> str:
    """Generate presigned URL for S3 video file (legacy method)"""
    try:
        bucket_name: str = 'drama'

        # Create S3 key based on drama structure
        # Format: drama_id/episode_X/Drama_Title_ep_X.mp4
        if drama_title:
            # Clean drama title for filename
            clean_title = drama_title.replace(' ', '_').replace('/', '_').replace('\\', '_')
            key = f"{drama_id}/episode_{episode_num}/{clean_title}_ep_{episode_num}.mp4"


        # Generate presigned URL (expires in 1 hour)
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': key},
            ExpiresIn=3600  # URL expires in 1 hour
        )

        print(f"Generated presigned URL for {key}: {presigned_url}")
        return presigned_url

    except Exception as e:
        print(f"Error generating presigned URL: {e}")
        # Fallback to direct S3 URL
        return f"{s3_client.meta.endpoint_url}/{bucket_name}/{drama_id}/episode_{episode_num}/episode_{episode_num}.mp4"

async def safe_reply_text(message, text: str, reply_markup=None, parse_mode: str = None, **kwargs):
    """Safely reply to message, fallback to send_text if reply fails. Returns the sent message."""
    try:
        return await message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode, **kwargs)
    except Exception as e:
        print(f"Reply failed, using send_text instead: {e}")
        try:
            return await message.chat.send_message(text, reply_markup=reply_markup, parse_mode=parse_mode, **kwargs)
        except Exception as e2:
            print(f"Send message also failed: {e2}")
            # Last resort - try without parse_mode
            try:
                return await message.chat.send_message(text, reply_markup=reply_markup, **kwargs)
            except Exception as e3:
                print(f"All message sending methods failed: {e3}")
                raise Exception(f"Failed to send message after all attempts: {e3}") from e3

async def safe_edit_message(query, text: str, reply_markup=None, parse_mode: str = None) -> None:
    """Safely edit message text or caption depending on message type"""
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception as e:
        if "no text in the message to edit" in str(e).lower():
            # If original message was a photo, edit the caption instead
            try:
                await query.edit_message_caption(
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
            except Exception:
                # If that fails too, send a new message
                await safe_reply_text(query.message, text, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            # For other errors, try sending a new message
            await safe_reply_text(query.message, text, reply_markup=reply_markup, parse_mode=parse_mode)