import os

from dotenv import load_dotenv
from google import genai


# Load the Gemini API key from the .env file.
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
	raise RuntimeError("GEMINI_API_KEY is not set in the .env file")

# Create the Gemini client with the API key.
client = genai.Client(api_key=api_key)

# Send a simple test prompt to Gemini.
response = client.models.generate_content(
	model="gemini-3.8-flash",
	contents="Say hello in one sentence",
)

# Print Gemini's response.
print(response.text)
