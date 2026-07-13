import yt_dlp
import traceback

def test_extraction(url, opts):
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            print(f"Success! Found {len(info.get('formats', []))} formats.")
    except Exception as e:
        print(f"Failed! Error: {e}")

if __name__ == "__main__":
    url = "https://youtu.be/H1Mbg3MASCE?si=cjJNOmugY_6-pHBQ"
    
    print("\n--- Testing Default opts ---")
    test_extraction(url, {
        "quiet": True, "no_warnings": True, "skip_download": True
    })

    print("\n--- Testing format: 'all' ---")
    test_extraction(url, {
        "quiet": True, "no_warnings": True, "skip_download": True, "format": "all"
    })
