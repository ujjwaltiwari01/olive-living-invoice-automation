from google.cloud import documentai
from google.oauth2 import service_account

project_id = "olive-invoice-automation"
location = "us"
processor_id = "b6c8916bc52a549"

credentials = service_account.Credentials.from_service_account_file(
    r"D:\Olive invoice automation\olive-invoice-automation-a4c87dd56907.json"
)

client = documentai.DocumentProcessorServiceClient(credentials=credentials)

name = client.processor_path(project_id, location, processor_id)

print("Processor connected:", name)