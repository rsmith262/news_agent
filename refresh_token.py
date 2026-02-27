from threadspipepy.threadspipe import ThreadsPipe

import os
from dotenv import load_dotenv, set_key

# Load env vars
dotenv_file = ".env"
load_dotenv(dotenv_file)

token = os.getenv("THREADS_TOKEN")
handle = os.getenv("THREADS_HANDLE")

api = ThreadsPipe(
    user_id=handle,
    access_token=token,
)

refreshed = api.refresh_token(
    access_token=token
)

########################################
#update to .env file
new_token = refreshed["access_token"]
os.environ["THREADS_TOKEN"] = new_token

# Persist to .env file
set_key(dotenv_file, "THREADS_TOKEN", new_token)