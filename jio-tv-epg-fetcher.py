import requests
import xml.etree.ElementTree as ET
from xml.dom import minidom
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
from datetime import datetime, timedelta
import time
import os

JIO_CHANNEL_LIST_URL = "https://jiotvapi.cdn.jio.com/apis/v3.0/getMobileChannelList/get/?langId=6&devicetype=phone&os=android&usertype=JIO&version=343"
JIO_EPG_URL = "https://jiotvapi.cdn.jio.com/apis/v1.3/getepg/get?channel_id={}&offset={}"

HEADERS = {
    "User-Agent": "JioTV/7.0.5 (Linux;Android 10) ExoPlayerLib/2.11.7",
    "Accept-Encoding": "gzip",
    "Connection": "Keep-Alive"
}

OUTPUT_XML = "jio_epg.xml"

def fetch_channels():
    print("📡 Fetching channel list...")
    response = requests.get(JIO_CHANNEL_LIST_URL, headers=HEADERS)
    response.raise_for_status()
    data = response.json()
    return data.get("result", {}).get("channels", [])

def fetch_epg(channel_id, offset):
    url = JIO_EPG_URL.format(channel_id, offset)
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    data = response.json()
    return data.get("epg", [])

def build_xmltv(channels, epg_data):
    tv = ET.Element("tv")

    # Channel definitions
    for channel in channels:
        channel_el = ET.SubElement(tv, "channel", id=str(channel["channel_id"]))
        display_name = ET.SubElement(channel_el, "display-name", lang="en")
        display_name.text = channel["channel_name"]
        icon = ET.SubElement(channel_el, "icon", src=channel.get("logoUrl", ""))

    # Programme definitions
    for entry in epg_data:
        prog_el = ET.SubElement(tv, "programme", {
            "start": entry["start_time"],
            "stop": entry["end_time"],
            "channel": str(entry["channel_id"])
        })
        title = ET.SubElement(prog_el, "title", lang="en")
        title.text = entry.get("title", "")
        desc = ET.SubElement(prog_el, "desc", lang="en")
        desc.text = entry.get("description", "")
        category = ET.SubElement(prog_el, "category", lang="en")
        category.text = entry.get("genre", "Other")

    # Pretty print XML
    rough_string = ET.tostring(tv, encoding="utf-8")
    reparsed = minidom.parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent="  ")

    with open(OUTPUT_XML, "w", encoding="utf-8") as f:
        f.write(pretty_xml)

    print(f"✅ XMLTV written to {OUTPUT_XML}")

def format_epg(epg_list, channel_id):
    formatted = []
    for item in epg_list:
        start = datetime.fromtimestamp(item["starttime"]).strftime("%Y%m%d%H%M%S") + " +0530"
        end = datetime.fromtimestamp(item["endtime"]).strftime("%Y%m%d%H%M%S") + " +0530"
        formatted.append({
            "channel_id": channel_id,
            "start_time": start,
            "end_time": end,
            "title": item.get("title", ""),
            "description": item.get("description", ""),
            "genre": item.get("genre", "Other")
        })
    return formatted

def main():
    channels = fetch_channels()
    epg_data = []
    max_offset = 7  # Offset 0 to 7 = 8 * 3 hours = 24 hours

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for ch in channels:
            ch_id = ch["channel_id"]
            for offset in range(0, max_offset + 1):
                futures.append(executor.submit(fetch_epg, ch_id, offset))

        for future in tqdm(futures, desc="📺 Fetching EPG"):
            try:
                data = future.result()
                if data:
                    ch_id = data[0].get("channel_id")
                    epg_data.extend(format_epg(data, ch_id))
            except Exception as e:
                print(f"⚠️ Error fetching EPG: {e}")

    build_xmltv(channels, epg_data)

if __name__ == "__main__":
    main()
