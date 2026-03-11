import feedparser
#import json
import re
from datetime import datetime, timedelta
import time
#import pandas as pd

def get_rss(keywords): #function used in main.py
    # add other rss for other big news outlets itv, sky, maybe as well things like real python
    urls = [# Original
            "https://www.theguardian.com/uk/technology/rss",
            "https://www.theguardian.com/uk-news/rss",
            "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
            "https://www.marktechpost.com/feed/",
            "https://www.wired.com/feed/rss",
            "https://openai.com/blog/rss/",
            "https://news.microsoft.com/source/topics/ai/feed/",
            "https://feeds.bbci.co.uk/news/technology/rss.xml",

            # General AI News
            "https://openai.com/blog/rss.xml",
            "https://deepmind.google/blog/rss.xml",
            "https://www.anthropic.com/news/rss.xml",
            "https://www.technologyreview.com/topic/artificial-intelligence/feed/",
            "https://venturebeat.com/category/ai/feed/",
            "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml",

            # Research-Focused
            "https://export.arxiv.org/rss/cs.AI",
            "https://export.arxiv.org/rss/cs.LG",
            "https://paperswithcode.com/rss",

            # Enterprise / Business AI
            "https://techcrunch.com/tag/artificial-intelligence/feed/",
            "https://aibusiness.com/rss.xml",
            "https://www.mckinsey.com/featured-insights/artificial-intelligence/rss",

            # Aggregators / Newsletters
            "https://importai.substack.com/feed",
            "https://www.bensbites.co/rss",
            "https://tldr.tech/ai/rss",
            ]
    
    # urls = [
    #         # General AI News
    #         "https://openai.com/blog/rss.xml",
    #         "https://deepmind.google/blog/rss.xml",
    #         "https://www.anthropic.com/news/rss.xml",
    #         "https://www.technologyreview.com/topic/artificial-intelligence/feed/",
    #         "https://venturebeat.com/category/ai/feed/",
    #         "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml",

    #         # Research-Focused
    #         "https://export.arxiv.org/rss/cs.AI",
    #         "https://export.arxiv.org/rss/cs.LG",
    #         "https://paperswithcode.com/rss",

    #         # Enterprise / Business AI
    #         "https://techcrunch.com/tag/artificial-intelligence/feed/",
    #         "https://aibusiness.com/rss.xml",
    #         "https://www.mckinsey.com/featured-insights/artificial-intelligence/rss",

    #         # Aggregators / Newsletters
    #         "https://importai.substack.com/feed",
    #         "https://www.bensbites.co/rss",
    #         "https://tldr.tech/ai/rss",
    #         ]
    
    # regex pattern with word boundaries for all keywords
    pattern = re.compile(r'\b(' + '|'.join(map(re.escape, keywords)) + r')\b', re.IGNORECASE)
    
    cutoff = datetime.now() - timedelta(days=3)
    
    all_results = []  # container for results
    
    for url in urls:
        feed = feedparser.parse(url)
        top_ten = feed.entries[:15]
        feed_results = []
    
    
        for e in top_ten:
            if "published_parsed" not in e:
                continue
    
            pub_date = datetime.fromtimestamp(time.mktime(e.published_parsed))
    
            if pub_date > cutoff and (pattern.search(e.title or "") or pattern.search(e.summary or "")):
            #if pub_date > cutoff:
                feed_results.append({
                    "title": e.title,
                    "link": e.link,
                    "published": e.published,
                    "summary": e.get("summary", ""),
                    "source": feed.feed.get("title", url)
                })
    
        if feed_results:
            #all_results[url] = feed_results
            all_results.extend(feed_results)

    return all_results