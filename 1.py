import os
import re
import requests
import mimetypes
import pandas as pd
import os
import datetime
import re
import shutil
import subprocess

from PIL import Image
from io import BytesIO

from wordpress_xmlrpc import Client, WordPressPost
from wordpress_xmlrpc.methods import media, posts
from wordpress_xmlrpc.compat import xmlrpc_client
from wordpress_xmlrpc.methods.posts import NewPost

# Define CustomField class yourself because it’s missing in your installed version
class CustomField(object):
    def __init__(self, key, value):
        self.key = key
        self.value = value

# === Meta Description Generation ===
def generate_meta_description(title):
    with open("openrouter_key.txt", "r") as f:
        api_key = f.read().strip()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://yourdomain.com",
        "Content-Type": "application/json"
    }

    prompt = (
        f"Write a unique, concise, and SEO-optimized meta description of about 80 characters for a UK tutoring blog post by Tutor GP titled '{title}'. Include relevant keywords naturally without keyword stuffing. Craft the description to sound human, clearly conveying the blog’s value to both search engines and readers."
    )

    body = {
        "model": "mistralai/mistral-7b-instruct",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7
    }

    response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=body)
    response.raise_for_status()
    result = response.json()

    description = result["choices"][0]["message"]["content"].strip()
    description = description.replace('\n', ' ').strip('"').strip()
    
    cta = " Book your free consultation at: https://tutorgp.com/contact-us."
    max_length = 220 - len(cta)

    if len(description) > max_length:
        description = description[:max_length-3].rstrip() + "..."

    description = description + cta
    return description

# === Focus Keyword Generation ===
def generate_focus_keyword(title):
    with open("openrouter_key.txt", "r") as f:
        api_key = f.read().strip()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://yourdomain.com",
        "Content-Type": "application/json"
    }

    prompt = (
        f"Generate a short, relevant, and SEO-optimized focus keyword or key phrase (2 to 4 words) "
        f"for the Tutor GP, a UK tutoring blog post titled '{title}'. The keyword should reflect the main topic "
        f"and be suitable for Rank Math SEO plugin focus keyword field."
    )

    body = {
        "model": "mistralai/mistral-7b-instruct",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7
    }

    response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=body)
    response.raise_for_status()
    result = response.json()

    keyword = result["choices"][0]["message"]["content"].strip().strip('"')
    return keyword

# === Emoji Detection ===
def contains_emoji(s):
    emoji_pattern = re.compile(
        "[" 
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags (iOS)
        "\U00002700-\U000027BF"  # Dingbats
        "\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
        "\U00002600-\U000026FF"  # Misc symbols
        "]+", flags=re.UNICODE)
    return bool(emoji_pattern.search(s))

# === Heading Detection Functions ===
class HeadingTracker:
    def __init__(self):
        self.detected_headings = set()
        self.count = 0

    def _matches_bold_enclosed(self, line):
        # Match anything enclosed in **...** (up to 16 words, no trailing period)
        enclosed = re.findall(r'\*\*(.+?)\*\*', line)
        for h in enclosed:
            h = h.strip()
            if len(h.split()) <= 16 and not h.endswith('.'):
                bolded = f"**{h}**"
                if bolded not in self.detected_headings:
                    self.detected_headings.add(bolded)
                    return True
        return False

    def _matches_bold_start(self, line):
        # Line starts with **
        if line.startswith('**'):
            h = line[2:].strip()
            if len(h.split()) <= 16 and not h.endswith('.'):
                bolded = f"**{h}**"
                if bolded not in self.detected_headings:
                    self.detected_headings.add(bolded)
                    return True
        return False

    def _matches_bold_end(self, line):
        # Line ends with **
        if line.endswith('**'):
            h = line[:-2].strip()
            if len(h.split()) <= 16 and not h.endswith('.'):
                bolded = f"**{h}**"
                if bolded not in self.detected_headings:
                    self.detected_headings.add(bolded)
                    return True
        return False

    def _matches_emoji_line(self, line):
        # Line with emoji (up to 16 words, no trailing period)
        if contains_emoji(line):
            if len(line.split()) <= 16 and not line.endswith('.'):
                bolded = f"**{line}**"
                if bolded not in self.detected_headings:
                    self.detected_headings.add(bolded)
                    return True
        return False

    def _matches_colon_heading(self, line):
        if ':' in line and not line.endswith('.'):
            word_count = len(line.split())
            # Only allow short colon-style phrases like "Top Tips: Study Better"
            if word_count <= 10:
                before_colon = line.split(':')[0].strip()
                after_colon = line.split(':', 1)[1].strip()

                # Must not be a full sentence
                if not after_colon.endswith('.') and after_colon and not any(p in after_colon for p in [' is ', ' are ', ' have ', ' has ']):
                    if line not in self.detected_headings:
                        self.detected_headings.add(line)
                        return True
        return False

    def _matches_title_case(self, line):
        word_count = len(line.split())
        return (
            line.lower() == line.title().lower() and
            word_count <= 12 and
            not line.endswith('.')
    )


    def get_heading_level(self, line):
        line = line.strip()
        word_count = len(line.split())

        # 1. AI-generated Markdown-style headings
        if line.startswith("#### "):
            return 'h4'
        elif line.startswith("### "):
            return 'h3'
        elif line.startswith("## "):
            return 'h2'

        # Check all heading patterns
        if (
            self._matches_bold_enclosed(line) or
            self._matches_bold_start(line) or
            self._matches_bold_end(line) or
            self._matches_emoji_line(line) or
            self._matches_colon_heading(line) or
            line.startswith("- ") or
            line.startswith("• ") or
            (callable(self._matches_title_case) and self._matches_title_case(line)) or
            (line.lower() == line.title().lower() and word_count <= 12) or
            (word_count <= 5 and not line.endswith('.'))
        ):
            self.count += 1

            if self.count <= 4:
                return 'h2'
            elif self.count <= 6:
                return 'h3'
            elif self.count <= 9:
                return 'h4'
            else:
                return 'h5'
        else:
            return None

# === Format HTML Blocks ===
def format_content_with_html_blocks(content, heading_tracker):
    lines = content.strip().split('\n')
    output = []
    current_tag = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        heading_level = heading_tracker.get_heading_level(line)

        if heading_level:
            output.append(f"<{heading_level}>{line.strip('**')}</{heading_level}>")
            output.append("<p></p>")  # placeholder paragraph after heading
        else:
            output.append(f"<p>{line}</p>")

    return '\n'.join(output)

# === Generate blog content from title ===
def generate_blog_from_title(title):
    with open("openrouter_key.txt", "r") as f:
        api_key = f.read().strip()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://yourdomain.com",
        "Content-Type": "application/json"
    }

    prompt = (
        f"Write a blog post between 1000-1200 words, fully optimised for a UK-based tutoring business called Tutor GP '{title}', targeted at students, parents, tutors, or teachers. The article should be engaging, informative, and easy to read, written in a friendly, professional tone. Tailor the content to one or more of the following audiences students, parents, tutors, or teachers, depending on the title. Use a clear, structured format with descriptive, catchy headings and subheadings that include relevant emojis where appropriate. Do not label them as headings or subheadings. Avoid fluff or filler and ensure every paragraph adds meaningful value. Incorporate practical tips, real-life examples, insights, and actionable advice that the reader can apply immediately. Write in active voice, use short and concise sentences, and maintain a natural, conversational flow. Language should be human-like and accessible and avoid jargon and overly technical vocabulary. Integrate natural sounding keywords relevant to tutoring and education in the UK, such as academic success, study skills, personalised learning, online tutoring, GCSE Maths Tuition, GCSE Science Tuition, A-Level Physics Tuition, learning strategies, revision tips, student motivation, and parent support.The content you write should aligns with Google's E-E-A-T standards — Experience, Expertise, Authoritativeness, and Trustworthiness. The content should be Well-researched and accurate, showcasing real-world experience or practical insights where applicable. Expertly written, reflecting deep knowledge of the topic and using correct terminology. Authoritative, backed by credible sources, data, or personal credentials to establish reliability. Trustworthy, with a clear, honest tone that provides value to the reader and builds confidence in the information. Ensure the post is engaging, informative, and SEO-optimized while maintaining a professional and helpful tone throughout. Content Structure: Use Markdown-style headings. Use `##` for H2 (main sections), Use `###` for H3 (subsections), Use `####` for H4 (if needed), Use bullet points or numbered lists where appropriate."
        f"At the end of the article, include a section titled FAQs ❓ with at least eight relevant, concise, and genuinely helpful questions and answers that directly relate to the topic. Add Question next to the questions and Answer next to the answers. Also add relavent emojis in each question. Dont use ** before or after  ** in Questions and Answers. Use British English spelling and phrasing throughout. Avoid including author bios, promotional content, or generic statements. The goal is to provide clear value, inspire trust, and encourage reflection or practical action from the reader. Include headings and subheadings as needed. Each question should start with Q: and each answer should start with A:"

    )

    body = {
        "model": "mistralai/mistral-7b-instruct",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7
    }

    response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=body)
    response.raise_for_status()
    result = response.json()

    return result["choices"][0]["message"]["content"]

# === Generate image with OpenRouter ===
def generate_image(prompt):
    with open("openrouter_key.txt", "r") as f:
        api_key = f.read().strip()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://yourdomain.com",
        "Content-Type": "application/json"
    }

    body = {
        "model": "openai/dalle-mini",
        "prompt": prompt,
        "n": 1,
        "size": "512x512"
    }

    response = requests.post("https://openrouter.ai/api/v1/images/generations", headers=headers, json=body)
    if response.status_code != 200:
        print(f"Image generation failed: {response.status_code} - {response.text}")
        return None

    result = response.json()
    return result["data"][0]["url"] if "data" in result and len(result["data"]) > 0 else None


# === Read Excel and Process Posts ===
def read_excel_and_process_posts(filepath):
    df = pd.read_excel(filepath)

    for index, row in df.iterrows():
        try:
            title = str(row.iloc[0]).strip()
            category = [row.iloc[1]] if pd.notna(row.iloc[1]) else ["Uncategorized"]
            tags = [tag.strip() for tag in str(row.iloc[2]).split(",")] if pd.notna(row.iloc[2]) else []
            manual_image = str(row.iloc[3]).strip() if pd.notna(row.iloc[3]) else ""

            print(title)

            content = generate_blog_from_title(title)
            content = content.replace("**", "")  # remove double asterisks from content
            content = content.replace("Title:", "").strip()  # Remove all occurrences of "Title:" and strip whitespace

            tracker = HeadingTracker()
            formatted_content = format_content_with_html_blocks(content, tracker)

            # === Clean and format content ===
            lines = content.splitlines()
            formatted_lines = []
            in_list = False  # Track if we're in a <ul>
            skip_next = False  # For skipping answer line after a question
            tracker = HeadingTracker()

            for i, line in enumerate(lines):
                line = line.strip()
                if not line:
                    continue

                if skip_next:
                    skip_next = False
                    continue

                # FAQs Section Title
                if line.lower().startswith("faqs"):
                    if in_list:
                        formatted_lines.append("</ul>")
                        in_list = False
                    formatted_lines.append("<h2>FAQs ❓</h2>")
                    continue

                # Questions and Answers - wrap each pair in its own <ul> (no bullets)
                if re.match(r"^(question:|ques:|q:)", line, re.IGNORECASE):
                    # Remove Q-labels and leading bullet/marker symbols
                    clean_question = re.sub(r"^(question:|ques:|q:)?\s*[•\-\*]?\s*", "", line, flags=re.IGNORECASE).strip()
    
                    if in_list:
                        formatted_lines.append("</ul>")
                        in_list = False

                    formatted_lines.append('<ul style="list-style-type: none; padding-left: 0;">')
                    formatted_lines.append(f"<li><strong>{clean_question}</strong></li>")

                    # Check for answer in next line
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        if re.match(r"^(answer:|ans:|a:)", next_line, re.IGNORECASE):
                            # Remove A-labels and leading bullet/marker symbols
                            clean_answer = re.sub(r"^(answer:|ans:|a:)?\s*[•\-\*]?\s*", "", next_line, flags=re.IGNORECASE).strip()
                            formatted_lines.append(f"<li>{clean_answer}</li>")
                            skip_next = True

                    formatted_lines.append("</ul>")
                    in_list = False  # reset after closing Q&A list
                    continue

                # Bullet points
                if line.startswith("- ") or line.startswith("* "):
                    if not in_list:
                        formatted_lines.append("<ul>")
                        in_list = True
                    formatted_lines.append(f"<li>{line[2:].strip()}</li>")
                    continue
                else:
                    if in_list:
                        formatted_lines.append("</ul>")
                        in_list = False

                # Headings
                heading_level = tracker.get_heading_level(line)
                if heading_level:
                    clean_line = re.sub(r'^[#\*\"\•\-\\\|\~\=\s]+|[#\*\"\•\\\|\-\~\=\s]+$', '', line).strip()
                    formatted_lines.append(f"<{heading_level}>{clean_line}</{heading_level}>")
                else:
                    # Paragraph
                    formatted_lines.append(f"<p>{line}</p>")

            # Final cleanup
            if in_list:
                formatted_lines.append("</ul>")

            formatted_content = "\n".join(formatted_lines)

            # === Generate meta info first ===
            meta_description = generate_meta_description(title)
            focus_keyword = generate_focus_keyword(title)

            # === Handle image (local or AI-generated) ===
            featured_image_id = None
            img_html = ""

            if manual_image and os.path.isfile(manual_image):
                print(f"Using local image: {manual_image}")
                featured_image_id = upload_local_image_to_wordpress(manual_image, focus_keyword, meta_description)
                if featured_image_id:
                    media_details = wp.call(media.GetMediaItem(featured_image_id))
                    img_url = media_details.link
                    img_html = f'<img src="{img_url}" alt="{focus_keyword}" width="960" height="570" />'
            else:
                print("No valid local image found, attempting AI-generated image...")
                image_prompt = title + " tutoring education illustration"
                image_url = generate_image(image_prompt)
                if image_url:
                    featured_image_id = upload_image_to_wordpress(image_url)
                    if featured_image_id:
                        media_details = wp.call(media.GetMediaItem(featured_image_id))
                        img_url = media_details.link
                        img_html = f'<img src="{img_url}" alt="{focus_keyword}" width="960" height="570" />'
                else:
                    print("No image generated or provided; skipping image upload.")

            # === Combine image + content ===
            post_content = img_html + formatted_content
            

        except Exception as e:
            print(f"Failed processing row {index}: {e}")

# Paths for your GitHub repo
REPO_PATH = r"C:\Users\fariz\Desktop\AI Blog Script Writer\Web 2.0 blog publisher\blogs"  # adjust to your local cloned repo path
IMAGES_FOLDER = os.path.join(REPO_PATH, "assets", "images")
POSTS_FOLDER = os.path.join(REPO_PATH, "_posts")

# copy_image_to_repo
def copy_image_to_repo(image_full_path):
    if not os.path.isfile(image_full_path):
        print(f"Image file not found: {image_full_path}")
        return None

    # Get image filename
    image_filename = os.path.basename(image_full_path)
    dest_path = os.path.join(IMAGES_FOLDER, image_filename)

    # Copy image to assets/images in repo
    shutil.copy(image_full_path, dest_path)
    print(f"Copied image to {dest_path}")

    # Return relative image path for markdown
    return f"/assets/images/{image_filename}"

def slugify(text):
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"\s+", "-", text)
    return text.strip("-")

def generate_markdown_file(title, date, content, image_markdown, filename_slug):
    post_filename = f"{date}-{filename_slug}.md"
    post_filepath = os.path.join(POSTS_FOLDER, post_filename)

    markdown = f"""---
layout: post
title: "{title}"
date: {date}
---

{image_markdown}

{content}
"""

    with open(post_filepath, "w", encoding="utf-8") as f:
        f.write(markdown)
    print(f"Saved markdown post to {post_filepath}")

def read_excel_and_process_posts(filepath):
    df = pd.read_excel(filepath)

    for index, row in df.iterrows():
        try:
            title = str(row.iloc[0]).strip()
            category = [row.iloc[1]] if pd.notna(row.iloc[1]) else ["Uncategorized"]
            tags = [tag.strip() for tag in str(row.iloc[2]).split(",")] if pd.notna(row.iloc[2]) else []
            manual_image = str(row.iloc[3]).strip() if pd.notna(row.iloc[3]) else ""

            print(f"Processing: {title}")

            # Your blog content generation (you can keep your HeadingTracker and formatting here)
            content = generate_blog_from_title(title)
            content = content.replace("**", "").replace("Title:", "").strip()

            # Use your existing content formatting (simplified here)
            formatted_content = content  # Or your formatting function calls here

            # Generate slug and date
            date = datetime.date.today().isoformat()  # e.g. 2025-07-03
            filename_slug = slugify(title)

            # Handle image copy
            image_md = ""
            if manual_image and os.path.isfile(manual_image):
                relative_image_path = copy_image_to_repo(manual_image)
                if relative_image_path:
                    image_md = f"![{title}]({relative_image_path})"

            # Generate markdown file
            generate_markdown_file(title, date, formatted_content, image_md, filename_slug)

        except Exception as e:
            print(f"Failed processing row {index}: {e}")

def git_commit_and_push(repo_path, commit_message="Auto-publish blog post"):
    try:
        # Run git add
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)

        # Run git commit
        subprocess.run(["git", "commit", "-m", commit_message], cwd=repo_path, check=True)

        # Run git push
        subprocess.run(["git", "push"], cwd=repo_path, check=True)

        print("✅ Blog post pushed to GitHub!")
    except subprocess.CalledProcessError as e:
        print(f"❌ Git command failed: {e}")

def git_commit_and_push(repo_path):
    try:
        os.chdir(repo_path)
        os.system("git add .")
        os.system('git commit -m "Added new blog post and image"')
        os.system("git push")
        print("✅ Changes pushed to GitHub!")
    except Exception as e:
        print(f"❌ Git push failed: {e}")

if __name__ == "__main__":
    excel_path = r"C:\Users\fariz\Desktop\AI Blog Script Writer\Web 2.0 blog publisher\blogs\blog ideas.xlsx"
    read_excel_and_process_posts(excel_path)

# Call this at the end of your script
git_commit_and_push(REPO_PATH)
