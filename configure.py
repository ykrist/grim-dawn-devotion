#!/usr/bin/env python
import argparse
import logging
import sys
import toml
from schema import *
from typing import List, Tuple, Set
from pathlib import Path
from functools import lru_cache

from common import (
    COUNTS_AS,
    CelestialPower,
    Config,
    Data,
    Star,
    normalize_name,
    parse_star,
    fatal,
    get_powers_by_patterns,
    get_bonus_kinds_by_patterns
)


cache = lru_cache(maxsize=None)


class OrDefault:
    def __init__(self, inner, default=None, default_factory=None):
        if default_factory is None and default is None:
            default_factory = inner
        elif default_factory is None:
            default_factory = lambda: default

        self.inner = inner
        self.default = default_factory

    def __repr__(self):
        return f"{self.__class__.__name__}({self.inner!r})"

    def validate(self, data):
        if data is None:
            return self.default()
        else:
            return self.inner.validate(data)


@cache
def celestial_power_patterns() -> List[Tuple[Star, str, CelestialPower]]:
    data = Data.load()
    return [
        (s,
         normalize_name(p.name),
         p)
        for s, p in data.celestial_powers.items()
    ]


def lookup_celestial_power(input_data: str) -> Star:
    input_name = normalize_name(Schema(str).validate(input_data))

    for star, name, p in celestial_power_patterns():
        if name == input_name:
            return star

    raise SchemaError(f"No celestial power that matches `{input_data}`")


def is_bonus_kind(input_data: str) -> str:
    data = Data.load()
    if input_data not in data.selectable_bonus_kinds:
        raise SchemaError(f"No bonus matches `{input_data}`")
    return True

def is_weapon(input_data: str) -> str:
    data = Data.load()
    if input_data not in data.weapon_types:
        raise SchemaError(f"`{input_data}` is not in {data.weapon_types}")
    return True

def get_config_schema() -> Schema:
    data = Data.load()
    return Schema({
        "points": int,
        "bonus": OrDefault(Schema([{
            "kind": And(str, is_bonus_kind),
            "weight" : Use(float),
            Optional("pets", default=False): bool
        }
        ]), default_factory=dict),
        "weapons": [Or(*data.weapon_types)],
        "celestial_powers": OrDefault(Schema([Or(*data.celestial_power_stars)]), default_factory=list),
        "stars": OrDefault(Schema(
            [And(str, Use(lambda x: parse_star(data, x)))],
        ), default_factory=list),
    })



def load_config(path: Path) -> Config:
    with open(path, 'r') as fp:
        config = toml.load(fp)

    config = get_config_schema().validate(config)

    objective = {}
    for bonus in config['bonus']:
        kind = bonus['kind']
        weight = bonus['weight']
        pets = bonus['pets']
        if pets:
            kind = "Pets." + kind
        try:
            objective[kind] += weight
        except KeyError:
            objective[kind] = weight

    config =  Config(
        objective=objective,
        weapons=set(config['weapons']),
        desired_stars=set(config['stars']),
        num_points=config['points'],
        celestial_powers=config['celestial_powers']
    )

    return config


def load_config_or_exit(path=None) -> Config:
    path = path or Path("config.toml")
    try:
        return load_config(path)
    except SchemaError as e:
        print(f"Error in config file {path}")
        print(e)
        sys.exit(1)
    except FileNotFoundError:
        print(f"File not found: {path}")
        sys.exit(1)
    except toml.TomlDecodeError as e:
        print(f"Error parsing config file {path}")
        print(e)
        sys.exit(1)


def generate_config(args):
    if args.o and args.o.exists() and not args.force:
        fatal(f"File {args.o} already exists. Use -f to overwrite.")

    data = Data.load()
    bonuses = get_bonus_kinds_by_patterns(data, args.bonus)
    powers = get_powers_by_patterns(data, args.power) if args.power else []

    config = Config(
        objective={b: 1 for b in bonuses},
        desired_stars = set(),
        weapons=set(),
        celestial_powers = {p.name for _, p in powers},
        num_points=args.n,
        log_level=logging.WARNING,
    )

    if args.o:
        config.to_file(args.o)
    else:
        print(config.to_toml())


if __name__ == '__main__':
    p = argparse.ArgumentParser(description="Generate a config file for solve.py")
    p.add_argument('-n', type=int, default=55, help='Set number of available devotion points')
    p.add_argument('-p', '--power', action='append', default=[], help='Select Celestial Powers by pattern')
    p.add_argument('-b', '--bonus', action='append', default=[], help='Select bonuses by pattern')
    p.add_argument('-o', type=Path, default=None, help='Path of file to write to.', metavar='FILEPATH')
    p.add_argument('-f', '--force', action='store_true', help='Allow overwrite of existing config')
    args = p.parse_args()
    generate_config(args)
