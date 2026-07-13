import yt_dlp
import traceback

def select_best_format(info, quality_index):
    # Heights ordered from best to worst
    YT_QUALITY_HEIGHTS = [1080, 720, 480, 360, 240, 144]
    max_height = YT_QUALITY_HEIGHTS[min(quality_index, len(YT_QUALITY_HEIGHTS) - 1)]
    
    formats = info.get("formats", [])
    
    # Separate streams
    video_streams = [f for f in formats if f.get("vcodec") != "none" and f.get("acodec") == "none"]
    audio_streams = [f for f in formats if f.get("acodec") != "none" and f.get("vcodec") == "none"]
    combined_streams = [f for f in formats if f.get("vcodec") != "none" and f.get("acodec") != "none"]
    
    # Filter by height
    valid_video = [f for f in video_streams if (f.get("height") or 0) <= max_height]
    valid_combined = [f for f in combined_streams if (f.get("height") or 0) <= max_height]
    
    # Fallback to any height if none match the max_height
    if not valid_video and video_streams:
        valid_video = video_streams
    if not valid_combined and combined_streams:
        valid_combined = combined_streams
        
    # Sort to get the best one
    # For video: highest height, then highest tbr/filesize
    def video_sort_key(f):
        return (f.get("height") or 0, f.get("tbr") or 0, f.get("filesize") or 0)
        
    def audio_sort_key(f):
        return (f.get("abr") or 0, f.get("tbr") or 0, f.get("filesize") or 0)
        
    if valid_video:
        valid_video.sort(key=video_sort_key, reverse=True)
    if valid_combined:
        valid_combined.sort(key=video_sort_key, reverse=True)
    if audio_streams:
        audio_streams.sort(key=audio_sort_key, reverse=True)
        
    # Decide format_id
    if valid_video and audio_streams:
        v_id = valid_video[0]["format_id"]
        a_id = audio_streams[0]["format_id"]
        return f"{v_id}+{a_id}"
    elif valid_combined:
        return valid_combined[0]["format_id"]
    elif formats:
        # Absolute fallback to whatever is last/best
        return formats[-1]["format_id"]
    else:
        return "best"  # Absolute last resort

def main():
    url = "https://youtu.be/HyMxt7oIfIs?si=6ydGOQT2pyy2QKfB"
    info_opts = {
        "quiet": True,
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(info_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        
    fmt = select_best_format(info, 2) # max_height = 480
    print(f"Selected format: {fmt}")
    
    dl_opts = {
        "quiet": True,
        "format": fmt,
        "skip_download": True,
    }
    try:
        with yt_dlp.YoutubeDL(dl_opts) as ydl:
            ydl.extract_info(url, download=False) # this will test if the format selection is valid
            print("Format selection is valid!")
    except Exception as e:
        print(f"Failed! {e}")

if __name__ == "__main__":
    main()
