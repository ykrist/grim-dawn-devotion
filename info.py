#!/usr/bin/env python
import argparse
import json
import re
from prettytable import PrettyTable, PLAIN_COLUMNS
from grim_dawn_data import WEAPON_TYPES
from common import *

def output_table(args, table: PrettyTable):
    # table.set_style(PLAIN_COLUMNS)
    table.sortby = None

    if args.json:
        print(table.get_json_string(header=False))
    else:
        print(table)


def bonus(args):
    data = Data.load()
    selected_bonuses = get_bonus_kinds_by_patterns(data, args.pattern)
    selected_bonuses.sort(key=bonus_kind_lex_key)

    table = PrettyTable()
    table.field_names = ["Bonus", "Description", "Value"]
    table.align = "l"
    table.align['Value'] = "c"
    for b in selected_bonuses:
        info = data.bonus_kinds_info[b]
        table.add_row([b, info['display'], info['value']])
    output_table(args, table)

def constellation(args):
    data = Data.load()
    selected_constellations = filter_strings(data.constellations, args.pattern)
    selected_constellations.sort()

    table = PrettyTable()

    table.field_names = ["Constellation", "Stars", "Affinity Req.", "Affinity Bonus"]
    table.align["Constellation"] = "l"
    fmt_affinity = lambda aff:  ", ".join(f"{aff[a]:2} {a[:3].capitalize()}" for a in data.affinities if a in aff)
    for c in selected_constellations:
        table.add_row([c, len(data.constellations[c]), fmt_affinity(data.affinity_req[c]), fmt_affinity(data.affinity_bonus[c])])

    output_table(args, table)

def constellation_stars(args):
    data = Data.load()
    selected_constellations = filter_strings(data.constellations, args.pattern)
    selected_constellations.sort()

    table = PrettyTable()

    if args.json:
        jsondata = []
        for c in selected_constellations:
            for s in data.constellations[c]:
                d = {
                    "Star": s.to_json_dict(),
                    "Bonuses": [b.display() for b in data.star_bonuses.get(s, [])]
                }
                p = data.celestial_powers.get(s)
                if p:
                    d['CelestialPower'] = p.name
                jsondata.append(d)
        print(json.dumps(jsondata, indent='  '))
    else:
        table.field_names = ["Star", "Bonuses"]
        table.align["Constellation"] = "l"
        for c in selected_constellations:
            for s in data.constellations[c]:
                star_name = f"{s.cons} {s.idx}"
                first_row = True
                for b in data.star_bonuses.get(s, []):
                    table.add_row([star_name if first_row else "", b.display()])
                    first_row = False
                power = data.celestial_powers.get(s)
                if power:
                    table.add_row([star_name if first_row else "", power.desc])

                table.add_row(["", ""])
        table.del_row(len(table.rows) - 1)
        table.align["Bonuses"] = "l"

        output_table(args, table)


def celestial_powers(args):
    data = Data.load()
    powers = get_powers_by_patterns(data, args.pattern)
    powers.sort()

    table = PrettyTable()
    table.field_names = ["Power", "Star"]
    table.align = "l"
    for star, p in powers:
        table.add_row([p.desc, f"{star.cons} {star.idx}"])

    output_table(args, table)

def weapon_types(args):
    table = PrettyTable()
    table.field_names = ["Type", "Description"]
    table.align = "l"
    for t, desc in WEAPON_TYPES.items():
        table.add_row([t, desc])

    output_table(args, table)


def add_common_args(subparser: argparse.ArgumentParser):
    subparser.add_argument("pattern", nargs="*", help="Pattern(s) to filter by.")
    subparser.add_argument("--json", action='store_true', help="Output as JSON")

if __name__ == '__main__':
    p = argparse.ArgumentParser(
        description="Print out information about Constellations, Stars, Bonuses and Celestial Powers"
    )
    sp = p.add_subparsers(required=True, dest="cmd")


    bon = sp.add_parser("bonus", aliases=["b"], help="List possible bonuses")
    add_common_args(bon)
    bon.set_defaults(func=bonus)

    cons = sp.add_parser("constellations", aliases=["c", "cons"], help="List Constellations")
    add_common_args(cons)
    cons.set_defaults(func=constellation)

    stars = sp.add_parser("stars", aliases=["s"], help="Stars within a Constellation")
    add_common_args(stars)
    stars.set_defaults(func=constellation_stars)

    powers = sp.add_parser("powers", aliases=["p"], help="List Celestial Powers")
    add_common_args(powers)
    powers.set_defaults(func=celestial_powers)

    weapons = sp.add_parser("weapons", aliases=["w"], help="List Weapon Types")
    weapons.add_argument("--json", action='store_true', help="Output as JSON")
    weapons.set_defaults(func=weapon_types)

    args = p.parse_args()

    args.func(args)
