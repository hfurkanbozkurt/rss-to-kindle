#!/usr/bin/env python3
import feedparser
import google.generativeai as genai
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime, timedelta
import os
import requests
from bs4 import BeautifulSoup

def sanitize_html(html_content):
    """Sanitize HTML for Kindle compatibility - only allow safe tags and attributes"""
    if not html_content:
        return ''

    soup = BeautifulSoup(html_content, 'html.parser')

    # Remove all script, style, svg, button, form tags
    for tag in soup(['script', 'style', 'svg', 'button', 'form', 'iframe', 'noscript']):
        tag.decompose()

    # Allowed tags and attributes
    allowed_tags = {'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'a', 'strong', 'em', 'b', 'i', 'blockquote', 'pre', 'code', 'br', 'hr', 'div', 'span'}
    allowed_attrs = {'href', 'src', 'alt', 'title', 'id'}

    # Remove disallowed tags and attributes
    for tag in soup.find_all(True):
        if tag.name not in allowed_tags:
            tag.unwrap()
        else:
            # Remove disallowed attributes
            attrs = dict(tag.attrs)
            for attr in attrs:
                if attr not in allowed_attrs:
                    del tag[attr]

    return str(soup)

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

def get_digest_summary(entries):
    try:
        genai.configure(api_key=os.environ.get('GEMINI_API_KEY'))
        model = genai.GenerativeModel('gemini-2.5-pro')

        articles_text = "\n\n".join([
            f"Title: {e['title']}\nSource: {e['source']}\nContent: {e['content'][:2000]}"
            for e in entries
        ])

        prompt = f"""Analyze this collection of AI/ML research articles and provide a concise digest summary that:
1. Identifies the main themes and trends across all articles
2. Highlights the most significant findings or innovations
3. Notes any connections or patterns between different articles

Articles:
<Articles>
{articles_text}
</Articles>

Provide an engaging 2-3 paragraph summary of the entire digest."""

        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Digest summary generation failed: {str(e)[:50]}")
        return "Summary unavailable"

def fetch_new_entries():
    with open('feeds.txt', 'r') as f:
        feeds = [line.strip() for line in f if line.strip()]

    print(f"Processing {len(feeds)} feeds...")

    # Get articles from yesterday 2am to today 2am UTC
    from datetime import timezone
    now = datetime.now(timezone.utc)
    cutoff_start = now.replace(hour=2, minute=0, second=0, microsecond=0) - timedelta(days=1)
    cutoff_end = now.replace(hour=2, minute=0, second=0, microsecond=0)

    entries = []

    for feed_url in feeds:
        print(f"Fetching: {feed_url}")
        feed = feedparser.parse(feed_url)

        feed_count = 0
        for entry in feed.entries:
            pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc) if hasattr(entry, 'published_parsed') and entry.published_parsed else datetime.now(timezone.utc)

            if pub_date >= cutoff_start and pub_date < cutoff_end:
                print(f"  New article: {entry.title[:50]}...")

                # Try to get full article content
                full_content = scrape_article(entry.link)
                if not full_content:
                    # Fallback to RSS content
                    full_content = entry.get('summary', entry.get('description', entry.get('content', [{}])[0].get('value', '')))

                # Sanitize HTML for Kindle
                full_content = sanitize_html(full_content.strip() if full_content else '')

                entries.append({
                    'id': entry.get('id', entry.link),
                    'title': entry.title,
                    'link': entry.link,
                    'content': full_content,
                    'source': feed.feed.title
                })
                feed_count += 1

        print(f"  Total: {len(feed.entries)} | Selected: {feed_count}")

    print(f"Total new articles: {len(entries)}")
    return entries

def create_html(entries, digest_summary):
    """Create Kindle-optimized HTML - very simple structure that Kindle conversion actually handles"""

    # Simple, flat structure that Kindle's email converter can handle
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>AI Research Digest - {datetime.now().strftime('%Y-%m-%d')}</title>
</head>
<body>

<h1>AI Research Digest</h1>
<p><strong>{datetime.now().strftime('%B %d, %Y')}</strong></p>
<p>{len(entries)} articles</p>

<h2>Digest Summary</h2>
<p>{digest_summary}</p>

<h2>Table of Contents</h2>
<ol>
"""

    # Add TOC entries
    for i, entry in enumerate(entries, 1):
        html += f'<li><a href="#article{i}">{entry["title"]}</a> - {entry["source"]}</li>\n'

    html += "</ol>\n<hr>\n\n"

    # Add articles with simple structure
    for i, entry in enumerate(entries, 1):
        html += f"""
<h2 id="article{i}">{i}. {entry['title']}</h2>
<p><strong>Source:</strong> {entry['source']}</p>
<p><strong>Link:</strong> <a href="{entry['link']}">{entry['link']}</a></p>
<hr>
{entry['content']}
<hr>

"""

    html += "</body></html>"
    return html

def create_epub(entries, digest_summary):
    """Create a proper EPUB file for Kindle - this is what actually works well"""
    try:
        from ebooklib import epub
    except ImportError:
        print("ERROR: ebooklib not installed. Run: pip install ebooklib")
        return None

    book = epub.EpubBook()

    # Set metadata
    book.set_identifier(f'ai-digest-{datetime.now().strftime("%Y%m%d")}')
    book.set_title(f'AI Research Digest - {datetime.now().strftime("%Y-%m-%d")}')
    book.set_language('en')
    book.add_author('RSS to Kindle')

    # Add cover if it exists
    cover_path = 'cover.jpg' if os.path.exists('cover.jpg') else 'cover.jpeg'
    if os.path.exists(cover_path):
        with open(cover_path, 'rb') as f:
            book.set_cover('cover.jpg', f.read())

    # Create intro page
    intro = epub.EpubHtml(title='Introduction',
                          file_name='intro.xhtml',
                          lang='en')
    intro.content = f'''
    <html><body>
    <h1>AI Research Digest</h1>
    <p><strong>{datetime.now().strftime('%B %d, %Y')}</strong></p>
    <p>Compiled by RSS to Kindle</p>
    <p>{len(entries)} articles in this digest</p>
    <h2>Digest Summary</h2>
    <p>{digest_summary}</p>
    </body></html>
    '''
    book.add_item(intro)

    # Create chapters for each article
    chapters = []
    for i, entry in enumerate(entries, 1):
        chapter = epub.EpubHtml(title=entry['title'],
                                file_name=f'article_{i}.xhtml',
                                lang='en')

        chapter.content = f'''
        <html><body>
        <h1>{entry['title']}</h1>
        <p><strong>Source:</strong> {entry['source']}</p>
        <p><a href="{entry['link']}">Read online</a></p>
        <hr/>
        {entry['content']}
        </body></html>
        '''

        book.add_item(chapter)
        chapters.append(chapter)

    # Define Table of Contents - flat list, not nested
    book.toc = [intro] + chapters

    # Add navigation files
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # Define spine (reading order)
    book.spine = ['nav', intro] + chapters

    # Generate EPUB file
    filename = f'ai_digest_{datetime.now().strftime("%Y%m%d")}.epub'
    epub.write_epub(filename, book)

    return filename

def send_to_kindle(file_path, is_epub=False):
    """Send file to Kindle via email"""
    print(f"Preparing email to {os.environ['KINDLE_EMAIL']}")
    msg = MIMEMultipart()
    msg['From'] = os.environ['SMTP_USER']
    msg['To'] = os.environ['KINDLE_EMAIL']
    msg['Subject'] = f"AI Research Digest - {datetime.now().strftime('%Y-%m-%d')}"

    # Read and attach file
    with open(file_path, 'rb') as f:
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(f.read())
        encoders.encode_base64(part)

        filename = os.path.basename(file_path)
        part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
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
    import sys
    entries = fetch_new_entries()

    if entries:
        # Generate digest summary
        print("Generating digest summary...")
        digest_summary = get_digest_summary(entries)

        # Try to create EPUB (best for Kindle), fallback to HTML
        epub_file = create_epub(entries, digest_summary)

        if epub_file:
            print(f"Created EPUB: {epub_file}")
            if '--dry-run' in sys.argv:
                print(f"EPUB file ready to test: {epub_file}")
            else:
                send_to_kindle(epub_file, is_epub=True)
                print(f"Sent EPUB with {len(entries)} articles to Kindle")
        else:
            # Fallback to HTML
            print("Falling back to HTML (install ebooklib for better results)")
            html = create_html(entries, digest_summary)
            if '--dry-run' in sys.argv:
                with open('digest.html', 'w', encoding='utf-8') as f:
                    f.write(html)
                print(f"Generated digest.html with {len(entries)} articles")
            else:
                with open('digest.html', 'w', encoding='utf-8') as f:
                    f.write(html)
                send_to_kindle('digest.html')
                print(f"Sent HTML with {len(entries)} articles to Kindle")
    else:
        print("No new articles")