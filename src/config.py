import os

from dotenv import load_dotenv

load_dotenv()

NEWS_API_KEY = os.getenv("NEWS_API_KEY")

if not NEWS_API_KEY:
    raise RuntimeError("NEWS_API_KEY is not set. Check your .env file.")