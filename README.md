# RSS to Kindle

Automatically fetches RSS feeds, generates AI summaries using Google Gemini 2.0 Flash Lite (free), and sends them to your Kindle.

## Setup

1. Fork this repository
2. Get a free Gemini API key from https://aistudio.google.com/apikey
3. Add these secrets in GitHub Settings → Secrets and variables → Actions:
   - `GEMINI_API_KEY`: Your Google Gemini API key (free, no credit card needed)
   - `KINDLE_EMAIL`: Your Kindle email address (e.g., username@kindle.com)
   - `SMTP_HOST`: Your email SMTP server (e.g., smtp.gmail.com)
   - `SMTP_PORT`: SMTP port (e.g., 587)
   - `SMTP_USER`: Your email address
   - `SMTP_PASSWORD`: Your email password or app-specific password

4. Add your email to Kindle's approved sender list:
   - Go to Amazon → Manage Your Content and Devices → Preferences → Personal Document Settings
   - Add your sender email to "Approved Personal Document E-mail List"

## Configuration

Edit `feeds.txt` to add/remove RSS feeds (one per line).

## Schedule

Runs daily at 8 AM UTC. Modify `.github/workflows/rss-to-kindle.yml` to change schedule.
