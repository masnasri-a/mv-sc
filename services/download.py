
import boto3
import os
from botocore.exceptions import NoCredentialsError, ClientError
from botocore.client import Config

from dotenv import load_dotenv
load_dotenv()

def upload_to_s3(episode, book_id, file_path):
    try:
        s3_endpoint = os.getenv('S3_ENDPOINT', 'https://s3.nevaobjects.id')
        s3_access_key = os.getenv('S3_ACCESS_KEY', 'KC3VYX02LN7WIYJGURIN')
        s3_secret_key = os.getenv('S3_SECRET_KEY', 'FUXY0Oj6R7CR0GOZAOE4zUnID1Eri0vGeISnnfGb')
        bucket_name = 'drama'

        if not s3_access_key or not s3_secret_key:
            print("❌ S3 credentials not found in environment variables")
            return None

        s3_client = boto3.client(
            's3',
            aws_access_key_id=s3_access_key,
            aws_secret_access_key=s3_secret_key,
            endpoint_url=s3_endpoint,
            config=Config(signature_version='s3')
            )

        filename = os.path.basename(file_path)
        s3_key = f"{book_id}/episode_{episode}/{filename}"

        print(f"📤 Uploading {filename} to S3-compatible storage...")
        s3_client.upload_file(file_path, bucket_name, s3_key)

        s3_url = f"{s3_endpoint}/{bucket_name}/{s3_key}"

        print(f"✅ Successfully uploaded to: {s3_url}")
        return s3_url

    except FileNotFoundError:
        print(f"❌ File not found: {file_path}")
        return None
    except NoCredentialsError:
        print("❌ S3 credentials not available")
        return None
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'NoSuchBucket':
            print(f"❌ Bucket '{bucket_name}' does not exist")
        elif error_code == 'AccessDenied':
            print("❌ Access denied to S3 storage")
        else:
            print(f"❌ S3 upload failed: {e}")
        return None
    except Exception as e:
        print(f"❌ Unexpected error during S3 upload: {e}")
        return None