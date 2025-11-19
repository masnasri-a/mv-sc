
import boto3
from botocore.client import Config

# Replace these placeholders with your credentials
access_key = 'KC3VYX02LN7WIYJGURIN'
secret_key = 'FUXY0Oj6R7CR0GOZAOE4zUnID1Eri0vGeISnnfGb'
endpoint_url = 'https://s3.nevaobjects.id'

# Initialize the S3 client
s3_client = boto3.client(
    's3',
    aws_access_key_id=access_key,
    aws_secret_access_key=secret_key,
    endpoint_url=endpoint_url
)

bucket_name = 'drama'
book_id = '41000118944'

# Get total folders inside book_id
prefix = f"{book_id}/"
try:
    response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=prefix, Delimiter='/')
    folders = response.get('CommonPrefixes', [])
    total_folders = len(folders)
    print(f"Total folders inside {book_id}: {total_folders}")
    for folder in folders:
        print(f"Folder: {folder['Prefix']}")
except Exception as e:
    print(f"Error: {e}")
