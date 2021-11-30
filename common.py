from grim_dawn_data import load_constellation_bonuses, WEAPON_TYPES, COUNTS_AS
from grim_dawn_data.bonuses import *
from grim_dawn_data.json_utils import JsonSerializable
import dataclasses
import json
import re
import sys
from pathlib import Path
from typing import *
import math
import logging
import copy
import toml
import textwrap
import functools

cache = functools.lru_cache(maxsize=None)

@dataclasses.dataclass(frozen=True, eq=True, order=True)
class Star(JsonSerializable):
    cons: str
    idx: int

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
class CelestialPower:
    name: str
    desc: str

def _is_selectable(b: Bonus) -> bool:
    return not isinstance(b, (ChanceOf, Pets)) and b.kind_id() not in COUNTS_AS


@dataclasses.dataclass
class Data:
    weapon_types: List[str]
    affinities: List[str]
    stars: List[Star]
    celestial_powers: Dict[Star, CelestialPower]
    celestial_power_stars: Dict[str, Star]
    predecessor: Dict[Star, Star]
    star_bonuses: Dict[Star, List[Bonus]]
    constellations: Dict[str, List[Star]]
    self_sufficient_constellations: Set[str]
    affinity_req: Dict[str, Dict[str, int]]
    affinity_bonus: Dict[str, Dict[str, int]]
    bonus_kinds: Set[str]
    selectable_bonus_kinds: Set[str]
    bonus_kinds_info : Dict[str, Dict[str, str]]
    weapon_req: Dict[Star, Set[str]]

    @staticmethod
    @cache
    def load():
        affinities = ["ascendant", "chaos", "eldritch", "order", "primordial"]
        stars = []
        celestial_powers = {}
        bonuses = {}
        pred = {}
        constellation = {}
        weapon_req = {}
        affinity_req = {}
        affinity_bonus = {}
        bonus_kinds = {}
        self_sufficient_constellations = set()

        raw = load_constellation_bonuses()
        for c in raw:
            cons = c['name']
            starlist = []
            for idx, stardata in c['skills'].items():
                idx = int(idx)
                star = Star(cons, idx)

                try:
                    blist = stardata['bonuses']
                except:
                    pass
                else:
                    bonuses[star] = blist
                    bonus_kinds.update((b.kind_id(), b) for b in blist)

                if 'celestial_power' in stardata:
                    desc = stardata['celestial_power']
                    name = normalize_name(stardata['celestial_power'])
                    celestial_powers[star] = CelestialPower(name, desc)

                if 'weapon_requirement' in stardata:
                    weapon_req[star] = set(stardata['weapon_requirement'])

                stars.append(star)
                starlist.append(star)

            constellation[cons] = starlist
            pred.update((Star(cons, int(i)), Star(cons, j)) for i, j in c['pred'].items())

            aff_req = dict(c['affinity_required'])
            aff_bonus = dict(c['affinity_bonus'])

            if all(aff_bonus.get(a, 0) >= aff_req.get(a, 0) for a in affinities):
                self_sufficient_constellations.add(cons)

            affinity_req[cons] = aff_req
            affinity_bonus[cons] = aff_bonus

        selectable_bonus_kinds = {k for k,b in bonus_kinds.items() if _is_selectable(b)}
        bonus_kinds_info = {k : {
            "display" : b.display_symbolic(),
            "value": _value_formula(b),
        } for k, b in bonus_kinds.items()}
        bonus_kinds = set(bonus_kinds)

        _DATA = Data(
            weapon_types=WEAPON_TYPES,
            weapon_req=weapon_req,
            affinities=affinities,
            affinity_req=affinity_req,
            affinity_bonus=affinity_bonus,
            constellations=constellation,
            celestial_powers=celestial_powers,
            celestial_power_stars={p.name: s for s, p in celestial_powers.items()},
            bonus_kinds=bonus_kinds,
            selectable_bonus_kinds=selectable_bonus_kinds,
            bonus_kinds_info=bonus_kinds_info,
            predecessor=pred,
            stars=stars,
            star_bonuses=bonuses,
            self_sufficient_constellations=self_sufficient_constellations
        )
        return _DATA

def _value_formula(b : Bonus) -> str:
    return {
        MiscBonus: "X",
        DamageModifier: "X",
        Damage: "0.5 * (X + Y)",
        Retaliation: "0.5 * (X + Y)",
        DamageOverTime: "X",
        ResistanceReduction: "X * Y",
        DamageOverTimeModifier: "X + Y",
    }.get(b.__class__, "N/A")


@dataclasses.dataclass
class Config:
    objective: Dict[str, float]
    desired_stars: Set[Star]
    weapons: Set[str]
    celestial_powers: Set[str]
    num_points: int
    log_level: int = logging.ERROR

    def validate(self, data: Data):
        for kind in self.objective:
            assert kind in data.bonus_kinds, f"no such bonus: `{kind}` "

    def to_dict(self) -> Dict:
        bonuses = []
        for kind, weight in sorted(self.objective.items()):
            b = {
                'kind': kind,
                'weight': weight,
            }
            bonuses.append(b)

        stars = sorted(fmt_star(s) for s in self.desired_stars)
        powers = sorted(self.celestial_powers)
        weapons = sorted(self.weapons)

        return {
            "points": self.num_points,
            "weapons": weapons,
            "bonus": bonuses,
            "celestial_powers": powers,
            "stars": stars,
        }

    def to_toml(self) -> str:
        comments = {
            "points": "Number of devotion points available",
            "celestial_powers": "Which celestial powers to unlock (case insensitive). Run './info.py p' for a full list",
            "stars": "Force these stars to be picked. Format is '[Constellation] [Index]', case insensitive; for example 'Revenant 0' or 'Vire the Stone Matron 5'.",
            "weapons": "Weapon types you will be using.  A star's bonuses only count if you meet the weapon requirement."
                       "  Possible weapons types are: " + ", ".join(w for w in WEAPON_TYPES) + ".  See './info.py w' for descriptions.",
        }


        data = Data.load()
        config = self.to_dict()
        bonuses = config.pop("bonus")
        toml_content = []

        add_comment = lambda c: toml_content.extend("# " + l for l in textwrap.wrap(c, 100))

        for k, v in config.items():
            try:
                add_comment(comments[k])
            except KeyError:
                pass
            toml_content.append(toml.dumps({k: v}))

        for b in bonuses:
            toml_content.append("[[bonus]]")
            info = data.bonus_kinds_info[b['kind']]
            add_comment(info['display'])
            add_comment("value = " + info['value'])
            toml_content.append(toml.dumps(b))

        return "\n".join(toml_content)

    def to_file(self, path: Path):
        with open(path, 'w') as fp:
            fp.write(self.to_toml())

def _calculate_bonus_value(b: Bonus) -> float:
    if isinstance(b, (MiscBonus, DamageModifier)):
        return b.amount
    elif isinstance(b, (Damage, Retaliation)):
        return b.min_val
    elif isinstance(b, DamageOverTimeModifier):
        return b.damage_mod + b.duration_mod
    elif isinstance(b, ChanceOf):
        assert not isinstance(b.bonus, Pets)
        return b.prob * _calculate_bonus_value(b.bonus)
    elif isinstance(b, Pets):
        assert not isinstance(b.bonus, ChanceOf)
        return _calculate_bonus_value(b.bonus)
    elif isinstance(b, DamageOverTime):
        return b.dps * b.duration
    elif isinstance(b, ResistanceReduction):
        return b.amount * b.duration
    else:
        raise NotImplementedError

def star_bonuses_meet_weapon_req(data: Data, config: Config) -> Dict[Star, List[Bonus]]:
    star_bonuses = {}
    for s, blist in data.star_bonuses.items():
        try:
            weapon_req = data.weapon_req[s]
        except KeyError:
            pass
        else:
            if len(config.weapons & weapon_req) == 0:
                continue
        star_bonuses[s] = blist
    return star_bonuses


def calculate_bonus_objective(config: Config, b: Bonus) -> Optional[float]:
    k = b.kind_id()
    weight = config.objective.get(k, 0)
    if isinstance(b, ChanceOf):
        weight += config.objective.get(b.bonus.kind_id(), 0)
    if k in COUNTS_AS:
        for k2, proportion in COUNTS_AS[k]:
            weight += proportion * config.objective.get(k2, 0)
    return weight * _calculate_bonus_value(b)

def calculate_star_objective(data: Data, config: Config) -> Dict[Star, float]:
    obj = {}
    for s, blist in star_bonuses_meet_weapon_req(data, config).items():
        coeff = 0
        for b in blist:
            coeff += calculate_bonus_objective(config, b)
        if coeff > 0:
            obj[s] = coeff
    return obj


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
                star = Star(cons, idx)
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
    return filter_strings(data.selectable_bonus_kinds, patterns, key=lambda k: data.bonus_kinds_info[k]['display'])

def get_powers_by_patterns(data: Data, patterns: List[str]) -> List[Tuple[Star, CelestialPower]]:
    return filter_strings(data.celestial_powers.items(), patterns, key=lambda pair: pair[1].desc)


def eprint(*args, **kwargs):
    kwargs['file'] = sys.stderr
    print(*args, **kwargs)


def fatal(*args):
    eprint(*args)
    sys.exit(1)

