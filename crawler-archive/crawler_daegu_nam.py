import json
import time
import re
from pathlib import Path
import requests

BASE_URL = "https://council.nam.daegu.kr"
FETCH_URL = f"{BASE_URL}/mnts/asvr/cnts/mnt/inc"
HEADERS = {
    "Referer": f"{BASE_URL}/mnts/content/mntsContentsList.html",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

def clean_title(title):
    text = re.sub(r'<[^>]+>', '', title).strip()
    text = re.sub(r'[\\/*?:"<>|]', '_', text)
    text = text.replace('\r', '').replace('\n', ' ').replace('\t', ' ')
    text = re.sub(r'\s+', ' ', text)
    return text

def fetch_nodes(session, name, params):
    """fancytree 지연 로드 엔드포인트 호출 (GET). 노드 리스트 반환"""
    res = session.get(f"{FETCH_URL}/{name}.php", params=params)
    return res.json()

def viewer_href(node):
    """노드 title 안의 회의록 뷰어 링크 추출"""
    m = re.search(r'href="([^"]*mntViewer\.php\?params=[^"]+)"', node.get("title", ""))
    return m.group(1).replace("&amp;", "&") if m else None

def check_html(text):
    """수집된 HTML 상태 판별: 'ok' / 'error'(오류 페이지)"""
    return "ok" if 'id="minutesViewer"' in text else "error"

def download_html(session, href, retries=3):
    """정상 HTML을 받을 때까지 재시도. (status, text) 반환"""
    status, text = "error", ""
    for _ in range(retries):
        res = session.get(f"{BASE_URL}{href}")
        res.encoding = "utf-8"
        text = res.text
        status = check_html(text)
        if status == "ok":
            break
        time.sleep(1)
    return status, text

def resolve_href(session, node):
    """차수 노드에서 뷰어 링크를 찾는다. 안건 노드(agnd)면 첫 안건의 링크를 사용
    (뷰어는 안건과 무관하게 해당 회의 전체를 보여준다)"""
    href = viewer_href(node)
    if href:
        return href
    if node.get("mode") == "agnd":
        for agnd in fetch_nodes(session, "treeAgndFetch", {"mntSn": node["mntSn"]}):
            href = viewer_href(agnd)
            if href:
                return href
    return None

def main():
    data_dir = Path(__file__).resolve().parent.parent / "minutes-archive" / "daegu-nam"
    data_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update(HEADERS)

    print("Fetching 'gnrtn' list (대수)...")
    page = session.get(f"{BASE_URL}/mnts/content/mntsContentsList.html?params=bHlOMUZTd0Nmd1QrSVcveUdUU2dnQT09")
    m = re.search(r'source:\s*(\[\{.*?\}\]),\s*lazyLoad', page.text, re.S)
    if not m:
        print("Error: gnrtn list not found")
        return
    gnrtn_list = json.loads(m.group(1))

    for gnrtn_node in gnrtn_list:
        gnrtn = gnrtn_node["gnrtn"]
        gnrtn_dir = data_dir / clean_title(gnrtn_node["title"])
        gnrtn_dir.mkdir(parents=True, exist_ok=True)
        print(f"Fetching sessions for gnrtn: {gnrtn}")

        try:
            sesn_list = fetch_nodes(session, "treeGnrtnSesnFetch", {"gnrtn": gnrtn})
        except Exception as e:
            print(f"Error fetching sessions for gnrtn {gnrtn}: {e}")
            continue

        for sesn_node in sesn_list:
            sesn = sesn_node["sesn"]
            sesn_dir = gnrtn_dir / clean_title(sesn_node["title"])
            sesn_dir.mkdir(parents=True, exist_ok=True)
            print(f"  Fetching committees for session: {sesn_dir.name}")

            try:
                cmt_list = fetch_nodes(session, "treeGnrtnCmtFetch", {"gnrtn": gnrtn, "sesn": sesn})
            except Exception as e:
                print(f"Error fetching committees for session {sesn}: {e}")
                continue

            for cmt_node in cmt_list:
                cmt_dir = sesn_dir / clean_title(cmt_node["title"])
                cmt_dir.mkdir(parents=True, exist_ok=True)
                print(f"    Fetching meetings for committee: {cmt_dir.name}")

                try:
                    chasu_list = fetch_nodes(session, "treeGnrtnChasuFetch", {"gnrtn": gnrtn, "sesn": sesn, "cmtCd": cmt_node["cmtCd"]})
                except Exception as e:
                    print(f"Error fetching meetings for committee {cmt_dir.name}: {e}")
                    continue

                for chasu_node in chasu_list:
                    min_title = clean_title(chasu_node["title"])
                    if len(min_title) > 200:
                        min_title = min_title[:200]
                    meeting_file = cmt_dir / f"{min_title}.html"

                    if meeting_file.exists():
                        if check_html(meeting_file.read_text(encoding="utf-8", errors="replace")) == "ok":
                            print(f"      Already exists: {meeting_file.name}")
                            continue
                        print(f"      Re-downloading (error): {meeting_file.name}")
                    else:
                        print(f"      Downloading HTML: {meeting_file.name}")

                    try:
                        href = resolve_href(session, chasu_node)
                        if not href:
                            print(f"      FAILED (no viewer link): {meeting_file.name}")
                            continue
                        status, text = download_html(session, href)
                        if status == "error":
                            print(f"      FAILED (error page): {meeting_file.name}")
                            continue
                        with open(meeting_file, "w", encoding="utf-8") as f:
                            f.write(text)
                    except Exception as e:
                        print(f"Error downloading {meeting_file.name}: {e}")

                    time.sleep(0.5)

if __name__ == "__main__":
    main()
