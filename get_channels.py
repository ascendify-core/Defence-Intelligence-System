# run this: python get_channels.py
# requires: pip install yt-dlp

import subprocess, json

video_ids = [
    "KkgSOzFZG-g", "hAyYQT5gr1c", "iJwzKd2CJPY", "_Ah0weIMrYk",
    "K08GpKx5OJM", "04sNLYhCenM", "hLbNKU4TSJI", "bC_m1bd_emg",
    "rKSRxl-54sM", "FykUA3wD1o4", "ckAedg7-EYk", "Tcc2-6V6LI8",
    "2lrnVAsiF0M", "u4iVgP-Zueg", "4gMn97Lvye0", "scILbvGT0_c",
    "ub-WKCevFUw", "lNwqG4zR77c"
]

for vid in video_ids:
    url = f"https://www.youtube.com/watch?v={vid}"
    result = subprocess.run(
        ["yt-dlp", "--dump-json", "--no-download", url],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        data = json.loads(result.stdout)
        print(f"{vid} | {data.get('channel', 'Unknown')}")
    else:
        print(f"{vid} | ERROR")