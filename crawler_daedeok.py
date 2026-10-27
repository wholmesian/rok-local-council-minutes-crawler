import os
import json
import time
import re
from pathlib import Path
import requests

BASE_URL = "https://council.daedeok.go.kr"
HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://council.daedeok.go.kr/kr/minutes/session.do",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

def clean_title(title):
    text = re.sub(r'<[^>]+>', '', title).strip()
    text = re.sub(r'[\\/*?:"<>|]', '_', text)
    text = text.replace('\r', '').replace('\n', ' ').replace('\t', ' ')
    text = re.sub(r'\s+', ' ', text)
    return text

def main():
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    
    cl_cd = "CO" # 대덕구 의회
    
    session = requests.Session()
    session.headers.update(HEADERS)

    # 사이트가 CSRF 토큰 없이는 403을 반환하므로, 목록 페이지에서 토큰을 받아 헤더에 설정
    page = session.get(f"{BASE_URL}/kr/minutes/session.do")
    m = re.search(r'name="_csrf"\s+content="([^"]+)"', page.text) or re.search(r'content="([^"]+)"\s+name="_csrf"', page.text)
    if m:
        session.headers["X-CSRF-TOKEN"] = m.group(1)
    
    print("Fetching 'th' list (대수)...")
    try:
        res_th = session.post(f"{BASE_URL}/minutes/async/th.do", data={"cl_cd": cl_cd})
        th_list = res_th.json()
    except Exception as e:
        print(f"Error fetching th list: {e}")
        return
        
    for th_node in th_list:
        th = th_node.get("data", {}).get("th")
        if not th:
            continue
            
        th_title = clean_title(th_node.get("text", f"{th}대"))
        th_dir = data_dir / th_title
        th_dir.mkdir(parents=True, exist_ok=True)
        print(f"Fetching sessions for th: {th}")
        
        try:
            res_sess = session.post(f"{BASE_URL}/minutes/async/session.do", data={"cl_cd": cl_cd, "th": th})
            sess_list = res_sess.json()
        except Exception as e:
            print(f"Error fetching sessions for th {th}: {e}")
            continue
            
        for sess_node in sess_list:
            sess = sess_node.get("data", {}).get("session")
            if not sess:
                continue
                
            sess_title = clean_title(sess_node.get("text", f"session_{sess}"))
            sess_dir = th_dir / sess_title
            sess_dir.mkdir(parents=True, exist_ok=True)
            print(f"  Fetching committees for session: {sess}")
            
            try:
                res_cmt = session.post(f"{BASE_URL}/minutes/async/committee.do", data={"cl_cd": cl_cd, "th": th, "session": sess})
                cmt_list = res_cmt.json()
            except Exception as e:
                print(f"Error fetching committees for session {sess}: {e}")
                continue
                
            for cmt_node in cmt_list:
                cmt_cd = cmt_node.get("data", {}).get("cmt_cd")
                if not cmt_cd:
                    continue
                    
                cmt_title = clean_title(cmt_node.get("text", f"committee_{cmt_cd}"))
                cmt_dir = sess_dir / cmt_title
                cmt_dir.mkdir(parents=True, exist_ok=True)
                print(f"    Fetching minutes for committee: {cmt_title}")
                
                try:
                    res_min = session.post(f"{BASE_URL}/minutes/async/minutes.do", data={"cl_cd": cl_cd, "th": th, "session": sess, "cmt_cd": cmt_cd})
                    min_list = res_min.json()
                except Exception as e:
                    print(f"Error fetching minutes for committee {cmt_title}: {e}")
                    continue
                    
                for min_node in min_list:
                    uid = min_node.get("data", {}).get("uid")
                    if not uid:
                        continue
                        
                    min_title = min_node.get("a_attr", {}).get("title", min_node.get("text", f"minutes_{uid}"))
                    min_title = clean_title(min_title)
                    if len(min_title) > 200:
                        min_title = min_title[:200]
                        
                    meeting_file = cmt_dir / f"{min_title}.html"
                    
                    if meeting_file.exists():
                        print(f"      Already exists: {meeting_file.name}")
                        continue
                        
                    print(f"      Downloading HTML for uid={uid}")
                    try:
                        res_html = session.get(f"{BASE_URL}/viewer/minutes.do?uid={uid}", headers={"Referer": BASE_URL})
                        with open(meeting_file, "w", encoding="utf-8") as f:
                            f.write(res_html.text)
                    except Exception as e:
                        print(f"Error downloading {uid}: {e}")
                        
                    time.sleep(0.5)

if __name__ == "__main__":
    main()
