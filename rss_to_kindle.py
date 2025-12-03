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

def load_sent_items():
    if os.path.exists('sent_items.json'):
        with open('sent_items.json', 'r') as f:
            return json.load(f)
    return {}

def save_sent_items(sent_items):
    with open('sent_items.json', 'w') as f:
        json.dump(sent_items, f)

def get_summary(title, content):
    genai.configure(api_key=os.environ['GEMINI_API_KEY'])
    model = genai.GenerativeModel('gemini-2.0-flash-lite')
    prompt = f"""Analyze this AI/ML research article and provide a concise summary that captures:
1. The core innovation or finding
2. Why it matters (practical implications or theoretical significance)
3. Any notable limitations or caveats

Title: {title}

Content: {content[:3000]}

Provide a clear, engaging summary in 3-4 sentences that would help a technical reader decide if they should read the full article."""
    response = model.generate_content(prompt)
    return response.text

def fetch_new_entries():
    with open('feeds.txt', 'r') as f:
        feeds = [line.strip() for line in f if line.strip()]
    
    sent_items = load_sent_items()
    cutoff = datetime.now() - timedelta(days=1)
    entries = []
    
    for feed_url in feeds:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries:
            entry_id = entry.get('id', entry.link)
            if entry_id in sent_items:
                continue
            
            pub_date = datetime(*entry.published_parsed[:6]) if hasattr(entry, 'published_parsed') and entry.published_parsed else datetime.now()
            if pub_date < cutoff:
                continue
            
            content = entry.get('summary', entry.get('description', entry.get('content', [{}])[0].get('value', '')))
            summary = get_summary(entry.title, content)
            
            entries.append({
                'id': entry_id,
                'title': entry.title,
                'link': entry.link,
                'summary': summary,
                'content': content,
                'source': feed.feed.title
            })
            sent_items[entry_id] = datetime.now().isoformat()
    
    save_sent_items(sent_items)
    return entries

def create_html(entries):
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
"""
    for entry in entries:
        html += f"""
<hr>
<h2>{entry['title']}</h2>
<p><strong>Source:</strong> {entry['source']}</p>
<div class="summary">
<p><strong>AI Summary:</strong> {entry['summary']}</p>
</div>
<p><a href="#{entry['id'][:8]}">Read full text below</a> | <a href="{entry['link']}">View online</a></p>
<div class="full-text" id="{entry['id'][:8]}">
<h3>Full Article</h3>
{entry['content']}
</div>
"""
    html += "</body></html>"
    return html

def send_to_kindle(html_content):
    msg = MIMEMultipart()
    msg['From'] = os.environ['SMTP_USER']
    msg['To'] = os.environ['KINDLE_EMAIL']
    msg['Subject'] = f"AI Research Digest - {datetime.now().strftime('%Y-%m-%d')}"
    
    part = MIMEBase('application', 'octet-stream')
    part.set_payload(html_content.encode('utf-8'))
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', f'attachment; filename="digest.html"')
    msg.attach(part)
    
    with smtplib.SMTP(os.environ['SMTP_HOST'], int(os.environ['SMTP_PORT'])) as server:
        server.starttls()
        server.login(os.environ['SMTP_USER'], os.environ['SMTP_PASSWORD'])
        server.send_message(msg)

if __name__ == '__main__':
    entries = fetch_new_entries()
    if entries:
        html = create_html(entries)
        send_to_kindle(html)
        print(f"Sent {len(entries)} articles to Kindle")
    else:
        print("No new articles")
