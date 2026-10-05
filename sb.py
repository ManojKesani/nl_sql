import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# Initialize the native Groq client
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Fetch all available models
models_page = client.models.list()

print("Available Groq Models:")
for model in models_page.data:
    print(f"- {model.id}")
