from dotenv import load_dotenv
import os

from threadspipepy.threadspipe import ThreadsPipe

load_dotenv

threads_token = os.getenv('THREADS_TOKEN')
