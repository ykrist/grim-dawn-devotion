from common import *
import requests
from bs4 import BeautifulSoup
from pathlib import Path

CACHE = Path("cache")
OUTPUT_DIR = Path("data/scraped")

def get_html(path: str) -> str:
    cache_path = CACHE / path.lstrip("/")
    if cache_path.exists():
        with open(cache_path, 'r') as fp:
            return fp.read()

    url = "https://grimdawn.fandom.com" + path
    res = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:78.0) Gecko/20100101 Firefox/78.0"})
    print(f"GET {url} [{res.status_code}]")
    assert res.status_code == 200
    text = res.text
    cache_path.parent.mkdir(exist_ok=True, parents=True)
    with open(cache_path, 'w') as fp:
        fp.write(text)
    return text

def get_doc(path: str) -> BeautifulSoup:
    return BeautifulSoup(get_html(path), "html.parser")

def table_match_header(tag, match_header):
    if tag.name != "table":
        return False

    header = [th.text.strip().replace(' ', '') for th in tag.find_all("th")]

    if header != match_header:
        return False

    return True


def _parse_affinity(tag):
    return [(
        img.attrs['alt'].strip().lower(),
        int(img.next_element.strip())
    ) for img in tag.find_all("img")]


def parse_constellation_page(path: str):
    doc = get_doc(path)

    table = doc.find("table", class_="skill-prog")

    stars = []

    has_header = [th.text.strip().replace(' ', '') for th in table.find_all("th")[:2]] == ["#", "Stats"]
    rows = table.find_all("tr")
    if has_header:
        rows = rows[1:]

    for row in rows:
        stat_bonuses = row.find_all('td')[-1]
        for br in stat_bonuses.find_all('br'):
            br.replace_with("\n")
        skills = [s.strip() for s in stat_bonuses.text.strip().splitlines()]
        skills = [s for s in skills if s]
        stars.append(skills)

    return stars

_SKIP_CONSTELLATIONS = {
    "Crossroads",
    "Nighttalon",
    "Mantis",
    "Lotus",
    "Scarab",
    "Hyrian",
    "Murmur",
    "Ulzaad",
    "Yugol",
    "Korvaak",
    "Azrakaa",
}



def parse_constellation_table(table):
    for row in table.find_all("tr")[1:]:
        row = row.find_all('td')
        constellation = row[0].find('a', title=True, href=True)
        link = constellation.attrs['href']
        constellation = constellation.attrs['title'].replace("(constellation)", "").strip()

        if constellation in _SKIP_CONSTELLATIONS:
            continue
        if constellation == "Crossroads":
            return

        path = get_output_path(constellation)

        if path.exists():
            continue

        affinity_req = _parse_affinity(row[2])
        affinity_bonus = _parse_affinity(row[3])

        stars = parse_constellation_page(link)

        data = {
            "name" : constellation,
            "affinity_required": affinity_req,
            "affinity_bonus": affinity_bonus,
            "bonus": stars,
        }

        dump_json(data, path)
        print("wrote", path)

def get_filename(constellation_name) -> str:
    name = constellation_name.split(',')[0]
    name = name.replace("'", '')
    name = name.strip()
    name = name.replace(' ', '_')
    return name.lower()

def get_output_path(constellation_name) -> Path:
    return OUTPUT_DIR / (get_filename(constellation_name) + ".json")

if __name__ == '__main__':
    OUTPUT_DIR.mkdir(exist_ok=True, parents=True)
    doc = get_doc("/wiki/Constellation")

    tables = doc.find_all(lambda tag: table_match_header(tag, ["Name", "Stats", "AffinityRequired", "AffinityBonus"]))

    for table in tables:
        parse_constellation_table(table)
