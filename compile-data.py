#!/usr/bin/env python
import re
import glob
from common import *

def load_data():
    data = {p.stem : p for p in (Path(p) for p in glob.glob("data/scraped/*.json"))}
    data.update({p.stem : p for p in (Path(p) for p in glob.glob("data/manual/*.json"))})

    items = []
    for id_, path in data.items():
        d = load_json(path)
        d['id'] = id_
        topopath = Path("data/topology") / path.name
        if topopath.exists():
            with open(topopath, 'r') as fp:
                d["topology"] = validate_topology(len(d['bonus']), json.load(fp))
        else:
            n = len(d["bonus"])
            d["topology"] = [[i, [j]] for i, j in zip(range(n), range(1,n))]
        items.append(d)

    return items


def parse_bonus_description(desc: str, pet: bool) -> List[Bonus]:
    m = re.fullmatch(r"\+?(?P<value>\d+\.?\d*) (?P<kind>[A-Za-z ]+)", desc)
    if m is not None:
        return [Bonus(
            apply_to_pets=pet,
            kind=m.group('kind'),
            value=float(m.group('value')),
        )]

    m = re.fullmatch(r"\+?(?P<value>\d+)% (?P<kind>[A-Za-z ]+)", desc)
    if m is not None:
        return [Bonus(
            apply_to_pets=pet,
            kind="% " + m.group('kind'),
            value=float(m.group('value')),
        )]

    m = re.match(r"Increases? (?P<kind>[A-Za-z ]+) by (?P<value>\d+)%", desc)
    if m is not None:
        return [Bonus(
            apply_to_pets=pet,
            kind="% " + m.group('kind'),
            value=float(m.group('value')),
        )]

    m = re.match(r"(?P<total>\d+) (?P<kind>[A-Za-z ]+) over (?P<dur>\d+) [Ss]econds", desc)
    if m is not None:
        total = float(m.group('total'))
        dur = float(m.group('dur'))
        return [Bonus(
            apply_to_pets=pet,
            kind="% " + m.group('kind'),
            value=total,
            duration=dur,
        )]

    m = re.match(r"(?P<min>\d+)\s*-\s*(?P<max>\d+) (?P<kind>[A-Za-z ]+ Damage)", desc)
    if m is not None:
        a = float(m.group('min'))
        b = float(m.group('max'))
        return [Bonus(
            apply_to_pets=pet,
            kind=m.group('kind'),
            value=(a + b) / 2,
            value_range=(a, b),
        )]


    m = re.match(r"(?P<value>\d+)% (?P<kind1>\w+) & (?P<kind2>\w+) Resistance", desc)
    if m is not None:
        return [Bonus(
            apply_to_pets=pet,
            kind="% " + kind + " resistance",
            value=float(m.group('value')),
        ) for kind in [m.group('kind1'), m.group('kind2')]]

    m = re.match(r"-(?P<value>\d+)% (?P<kind>\w+ Requirement for \w+)", desc)
    if m is not None:
        return [Bonus(
            apply_to_pets=pet,
            kind="-% " + m.group('kind'),
            value=float(m.group('value')),
        )]

    m = re.match(r"-(?P<value>\d+)% (?P<kind>[a-zA-Z ]+cost)", desc, flags=re.IGNORECASE)
    if m is not None:
        return [Bonus(
            apply_to_pets=pet,
            kind="-% " + m.group('kind'),
            value=float(m.group('value')),
        )]

    m = re.match(r"\+(?P<v1>\d+)% (?P<dot>.+) Damage with \+(?P<v2>\d+)% Increased Duration", desc, flags=re.IGNORECASE)
    if m is not None:
        kind1 = m.group('dot') + " damage"
        kind2 = m.group('dot') + " duration"
        return [Bonus(
            apply_to_pets=pet,
            kind="% " + k,
            value=float(v),
        ) for k, v in zip([kind1, kind2], [m.group('v1'), m.group('v2')])]

    m = re.match(r"\+(?P<v1>\d+)% vitality decay with \+(?P<v2>\d+)% increased duration", desc, flags=re.IGNORECASE)
    if m is not None:
        return [Bonus(
            apply_to_pets=pet,
            kind="% " + k,
            value=float(v),
        ) for k, v in zip(["Vitality Decay", "Vitality Decay Duration"], [m.group('v1'), m.group('v2')])]

    m = re.match(r"healing effects increased by (?P<val>\d+)%", desc, flags=re.IGNORECASE)
    if m is not None:
        return [Bonus(
            apply_to_pets=pet,
            kind="% Healing Effects",
            value=float(m.group('val')),
        )]


    if desc.startswith("Bonus to All Pets: "):
        assert not pet
        return parse_bonus_description(desc.replace("Bonus to All Pets: ", ""), True)

    print("NOT CLASSIFIED: ", desc)
    return []

def _replace_words(s: str, sub: dict):
    words = s.split()
    for i, w in enumerate(words):
        words[i] = sub.get(w, w)
    return " ".join(words)

def normalise_kind(s: str) -> str:
    clean = s.lower()
    clean = _replace_words(clean, {
        "damag": "damage",
        "converter": "converted",
        "physcial": "physical",
        "pierce": "piercing",
    })

    clean = clean.replace("defense abilitiy", "defensive ability")
    clean = clean.replace("of attack damage converted to health", "attack damage converted to health")

    return clean

def validate_topology(num_stars, topo):
    inds = set()
    for i, succ in topo:
        assert i not in succ, "self edge in topology"
        inds.add(i)
        inds.update(succ)

    assert inds == set(range(num_stars)), "extra/missing stars in topology"
    return topo

def parse_celestial_power(desc: str) -> CelestialPower:
    desc = desc.lstrip('[').rstrip(']').strip()
    name = re.sub('\s*\(.+\)\s*$', '', desc)
    return CelestialPower(name, desc)

def parse_star_bonus(bonus_list: List[str]) -> Union[List[Bonus], CelestialPower]:
    if re.search("\(\d+%( chance)? (on|when|at).+\)$", bonus_list[0], flags=re.IGNORECASE):
        return parse_celestial_power(bonus_list[0])

    try:
        idx = bonus_list.index("Bonus to All Pets")
    except ValueError:
        idx = len(bonus_list)

    ret = []

    for s in bonus_list[:idx]:
        ret.extend(parse_bonus_description(s, False))
    for s in bonus_list[idx+1:]:
        ret.extend(parse_bonus_description(s, True))

    ret = [dataclasses.replace(b, kind=normalise_kind(b.kind)) for b in ret]

    return ret


if __name__ == '__main__':
    data = load_data()
    data.sort(key=lambda d: d['name'])
    for const in data:
        const['bonus'] = [parse_star_bonus(b) for i, b in enumerate(const['bonus'])]

    for k in sorted(set(b.kind for c in data for s in c['bonus'] if not isinstance(s, CelestialPower) for b in s)):
        print(k)

    dump_json(data, "data/main.json")