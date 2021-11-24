#!/usr/bin/env python
import argparse
import re
import sys

import yaml
from schema import *
from common import (
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
from typing import List, Tuple
from pathlib import Path
from functools import lru_cache

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
    input_data = normalize_name(input_data)

    for b in data.bonus_kinds:
        if b == input_data:
            # return b
            return True

    raise SchemaError(f"No bonus matches `{input_data}`")


SCHEMA = Schema({
    "points": int,
    "bonuses": OrDefault(Schema([{
        "bonus": And(str, is_bonus_kind),
        Optional("weight", default=1): Use(float),
        Optional("pets", default=False): bool
    }
    ]), default_factory=dict),
    "celestial_powers": OrDefault(Schema([Use(lookup_celestial_power)]), default_factory=list),
    "stars": OrDefault(Schema(
        [And(str, Use(lambda x: parse_star(Data.load(), x)))],
    ), default_factory=list),
    "ignore_stars": OrDefault(Schema(
        [And(str, Use(lambda x: parse_star(Data.load(), x)))]
    ), default_factory=list)
})


def load_config(path: Path) -> Config:
    with open(path, 'r') as fp:
        config = yaml.load(fp, yaml.CLoader)

    config = SCHEMA.validate(config)

    objective = {}
    for bonus in config['bonuses']:
        kind = bonus['bonus']
        weight = bonus['weight']
        okey = (kind, bonus['pets'])
        try:
            objective[okey] += weight
        except KeyError:
            objective[okey] = weight

    return Config(
        objective=objective,
        ignore_stars=set(config['ignore_stars']),
        desired_stars=set(config['stars'] + config['celestial_powers']),
        num_points=config['points'],
    )


def load_config_or_exit(path=None) -> Config:
    path = path or Path("config.yaml")
    try:
        return load_config(path)
    except SchemaError as e:
        print(f"Error in config file {path}")
        print(e)
        sys.exit(1)
    except FileNotFoundError:
        print(f"File not found: {path}")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"Error parsing config file {path}")
        print(e)
        sys.exit(1)


def generate_config(args):
    if args.o and args.o.exists() and not args.force:
        fatal(f"File {args.o} already exists. Use -f to overwrite.")

    data = Data.load()
    bonuses = get_bonus_kinds_by_patterns(data, args.bonus)
    powers = get_powers_by_patterns(data, args.power) if args.power else []

    yaml_data = {
        "points": args.n,
        "bonuses": [{"bonus": b, "weight" : 1 } for b in bonuses],
        "celestial_powers": [p.name for _, p in powers],
        "stars": None,
        "ignore_stars": None
    }
    yaml_kwargs = dict(default_flow_style=False, sort_keys=False)
    if args.o:
        with open(args.o, 'w') as fp:
            yaml.dump(yaml_data, fp, **yaml_kwargs)
    else:
        print(yaml.dump(yaml_data, **yaml_kwargs))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description="Generate a config file for solve.py")
    p.add_argument('-n', type=int, default=55, help='Set number of available devotion points')
    p.add_argument('-p', '--power', action='append', default=[], help='Select Celestial Powers by pattern')
    p.add_argument('-b', '--bonus', action='append', default=[], help='Select bonuses by pattern')
    p.add_argument('-o', type=Path, default=None, help='Path of file to write to.', metavar='FILEPATH')
    p.add_argument('-f', '--force', action='store_true', help='Allow overwrite of existing config')
    args = p.parse_args()
    generate_config(args)
