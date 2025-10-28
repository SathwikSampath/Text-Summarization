import os
import re
import yt_dlp
import google.generativeai as genai
import requests
import json
import time  # ✅ 1. Import the time library

# --- Configuration ---

# 1. Read all links from your file
file_path = "./youtube_video_links.txt"
try:
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read().strip()
    raw_links = [link.strip() for link in re.split('[,\n]', content) if link.strip()]
    total_links = len(raw_links)
    print(f"Successfully read {total_links} links from file.")
except FileNotFoundError:
    print(f"ERROR: Link file not found at {file_path}")
    # Stop the script if the link file doesn't exist
    raw_links = []
    total_links = 0

# -----------------------------------------------------------------
# ✅✅✅ BATCH CONTROL SECTION ✅✅✅
# -----------------------------------------------------------------
# Manually change these values for each run.

START_INDEX = 14
END_INDEX = 20  # Process 100 links in this batch

# -----------------------------------------------------------------

# 3. Define the SINGLE output file (it will be appended to)
jsonl_save_path = "./training_data.jsonl"

# 4. Define other paths and settings
subtitle_lang = "te"
cookies_file_path = "./www.youtube.com_cookies.txt"
# ✅ IMPORTANT: Replace with your actual API key
genai.configure(api_key="AIzaSyCD4HDKZmQnqygedyutlNo3JusWDamIZCo")

# --- Create the directory for the output file if it doesn't exist ---
os.makedirs(os.path.dirname(jsonl_save_path), exist_ok=True)

# --- Initialize the Gemini Model ---
model = genai.GenerativeModel("gemini-2.5-flash")

# --- Get the specific slice of links for this batch ---
# This ensures we only process the links you've defined
links_to_process = raw_links[START_INDEX:END_INDEX]

print(f"\n--- Starting Batch ---")
print(f"Processing links from index {START_INDEX} to {END_INDEX - 1}.")
print(f"Total links in this batch: {len(links_to_process)}")
print(f"Output will be appended to: {jsonl_save_path}")

# --- Process each link IN THIS BATCH ---
for i, video_url in enumerate(links_to_process):
    # This (i + START_INDEX) gives you the true index from your original file
    current_index = i + START_INDEX
    print(f"\n--- Processing Link #{current_index}: {video_url} ---")

    # STEP 3: yt-dlp options
    ydl_opts = {
        "skip_download": True,
        "subtitleslangs": [subtitle_lang],
        "subtitlesformat": "json3",
        "outtmpl": "%(id)s.%(ext)s",
        "cookiefile": cookies_file_path,
        "quiet": True, # Suppress yt-dlp console spam
    }

    try:
        # STEP 4: Get video info
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)

        duration_seconds = info.get("duration", 0)
        minutes = duration_seconds // 60
        video_id = info["id"]

        # Check video duration
        if not (5 <= minutes <= 60):
            print(f"❌ Video {video_id} out of range ({minutes} min). Skipping.")
            continue # Skip to the next link

        # Get subtitle info
        subtitles_info = info.get('automatic_captions', {}).get(subtitle_lang) or info.get('subtitles', {}).get(subtitle_lang)

        if subtitles_info:
            # Find the json3 subtitle URL
            subtitle_url = None
            for sub_info in subtitles_info:
                if sub_info.get('ext') == 'json3':
                    subtitle_url = sub_info.get('url')
                    break

            if subtitle_url:
                # Fetch and parse the subtitles
                response = requests.get(subtitle_url)
                if response.status_code == 200:
                    subtitle_data = response.json()
                    text_lines = []
                    for event in subtitle_data.get('events', []):
                        for seg in event.get('segs', []):
                            text_lines.append(seg.get('utf8', '').replace('\n', ' '))

                    transcription = " ".join(text_lines)

                    if not transcription.strip():
                        print(f"❌ Subtitles for {video_id} are empty. Skipping.")
                        continue

                    # --- Subtitles successfully fetched, now get summary ---
                    print(f"Subtitles for {video_id} fetched, generating summary...")

                    prompt = f"""
                    You are an expert at summarising Telugu lectures into concise yet complete.
                    Summarise the following Telugu lecture into a clear summary in Telugu,
                    keeping the important points intact. Do not shorten too much,
                    but also avoid excessive detail. Maintain natural Telugu teaching and use only telugu words dont involve any other language words in the summary. Make sure the total summary are in paragraphs.

                    Story:
                    {transcription}
                    """

                    summary_response = model.generate_content(prompt)
                    summary_text = summary_response.text

                    # --- ✅ Create and save the JSONL record ---
                    data_record = {
                        "text": transcription,
                        "summary": summary_text
                    }

                    # 'a' = append mode. This is the key to adding to the same file.
                    with open(jsonl_save_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(data_record, ensure_ascii=False) + "\n")

                    print(f"✅ Data for Link #{current_index} ({video_id}) appended to: {jsonl_save_path}")

                else:
                    print(f"❌ Failed to fetch subtitles for {video_id} (Status: {response.status_code}). Skipping.")
                    continue
            else:
                print(f"❌ No json3 subtitles found for {video_id} in '{subtitle_lang}'. Skipping.")
                continue
        else:
            print(f"❌ No subtitle info found for {video_id} in '{subtitle_lang}'. Skipping.")
            continue

    except Exception as e:
        # Catch any other errors (e.g., from yt-dlp or Gemini)
        print(f"❌ An error occurred while processing {video_url}: {e}. Skipping.")
        time.sleep(5)
        continue

    # ✅ 2. Add a 2-second pause after processing each link
    # This prevents the 429 "Too Many Requests" error
    time.sleep(10)

print(f"\n--- Batch from {START_INDEX} to {END_INDEX - 1} finished. ---")