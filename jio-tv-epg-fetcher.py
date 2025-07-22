import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import gzip
from tqdm import tqdm
from xml.dom import minidom

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://jiotv.com/"
}

CHANNELS_URL = "https://jiotvapi.cdn.jio.com/apis/v3.0/getMobileChannelList/get/?langId=6&devicetype=phone&os=android&usertype=JIO&version=343"
EPG_URL_TEMPLATE = "https://jiotvapi.cdn.jio.com/apis/v1.3/getepg/get?channel_id={channel_id}&offset={offset}"

def fetch_channels():
    print("📡 Fetching channel list...")
    response = requests.get(CHANNELS_URL, headers=HEADERS)
    response.raise_for_status()
    data = response.json()
    return data.get("result", []) if isinstance(data, dict) else data

def fetch_epg_offset_task(channel_id, offset):
    try:
        url = EPG_URL_TEMPLATE.format(channel_id=channel_id, offset=offset)
        response = requests.get(url, headers=HEADERS, timeout=5)
        if response.status_code == 404:
            return []
        response.raise_for_status()
        epg = response.json().get("epg", [])
        return [p for p in epg if "startEpoch" in p and "endEpoch" in p and "showname" in p]
    except:
        return []

def fetch_epg_concurrent(channel):
    channel_id = channel.get("channel_id")
    name = channel.get("channel_name", f"ID_{channel_id}")
    logo = channel.get("logoUrl", "")

    programs = []
    with ThreadPoolExecutor(max_workers=8) as offset_executor:
        futures = [offset_executor.submit(fetch_epg_offset_task, channel_id, offset) for offset in range(8)]
        for future in as_completed(futures):
            result = future.result()
            if result:
                programs.extend(result)

    if programs:
        programs.sort(key=lambda x: x.get("startEpoch", 0))
        return {
            "id": str(channel_id),
            "name": name,
            "logo": logo,
            "programs": programs
        }
    return None

def format_epoch(epoch_ms):
    dt = datetime.utcfromtimestamp(epoch_ms / 1000)
    return dt.strftime("%Y%m%d%H%M%S +0000")

def create_xmltv(channels_with_epg):
    print("🛠️ Creating XMLTV file...")
    tv = ET.Element("tv")

    # ✅ First: Write all <channel> entries
    for ch in channels_with_epg:
        channel = ET.SubElement(tv, "channel", id=ch["id"])
        ET.SubElement(channel, "display-name", lang="en").text = ch["name"]
        if ch["logo"]:
            ET.SubElement(channel, "icon", {'src': ch["logo"]})

    # ✅ Then: Write all <programme> entries
    for ch in channels_with_epg:
        for program in ch["programs"]:
            prog = ET.SubElement(tv, "programme", {
                "start": format_epoch(program["startEpoch"]),
                "stop": format_epoch(program["endEpoch"]),
                "channel": ch["id"]
            })
            ET.SubElement(prog, "title", lang="en").text = program.get("showname", "No Title")
            if program.get("description"):
                ET.SubElement(prog, "desc", lang="en").text = program["description"]
            if program.get("showGenre"):
                for genre in program["showGenre"]:
                    ET.SubElement(prog, "category", lang="en").text = genre
            if program.get("episode_num"):
                ET.SubElement(prog, "episode-num", system="onscreen").text = str(program["episode_num"])

    # ✅ Pretty-print XML for compatibility
    rough_xml = ET.tostring(tv, encoding="utf-8")
    pretty_xml = minidom.parseString(rough_xml).toprettyxml(indent="  ")

    with gzip.open("jiotv_epg.xml.gz", "wb") as f:
        f.write(pretty_xml.encode("utf-8"))
    print("✅ XMLTV file created: jiotv_epg.xml.gz")

def main():
    channels = fetch_channels()
    results = []

    print(f"🚀 Fetching EPG data in parallel for {len(channels)} channels...")
    with ThreadPoolExecutor(max_workers=30) as executor:
        futures = {executor.submit(fetch_epg_concurrent, ch): ch for ch in channels}
        for future in tqdm(as_completed(futures), total=len(futures), desc="📺 Processing channels"):
            result = future.result()
            if result:
                results.append(result)

    create_xmltv(results)

if __name__ == "__main__":
    main()
