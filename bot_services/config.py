import os
from dotenv import load_dotenv
from botocore.client import Config
import boto3

# Load environment variables
load_dotenv()

# Supabase configuration
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

# Bot configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Admin whitelist - users with unlimited access
ADMIN_WHITELIST = [1356120446, 731203660]

# S3 configuration for video streaming
S3_ENDPOINT = os.getenv('S3_ENDPOINT')
S3_ACCESS_KEY = os.getenv('S3_ACCESS_KEY')
S3_SECRET_KEY = os.getenv('S3_SECRET_KEY')

# Initialize S3 client
s3_client = boto3.client(
    's3',
    aws_access_key_id=S3_ACCESS_KEY,
    aws_secret_access_key=S3_SECRET_KEY,
    endpoint_url=S3_ENDPOINT,
    config=Config(signature_version='s3')
)