import json
import os
import time

from dotenv import load_dotenv
from google import genai


MIN_SECONDS_BETWEEN_CALLS = 8
last_successful_call_time = None


# Load the Gemini API key from the .env file and create a client.
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
	raise RuntimeError("GEMINI_API_KEY is not set in the .env file")

client = genai.Client(api_key=api_key)


def call_gemini_with_retry(client, model, prompt):
	global last_successful_call_time

	# Retry up to five times with exponential backoff between attempts.
	max_retries = 5
	wait_seconds = 5
	for attempt in range(1, max_retries + 1):
		# Keep successful Gemini calls at least eight seconds apart.
		if last_successful_call_time is not None:
			elapsed_seconds = time.monotonic() - last_successful_call_time
			remaining_seconds = MIN_SECONDS_BETWEEN_CALLS - elapsed_seconds
			if remaining_seconds > 0:
				time.sleep(remaining_seconds)

		try:
			response = client.models.generate_content(model=model, contents=prompt)
			last_successful_call_time = time.monotonic()
			return response
		except Exception as error:
			if attempt < max_retries:
				error_message = str(error)
				if "429" in error_message or "RESOURCE_EXHAUSTED" in error_message:
					print(f"Attempt {attempt} failed: rate limit hit (waiting 60s)")
					time.sleep(60)
				elif "503" in error_message:
					print(
						f"Attempt {attempt} failed: server busy (waiting {wait_seconds}s)"
					)
					time.sleep(wait_seconds)
					wait_seconds *= 2
				else:
					print(
						f"Attempt {attempt} failed, waiting {wait_seconds}s before retrying..."
					)
					time.sleep(wait_seconds)
					wait_seconds *= 2

	return None


def generate_section(
	section_name,
	instructions,
	relevant_facts,
	client,
	min_words=150,
	max_words=400,
):
	# Build a section-specific prompt using only the supplied relevant facts.
	prompt = f"""
Write the {section_name} section of a professional research paper.

Specific instructions:
{instructions}

Write between {min_words} and {max_words} words. Stay within this range, but do not
pad the section with filler or repeat information just to reach the minimum.

Relevant facts:
{json.dumps(relevant_facts, indent=2)}

Do not add any claim, statistic, technology, dataset, or detail that is not present in the given facts. If information needed is missing, write only using what is available, and do not fill gaps with invented content.

Return plain text only, with no JSON or Markdown, just the section's prose.
"""

	# Ask Gemini to generate the section with retry handling.
	response = call_gemini_with_retry(client, "gemini-3.8-flash", prompt)
	if response is None:
		return "Could not generate the section because the AI service was unavailable."

	return response.text.strip()


