#!/usr/bin/env python3
import feedparser
import google.generativeai as genai
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime, timedelta
import os
import json
import requests
from bs4 import BeautifulSoup

def load_sent_items():
    if os.path.exists('sent_items.json'):
        with open('sent_items.json', 'r') as f:
            return json.load(f)
    return {}

def save_sent_items(sent_items):
    with open('sent_items.json', 'w') as f:
        json.dump(sent_items, f)

def scrape_article(url):
    try:
        print(f"    Scraping full article...")
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Remove unwanted elements
        for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'iframe', 'noscript']):
            tag.decompose()
        
        # Try multiple selectors in order of preference
        selectors = [
            ('article', {}),
            ('main', {}),
            ('div', {'class': ['post-content', 'article-content', 'entry-content', 'content', 'post', 'article-body']}),
            ('div', {'id': ['content', 'main-content', 'article', 'post']}),
        ]
        
        article = None
        for tag, attrs in selectors:
            if attrs:
                for key, values in attrs.items():
                    for value in values:
                        article = soup.find(tag, {key: lambda x: x and value in x.lower() if x else False})
                        if article:
                            break
                    if article:
                        break
            else:
                article = soup.find(tag)
            if article:
                break
        
        if article:
            # Get text content with basic formatting
            paragraphs = article.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'ul', 'ol', 'blockquote', 'pre'])
            if paragraphs:
                content = '\n'.join([str(p) for p in paragraphs])
                return content if len(content) > 200 else None
        
        return None
    except Exception as e:
        print(f"    Failed to scrape: {str(e)[:50]}")
        return None

def get_summary(title, content):
    try:
        genai.configure(api_key=os.environ.get('GEMINI_API_KEY'))
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        prompt = f"""Analyze this AI/ML research article and provide a concise summary that captures:
1. The core innovation or finding
2. Why it matters (practical implications or theoretical significance)
3. Any notable limitations or caveats

Title: {title}

Content: {content[:3000]}

Provide a clear, engaging summary in 3-4 sentences that would help a technical reader decide if they should read the full article."""
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"    Summary generation failed: {str(e)[:50]}")
        return "Summary unavailable"

def fetch_new_entries():
    with open('feeds.txt', 'r') as f:
        feeds = [line.strip() for line in f if line.strip()]
    
    print(f"Processing {len(feeds)} feeds...")
    sent_items = load_sent_items()
    cutoff = datetime.now() - timedelta(days=1)
    entries = []
    
    for feed_url in feeds:
        print(f"Fetching: {feed_url}")
        feed = feedparser.parse(feed_url)
        print(f"  Found {len(feed.entries)} entries")
        
        for entry in feed.entries:
            entry_id = entry.get('id', entry.link)
            if entry_id in sent_items:
                continue
            
            pub_date = datetime(*entry.published_parsed[:6]) if hasattr(entry, 'published_parsed') and entry.published_parsed else datetime.now()
            if pub_date < cutoff:
                continue
            
            print(f"  New article: {entry.title[:50]}...")
            
            # Try to get full article content
            full_content = scrape_article(entry.link)
            if not full_content:
                # Fallback to RSS content
                full_content = entry.get('summary', entry.get('description', entry.get('content', [{}])[0].get('value', '')))
            
            full_content = full_content.strip() if full_content else ''
            summary = get_summary(entry.title, full_content)
            
            entries.append({
                'id': entry_id,
                'title': entry.title,
                'link': entry.link,
                'summary': summary,
                'content': full_content,
                'source': feed.feed.title
            })
            sent_items[entry_id] = datetime.now().isoformat()
    
    save_sent_items(sent_items)
    print(f"Total new articles: {len(entries)}")
    return entries

def create_html(entries):
    toc = '<h2>Table of Contents</h2><ol>'
    for i, entry in enumerate(entries, 1):
        toc += f'<li><a href="#article{i}">{entry["title"]}</a></li>'
    toc += '</ol><mbp:pagebreak/>'
    
    html = f"""<html><head><meta charset="utf-8"><title>AI Research Digest - {datetime.now().strftime('%Y-%m-%d')}</title>
<style>
body {{ font-family: serif; line-height: 1.6; margin: 20px; }}
.summary {{ background: #f5f5f5; padding: 10px; margin: 10px 0; border-left: 3px solid #333; }}
.full-text {{ margin-top: 15px; }}
a {{ color: #0066cc; }}
</style>
</head><body>
<h1>AI Research Digest</h1>
<p><em>{datetime.now().strftime('%B %d, %Y')}</em></p>
{toc}
"""
    for i, entry in enumerate(entries, 1):
        html += f"""
<mbp:pagebreak/>
<div id="article{i}">
<h2>{entry['title']}</h2>
<p><strong>Source:</strong> {entry['source']}</p>
<div class="summary">
<p><strong>AI Summary:</strong> {entry['summary']}</p>
</div>
<p><a href="{entry['link']}">View online</a></p>
<div class="full-text">
<h3>Full Article</h3>
{entry['content']}
</div>
</div>
"""
    html += "</body></html>"
    return html

def send_to_kindle(html_content):
    print(f"Preparing email to {os.environ['KINDLE_EMAIL']}")
    msg = MIMEMultipart()
    msg['From'] = os.environ['SMTP_USER']
    msg['To'] = os.environ['KINDLE_EMAIL']
    msg['Subject'] = f"AI Research Digest - {datetime.now().strftime('%Y-%m-%d')}"
    
    part = MIMEBase('application', 'octet-stream')
    part.set_payload(html_content.encode('utf-8'))
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', f'attachment; filename="digest.html"')
    msg.attach(part)
    
    print(f"Connecting to {os.environ['SMTP_HOST']}:{os.environ['SMTP_PORT']}")
    with smtplib.SMTP(os.environ['SMTP_HOST'], int(os.environ['SMTP_PORT'])) as server:
        server.starttls()
        print("Logging in...")
        server.login(os.environ['SMTP_USER'], os.environ['SMTP_PASSWORD'])
        print("Sending email...")
        server.send_message(msg)
    print("Email sent successfully!")

if __name__ == '__main__':
    entries = fetch_new_entries()
    if entries:
        html = create_html(entries)
        send_to_kindle(html)
        print(f"Sent {len(entries)} articles to Kindle")
    else:
        print("No new articles")
