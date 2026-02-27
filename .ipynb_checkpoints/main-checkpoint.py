# turndataframe into csv before passing to the llm
# https://docs.langchain.com/oss/python/integrations/tools/pandas

from get_rss import get_rss
import pandas as pd

search_keywords = ["ai","artificial intelligence", "machine learning", "robot", "robots", "data science", "grok", "openai", "chatgpt", "claude", "anthropic"]
rss_results = get_rss(search_keywords)

rss_df = pd.DataFrame(rss_results)

print(rss_df)

