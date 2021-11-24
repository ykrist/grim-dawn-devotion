#!/usr/bin/env python
import dataclasses
import sys

from gurobipy import *
from common import *
from termcolor import colored
import logging
import contextlib


@dataclasses.dataclass
class OutputSettings:
    show_all_bonuses: bool = False
    json: bool = False


class Subproblem:
    def __init__(self, data: Data, config: Config, target_constellations: Set[str], turns: int):
        model = Model()
        turns = range(turns)
        if config.log_level > logging.DEBUG:
            model.setParam('OutputFlag', 0)
        # Amount of each affinity we have the end of turn t
        Q = model.addVars(data.affinities, turns, name="Q")
        # Amount of points we've used have the end of turn t
        P = model.addVars(turns, name="P", ub=config.num_points)

        # Is constellation c active at the end of turn t?
        Y = model.addVars(data.constellations, turns, vtype=GRB.BINARY, name="Y")

        # Do we pick (p=1) or unpick (p=-1) constellation c on turn t?
        Z = model.addVars(data.constellations, [1, -1], turns, vtype=GRB.BINARY, name="Z")

        # Do we pick anything on turn t?
        W = model.addVars(turns, vtype=GRB.BINARY, name="W")

        constraints = {}

        constraints["affinity_req_pick"] = {
            (c, t, a): model.addConstr(Z[c, 1, t] * d <= (0 if t == 0 else Q[a, t - 1]))
            for t in turns
            for c in data.constellations
            for a, d in data.affinity_req[c].items()
        }
        constraints["affinity_req_unpick"] = {
            (c, t, a): model.addConstr(Y[c, t] * d <= Q[a, t])
            for t in turns
            for c in data.constellations if c not in data.self_sufficient_constellations
            for a, d in data.affinity_req[c].items()
        }

        constraints["calc_Q"] = {
            (t, a): model.addConstr(
                Q[a, t] == quicksum(Y[c, t] * data.affinity_bonus[c].get(a, 0) for c in data.constellations))
            for t in turns
            for a in data.affinities
        }

        constraints["inventory"] = {
            (c, t): model.addConstr(
                Y[c, t] == (Y[c, t - 1] if t > 0 else 0) + Z[c, 1, t] - Z[c, -1, t]
            )
            for c in data.constellations
            for t in turns
        }

        constraints["calc_P"] = {
            t: model.addConstr(
                P[t] == quicksum(len(stars) * Y[c, t] for c, stars in data.constellations.items())
            )
            for t in turns
        }

        constraints["max_points"] = {
            t: model.addConstr(
                P[t - 1] + quicksum(
                    len(stars) * Z[c, 1, t] for c, stars in data.constellations.items()) <= config.num_points
            )
            for t in turns[1:]
        }

        constraints["max_points"][0] = model.addConstr(
            quicksum(len(stars) * Z[c, 1, 0] for c, stars in data.constellations.items()) <= config.num_points
        )

        constraints["antisymmetry"] = {
            t: model.addConstr(W[t] <= W[t - 1])
            for t in turns[1:]
        }

        constraints["link_wz"] = {
            (c, t): model.addConstr(Z[c, 1, t] + Z[c, -1, t] <= W[t])
            for t in turns
            for c in data.constellations
        }

        constraints["must_add_something"] = {
            t: model.addConstr(quicksum(Z[c, 1, t] for c in data.constellations) >= W[t])
            for t in turns
        }

        constraints["final_Y"] = {
            c: model.addConstr(Y[c, turns[-1]] == int(c in target_constellations))
            for c in data.constellations
        }

        self.turns = turns
        self.data = data
        self.constraints = constraints
        self.Y = Y
        self.Z = Z
        self.W = W
        self.Q = Q
        self.P = P
        self.model = model

    def is_feasible(self) -> bool:
        self.model.optimize()
        status = self.model.Status
        if status == GRB.OPTIMAL:
            return True
        elif status == GRB.INFEASIBLE:
            return False
        else:
            raise Exception("unexpected GRB status", status)

    def _sum_refunds(self) -> LinExpr:
        return quicksum(
            self.Z[c, -1, t] * len(stars) for c, stars in self.data.constellations.items() for t in self.turns)

    def minimise_refunds(self) -> Optional[int]:
        logging.info(f"minimise refunds (max turns = {len(self.turns)})")
        self.model.setObjective(self._sum_refunds(), GRB.MINIMIZE)
        self.model.optimize()
        if self.model.Status == GRB.INFEASIBLE:
            return None
        elif self.model.Status == GRB.OPTIMAL:
            return round(self.model.ObjVal)
        else:
            raise Exception("unexpected GRB status", self.model.Status)

    def fix_num_refunds(self, n: int) -> Constr:
        try:
            return self.constraints["fix_num_refunds"]
        except KeyError:
            c = self.model.addConstr(self._sum_refunds() == n)
            self.constraints["fix_num_refunds"] = c
            return c

    def unfix_num_refunds(self):
        try:
            c = self.constraints.pop("fix_num_refunds")
        except KeyError:
            return
        self.model.remove(c)

    def minimise_turns(self) -> int:
        logging.info(f"minimise turns (max turns = {len(self.turns)})")
        self.model.setObjective(self.W.sum(), GRB.MINIMIZE)
        self.model.optimize()
        return round(self.model.ObjVal)

    def get_solution(self) -> List:
        actions = []
        active_constellations = set()
        for t in self.turns:
            if self.W[t].x > .9:
                added = set()
                removed = set()
                for c in self.data.constellations:
                    if self.Z[c, 1, t].x > .9:
                        added.add(c)
                    if self.Z[c, -1, t].x > .9:
                        removed.add(c)

                if added:
                    active_constellations |= added
                    actions.append({
                        "add": added,
                        "constellations": active_constellations.copy(),
                    })
                if removed:
                    active_constellations -= removed
                    actions.append({
                        "remove": removed,
                        "constellations": active_constellations.copy(),
                    })

        for d in actions:
            d['affinity'] = total_affinity(self.data, d['constellations'])
            d['points'] = total_points(self.data, d['constellations'])

        return actions


def total_affinity(data: Data, cons: Iterable[str]) -> Dict[str, int]:
    return {a: sum(data.affinity_bonus[c].get(a, 0) for c in cons) for a in data.affinities}


def total_points(data: Data, cons: Iterable[str]) -> int:
    return sum(len(data.constellations[c]) for c in cons)


def solve_final_constellation_path(data: Data, config: Config, constellations: Set[str]):
    previous_sp = None
    num_prev_refunds = None
    for turns in TURNS_SCHEDULE:
        sp = Subproblem(data, config, constellations, turns)
        num_refunds = sp.minimise_refunds()
        if num_prev_refunds is not None and num_prev_refunds == num_refunds:
            previous_sp.fix_num_refunds(num_refunds)
            previous_sp.minimise_turns()
            return previous_sp.get_solution()

        previous_sp = sp
        num_prev_refunds = num_refunds


TURNS_SCHEDULE = [4, 8, 12, 20, 30, 60, 200]


def grb_callback(model: Model, where: int):
    if where == GRB.Callback.MIPSOL:
        data: Data = model._data
        config: Config = model._config
        Y = model._Y
        Yv = model.cbGetSolution(model._Y)
        target_constellations = {c for c, val in Yv.items() if val > .9}
        logging.info(f"solving subproblem {target_constellations}", )
        for turns in TURNS_SCHEDULE:
            if Subproblem(data, config, target_constellations, turns).is_feasible():
                logging.info(f"feasible with {turns} turns")
                break
            else:
                logging.warning(f"infeasible with {turns} turns")
        else:
            logging.warning("add cut")
            model.cbLazy(quicksum(Y[c] for c in target_constellations) <= len(target_constellations) - 1)


def insert_straggler_stars(data: Data, config: Config, straggler_stars: List[Star], sp_sol: List):
    unfinished_cons = group_stars_by_constellation(straggler_stars)

    for c, stars in unfinished_cons.items():
        first_legal = 0
        for k in reversed(range(len(sp_sol))):
            for a, d in data.affinity_req[c].items():
                if d > sp_sol[k]['affinity'][a]:
                    break
            else:
                if sp_sol[k]['points'] + len(stars) <= config.num_points:
                    continue

            first_legal = k + 1
            break
        sp_sol[first_legal].setdefault("straggler_stars", []).extend(stars)
        for k2 in range(first_legal, len(sp_sol)):
            sp_sol[k2]['points'] += len(stars)


def group_stars_by_constellation(stars: Iterable[Star]) -> Dict[str, List[Star]]:
    by_constellation = {}
    for s in stars:
        by_constellation.setdefault(s[0], []).append(s)
    return by_constellation


def _fmt_stragglers(data: Data, stars: Iterable[Star], indent=0) -> str:
    cons = group_stars_by_constellation(stars)
    lines = []
    for c, stars in sorted(cons.items()):
        lines.append(colored(c, 'yellow'))

        bonus_lines = []
        mark_star = set()
        for s in sorted(stars):
            mark_star.add(len(bonus_lines))
            for b in data.bonuses.get(s, []):
                bonus_lines.append(b.display())
            if s in data.celestial_powers:
                bonus_lines.append(data.celestial_powers[s].desc)
            if not bonus_lines:
                bonus_lines.append("[no bonus]")
            bonus_lines.append("")

        if bonus_lines:
            bonus_lines.pop()

        for i, l in enumerate(bonus_lines):
            if i in mark_star:
                bonus_lines[i] = "(*) " + l
            else:
                bonus_lines[i] = " |  " + l

        lines.extend(bonus_lines)
        lines.append("")

    return "\n".join(" " * indent + l for l in lines)


def calculate_total_bonus(data: Data, chosen_stars: List[Star]) -> List[Bonus]:
    aggregate = {}
    bonus_list = []
    for s in chosen_stars:
        for b in data.bonuses.get(s, []):
            if b.prob is not None or b.duration is not None or b.value_range is not None:
                bonus_list.append(b)
            else:
                key = (b.kind, b.apply_to_pets)
                if key not in aggregate:
                    aggregate[key] = b
                else:
                    old = aggregate[key]
                    aggregate[key] = dataclasses.replace(old, value=old.value + b.value)
    bonus_list.extend(aggregate.values())
    return bonus_list


def pretty_print_solution(
        data: Data,
        sol: Dict,
        settings: OutputSettings = None
):
    settings = settings or OutputSettings()
    actions = sol['order']
    chosen_stars = sol['stars']

    for action in actions:
        try:
            title = "Remove Constellations"
            changed = action['remove']
            highlight_change = "red"
            prefix = "    -"
        except KeyError:
            title = "Add Constellations"
            changed = action['add']
            highlight_change = "green"
            prefix = "    +"

        print(title)
        for c in sorted(changed):
            if c in changed:
                print(colored(f"{prefix} {c}", highlight_change))
            else:
                print(" " * (len(prefix) + 1) + c)
        print()
        if 'straggler_stars' in action:
            print("Unlocked Stars")
            print(_fmt_stragglers(data, action['straggler_stars'], indent=4))


    print("Total Bonuses")
    sortkey = lambda b: (config.objective.get(b.objective_key(), 0) * -b.value, b.apply_to_pets, b.lex_key())
    for b in sorted(calculate_total_bonus(data, chosen_stars), key=sortkey):
        text = b.display()
        if b.objective_key() in config.objective:
            obj = b.value * config.objective[b.objective_key()]
            text = colored(f"[{obj:>9.1f}] " + text, 'blue', attrs=['bold'])
        elif not settings.show_all_bonuses:
            continue
        else:
            text = colored(" " * 10 + text, attrs=['dark'])
        print(text)


def main(data: Data, config: Config, output: OutputSettings):
    force_stars = config.desired_stars
    with contextlib.redirect_stdout(open(os.devnull, 'w')):
        model = Model()
    model._data = data
    model._config = config
    config.adjust_objective()
    if config.log_level > logging.DEBUG:
        model.setParam('OutputFlag', 0)
    model.setParam('LazyConstraints', 1)
    # Amount of each affinity we have
    Q = {a: model.addVar(name=f"Q[{a}]") for a in data.affinities}

    # Do we take star s?
    X = {s: model.addVar(vtype=GRB.BINARY, name=f"X[{s[0]},{s[1]}]") for s in data.stars}

    for s in force_stars:
        X[s].lb = 1

    # do we finish constellation c?
    Y = {c: model.addVar(vtype=GRB.BINARY, name=f"Y[{c}]") for c in data.constellations}
    model._Y = Y

    constraints = {}
    constraints['finish_constellation'] = {
        s: model.addConstr(Y[s[0]] <= X[s])
        for s in data.stars
    }

    constraints['pred'] = {
        (s1, s2): model.addConstr(X[s1] <= X[s2])
        for s1, s2 in data.predecessor.items()
    }

    constraints['affinity_req'] = {
        (s, a): model.addConstr(X[s] * amount <= Q[a])
        for s in data.stars
        for a, amount in data.affinity_req[s[0]].items()
    }

    constraints['affinity_bonus'] = {
        a: model.addConstr(Q[a] == quicksum(Y[c] * bonus.get(a, 0) for c, bonus in data.affinity_bonus.items()))
        for a in data.affinities
    }

    constraints['num_points'] = model.addConstr(quicksum(X.values()) == config.num_points)

    model.setObjective(quicksum(
        config.objective.get(b.objective_key(), 0) * b.value * X[s]
        for s, blist in data.bonuses.items() if s not in config.ignore_stars
        for b in blist
    ), GRB.MAXIMIZE)

    model.optimize(grb_callback)

    if model.status == GRB.INFEASIBLE:
        print("Impossible to satisfy requirements", file=sys.stderr)
        sys.exit(1)

    chosen_stars = [s for s, var in X.items() if var.x > .9]
    chosen_stars.sort()

    final_constellations = []
    for c, var in Y.items():
        if var.x > .9:
            final_constellations.append(c)
        elif all(X[s].x > 0.9 for s in data.constellations[c]):
            final_constellations.append(c)

    straggler_stars = [s for s in chosen_stars if s[0] not in final_constellations]
    order = solve_final_constellation_path(data, config, final_constellations)
    insert_straggler_stars(data, config, straggler_stars, order)
    sol = {"stars": chosen_stars, "order": order }
    if output.json:
        print(dumps_json(sol))
    else:
        pretty_print_solution(data, sol, output)

if __name__ == '__main__':
    import argparse
    import configure

    p = argparse.ArgumentParser()
    p.add_argument('-c', "--config", type=Path, default=None)
    p.add_argument('-a', "--all", action='store_true', help="List all bonuses obtained.")
    p.add_argument("-l", "--load",type=Path, default=None, help='Load an existing solution from a JSON file')
    p.add_argument('--json', action='store_true', help='Output as JSON')

    args = p.parse_args()

    config = configure.load_config_or_exit(args.config)

    logging.basicConfig(level=config.log_level)
    logging.getLogger("gurobipy").setLevel(logging.CRITICAL)

    output = OutputSettings(
        show_all_bonuses=args.all,
        json=args.json,
    )

    data = Data.load()
    if args.load:
        sol = load_json(args.load)
        pretty_print_solution(data, sol, output)
    else:
        main(data, config, output)
