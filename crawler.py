import os
import json
import time
import re
from pathlib import Path
import requests
from scrapling.fetchers import FetcherSession

BASE_URL = "https://yuseonggucouncil.go.kr/page/page05_02_02-ajax.php"
HTML_BASE_URL = "https://yuseonggucouncil.go.kr/CLRecords/Retrieval2/index.php"

def clean_title(title):
    # Titles are HTML links like <a href=#none> ... </a>
    # Let's extract the text and clean it
    text = re.sub(r'<[^>]+>', '', title).strip()
    # Replace problematic characters for filenames
    text = re.sub(r'[\\/*?:"<>|]', '_', text)
    text = text.replace('\r', '').replace('\n', ' ').replace('\t', ' ')
    # Clean up multiple spaces
    text = re.sub(r'\s+', ' ', text)
    return text

def main():
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    
    with FetcherSession() as session:
        # 1. We iterate over councilIds 1 to 9
        for council_id in range(1, 10):
            print(f"Fetching councilId: {council_id}")
            # Fetch sessions (th)
            try:
                res = requests.get(f"{BASE_URL}?councilId={council_id}", headers={"Referer": "https://www.google.com/"})
                sessions = res.json()
            except Exception as e:
                print(f"Error fetching sessions for {council_id}: {e}")
                continue

            for s in sessions:
                if "자료가 없습니다" in s.get("title", ""):
                    continue
                
                th = s.get("th")
                sess = s.get("session", "")
                
                if not th:
                    continue
                    
                session_title = clean_title(s.get("title", f"session_{th}"))
                session_dir = data_dir / f"{council_id}대" / session_title
                session_dir.mkdir(parents=True, exist_ok=True)
                
                print(f"  Fetching committees for council={council_id}, th={th}")
                try:
                    res_c = requests.get(f"{BASE_URL}?councilId={council_id}&th={th}")
                    committees = res_c.json()
                except Exception as e:
                    print(f"Error fetching committees for th {th}: {e}")
                    continue
                    
                for c in committees:
                    if "자료가 없습니다" in c.get("title", ""):
                        continue
                        
                    code = c.get("code")
                    if not code:
                        continue
                        
                    committee_title = clean_title(c.get("title", f"committee_{code}"))
                    committee_dir = session_dir / committee_title
                    committee_dir.mkdir(parents=True, exist_ok=True)
                    
                    print(f"    Fetching meetings for code={code}")
                    try:
                        res_m = requests.get(f"{BASE_URL}?councilId={council_id}&th={th}&session={sess}&code={code}")
                        meetings = res_m.json()
                    except Exception as e:
                        print(f"Error fetching meetings for code {code}: {e}")
                        continue
                        
                    for m in meetings:
                        if "자료가 없습니다" in m.get("title", ""):
                            continue
                            
                        fcode = m.get("fcode")
                        if not fcode:
                            continue
                            
                        meeting_title = clean_title(m.get("title", fcode))
                        meeting_file = committee_dir / f"{meeting_title}.html"
                        
                        if meeting_file.exists():
                            print(f"      Already exists: {meeting_file.name}")
                            continue
                            
                        print(f"      Downloading HTML for fcode={fcode}")
                        try:
                            res_html = requests.get(f"{HTML_BASE_URL}?hfile={fcode}&daesu={council_id}", headers={"Referer": "https://www.google.com/"})
                            with open(meeting_file, "w", encoding="utf-8") as f:
                                f.write(res_html.text)
                        except Exception as e:
                            print(f"Error downloading {fcode}: {e}")
                            
                        time.sleep(0.5) # delay to be polite

if __name__ == "__main__":
    main()
