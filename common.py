import dataclasses
import json
import re
import sys
from pathlib import Path
from typing import *
import math
import logging

import yaml

Star = Tuple[str, int]


def fmt_val(val: float) -> str:
    for places in [0, 1, 2]:
        if math.isclose(val, round(val, places), abs_tol=1e-6):
            return f"{{:.{places}f}}".format(val)

    return f"{val}"

def fmt_star(s: Star) -> str:
    return f'{s[0]} {s[1]}'


def bonus_kind_lex_key(kind: str) -> str:
    return kind.lstrip("% -")


@dataclasses.dataclass(frozen=True, eq=True)
class Bonus:
    apply_to_pets: bool
    value: float
    kind: str
    prob: Optional[float] = None
    duration: Optional[float] = None
    value_range: Optional[Tuple[float, float]] = None
    max_value: Optional[float] = None

    def objective_key(self) -> (str, bool):
        return (self.kind, self.apply_to_pets)

    def lex_key(self) -> str:
        return bonus_kind_lex_key(self.kind)

    def display(self) -> str:
        if self.apply_to_pets:
            s = "Bonus to All Pets: "
        else:
            s = ""

        if self.value_range is not None:
            value = f"{fmt_val(self.value_range[0])}-{fmt_val(self.value_range[1])}"
        else:
            value = fmt_val(self.value)

        kind = self.kind
        if kind.startswith("-% "):
            kind = kind.replace("-% ", "")
            value = f"-{value}% "
        elif kind.startswith("% "):
            pass
        else:
            value = f"{value} "
        return f"{s}{value}{kind}"


@dataclasses.dataclass(frozen=True, eq=True)
class CelestialPower:
    name: str
    desc: str


_DATA = None


@dataclasses.dataclass
class Data:
    affinities: List[str]
    stars: List[Star]
    celestial_powers: Dict[Star, CelestialPower]
    predecessor: Dict[Star, Star]
    bonuses: Dict[Star, List[Bonus]]
    constellations: Dict[str, List[Star]]
    self_sufficient_constellations: Set[str]
    affinity_req: Dict[str, Dict[str, int]]
    affinity_bonus: Dict[str, Dict[str, int]]
    bonus_kinds: Set[str]

    @staticmethod
    def load():
        global _DATA
        if _DATA:
            return _DATA

        affinities = ["ascendant", "chaos", "eldritch", "order", "primordial"]
        stars = []
        celestial_powers = {}
        bonuses = {}
        pred = {}
        constellation = {}
        affinity_req = {}
        affinity_bonus = {}
        bonus_kinds = set()
        self_sufficient_constellations = set()

        raw = load_json("data/main.json")
        for c in raw:
            cons = c['name']
            starlist = []
            for i, x in enumerate(c['bonus']):
                star = (cons, i)
                if isinstance(x, CelestialPower):
                    celestial_powers[star] = x
                else:
                    bonuses[star] = x
                    bonus_kinds.update(b.kind for b in x)
                stars.append(star)
                starlist.append(star)
            constellation[cons] = starlist

            for i, succ in c['topology']:
                i = (cons, i)
                for j in succ:
                    j = (cons, j)
                    assert j not in pred
                    pred[j] = i

            aff_req = dict(c['affinity_required'])
            aff_bonus = dict(c['affinity_bonus'])
            for a in affinities:
                if aff_bonus.get(a, 0) < aff_req.get(a, 0):
                    break
            else:
                self_sufficient_constellations.add(cons)

            affinity_req[cons] = aff_req
            affinity_bonus[cons] = aff_bonus

        _DATA = Data(
            affinities=affinities,
            affinity_req=affinity_req,
            affinity_bonus=affinity_bonus,
            constellations=constellation,
            celestial_powers=celestial_powers,
            bonus_kinds=bonus_kinds,
            predecessor=pred,
            stars=stars,
            bonuses=bonuses,
            self_sufficient_constellations=self_sufficient_constellations
        )
        return _DATA


@dataclasses.dataclass
class Config:
    objective: Dict[Tuple[str, bool], float]
    desired_stars: Set[Star]
    ignore_stars: Set[Star]
    num_points: int
    log_level: int = logging.WARNING

    def validate(self, data: Data):
        for kind, _ in self.objective:
            assert kind in data.bonus_kinds, f"no such bonus: `{kind}` "

    def adjust_objective(self):
            for k, kind_list in COUNTS_AS.items():
                for pet in [True, False]:
                    key1 = (k, pet)
                    for kind, proportion in kind_list:
                        key2 = (kind, pet)
                        if key2 in self.objective:
                            val = proportion * self.objective[key2]
                            if key1 in self.objective:
                                self.objective[key1] += val
                            else:
                                self.objective[key1] = val

    def to_yaml_dict(self) -> Dict:
        data = Data.load()
        bonuses = []
        for (kind, pets), weight in self.objective.items():
            b = {
                'bonus': kind,
                'weight': weight,
            }
            if pets:
                b['pets'] = True
            bonuses.append(b)

        stars = [fmt_star(s) for s in self.desired_stars if s not in data.celestial_powers]
        powers = [data.celestial_powers[s].name for s in self.desired_stars if s in data.celestial_powers]
        ignore_stars = [fmt_star(s) for s in self.ignore_stars]

        return {
            "points": self.num_points,
            "bonuses": bonuses,
            "celestial_powers": powers,
            "stars": stars,
            "ignore_stars": ignore_stars,
        }

    def dump_yaml(self, path: Path):
        with open(path, 'w') as fp:
            yaml.dump(self.to_yaml_dict(), fp, default_flow_style=False)

def _prepare_json(obj: dict):
    if dataclasses.is_dataclass(obj):
        return {
            "_type": obj.__class__.__name__,
            "data": _prepare_json(dataclasses.asdict(obj))
        }
    elif isinstance(obj, set):
        return {
            "_type": "set",
            "data": [_prepare_json(i) for i in obj]
        }
    elif isinstance(obj, tuple):
        return {
            "_type": "tuple",
            "data": [[_prepare_json(i) for i in obj]]
        }

    elif isinstance(obj, dict):
        return {_prepare_json(k): _prepare_json(v) for k, v in obj.items()}

    elif isinstance(obj, list):
        return [_prepare_json(k) for k in obj]

    else:
        return obj


def serialize_json(obj):
    if dataclasses.is_dataclass(obj):
        return {
            "_type": obj.__class__.__name__,
            "data": dataclasses.asdict(obj)
        }
    elif isinstance(obj, set):
        return {
            "_type": "set",
            "data": list(obj)
        }
    elif isinstance(obj, tuple):
        return {
            "_type": "tuple",
            "data": list(obj)
        }
    raise NotImplementedError


def deserialize_json(data: dict):
    try:
        typename = data["_type"]
    except KeyError:
        return data
    else:
        if typename == "set":
            return set(data['data'])
        elif typename == "tuple":
            return tuple(*data['data'])
        else:
            cls = globals()[typename]
            return cls(**data['data'])


def loads_json(s: str) -> object:
    return json.loads(s, object_hook=deserialize_json)


def dumps_json(obj) -> str:
    return json.dumps(_prepare_json(obj), indent="  ")


def load_json(p: Path) -> dict:
    with open(p, 'r') as fp:
        return json.load(fp, object_hook=deserialize_json)


def dump_json(obj, p: Path):
    with open(p, 'w') as fp:
        return json.dump(_prepare_json(obj), fp, indent="  ")


def normalize_name(s: str) -> str:
    return s.lower().replace(',', '').replace("'", '').strip()


def parse_star(data: Data, s: str) -> Star:
    m = re.fullmatch(r"([a-z,' ]+) (\d+)", s, flags=re.IGNORECASE)
    if m:
        cons = normalize_name(m.group(1))
        idx = int(m.group(2))
        for c, stars in data.constellations.items():
            if normalize_name(c) == cons:
                cons = c
                star = (cons, idx)
                if star in stars:
                    return star
                else:
                    raise ValueError(f"No star with that index in constellation: {c}")

        raise ValueError(f"No such constellation: {m.group(1)}")
    else:
        raise ValueError(f"Star must be in the format: [Constellation] [index]")


def filter_strings(strings: Iterable[str], patterns: List[str], key=None) -> List[str]:
    patterns = [re.compile(p, flags=re.IGNORECASE) for p in patterns]
    key = key or (lambda x: x)
    if patterns:
        return [s for s in strings if any(p.search(key(s)) for p in patterns)]
    else:
        return list(strings)


def get_bonus_kinds_by_patterns(data: Data, patterns: List[str]) -> List[str]:
    return filter_strings(data.bonus_kinds, patterns)


def get_powers_by_patterns(data: Data, patterns: List[str]) -> List[Tuple[Star, CelestialPower]]:
    return filter_strings(data.celestial_powers.items(), patterns, key=lambda pair: pair[1].desc)


def eprint(*args, **kwargs):
    kwargs['file'] = sys.stderr
    print(*args, **kwargs)

def fatal(*args):
    eprint(*args)
    sys.exit(1)



COUNTS_AS = {
    "% elemental damage": [
        ("% cold damage", 1),
        ("% fire damage", 1),
        ("% lightning damage", 1),
    ],
    "% elemental resistance": [
        ("% cold resistance", 1),
        ("% fire resistance", 1),
        ("% lightning resistance", 1),
    ],
    "elemental damage": [
        ("cold damage", 1 / 3),
        ("fire damage", 1 / 3),
        ("lightning damage", 1 / 3),
    ],
    "% maximum all resistance": [
        ("% maximum aether resistance", 1),
        ("% maximum bleeding resistance", 1),
        ("% maximum chaos resistance", 1),
        ("% maximum cold resistance", 1),
        ("% maximum fire resistance", 1),
        ("% maximum lightning resistance", 1),
        ("% maximum piercing resistance", 1),
        ("% maximum vitality resistance", 1),
    ]
}

