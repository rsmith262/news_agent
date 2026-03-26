# turndataframe into csv before passing to the llm
# https://docs.langchain.com/oss/python/integrations/tools/pandas

from get_rss import get_rss
import pandas as pd
from pprint import pprint

# show all cols
pd.set_option('display.max_columns', None)

search_keywords = ["ai","artificial intelligence", "machine learning", "robot", "robots", "data science", "grok", "openai", "chatgpt", "claude", "anthropic","LLM","Mistral","Gemini", "Deepseek","llama","codex"]
rss_results = get_rss(search_keywords)

rss_df = pd.DataFrame(rss_results)

print(rss_df)
print('############################################')
#pprint(rss_results)
print((rss_df.shape))

rss_df.to_csv('test_rss_feeds.csv',index=False)

## do a further filter if the user asks for a specific topic


