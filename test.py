
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
endpoint_url=endpoint_url,
config=Config(signature_version='s3')
)

# Example: List buckets
# try:
#     response = s3_client.list_buckets()
#     print("Buckets:")
#     for bucket in response['Buckets']:
#         print(bucket['Name'])
#         # list file 
#         try:
#             objects = s3_client.list_objects_v2(Bucket=bucket['Name'])
#             if 'Contents' in objects:
#                 print(" Files:")
#                 for obj in objects['Contents']:
#                     print(f"  - {obj['Key']}")
#             else:
#                 print(" No files found in this bucket.")
#         except Exception as e:
#             print(f"Error listing objects in bucket {bucket['Name']}: {e}")
# except Exception as e:
#     print(f"Error: {e}") 

# Upload a file to S3
bucket_name = 'drama'  # Replace with your actual bucket name
file_path = 'test.mp4'
key = '41000118944/episode_3/Penantian_untuk_Dicintai_ep_3.mp4'  # https://s3.nevaobjects.id/drama/41000118944/episode_3/Penantian_untuk_Dicintai_ep_3.mp4

try:
    # s3_client.upload_file(file_path, bucket_name, key)
    # print(f"Successfully uploaded {file_path} to {bucket_name}/{key}")
    # Generate a presigned URL for the uploaded file
    presigned_url = s3_client.generate_presigned_url(
        'get_object',
        Params={'Bucket': bucket_name, 'Key': key},
        ExpiresIn=3600  # URL expires in 1 hour
    )
    print(f"Presigned URL: {presigned_url}")
except Exception as e:
    print(f"Error uploading file: {e}")