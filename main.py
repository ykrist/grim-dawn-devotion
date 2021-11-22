from gurobi import *
from common import *

DATA = load_json("data/main.json")

AFFINITIES = ["chaos", "primordial", "eldritch", "order", "ascendant"]
STARS = []
CELESTIAL_POWERS = {}
BONUSES = {}
PRED = {}
CONSTELLATION = {}
AFFINITY_REQ = {}
AFFINITY_BONUS = {}
BONUS_KINDS = set()

for c in DATA:
    cons = c['name']
    starlist = []
    for i, x in enumerate(c['bonus']):
        star = (cons, i)
        if isinstance(x, CelestialPower):
            CELESTIAL_POWERS[star] = x
        else:
            BONUSES[star] = x
            BONUS_KINDS.update(b.kind for b in x)
        STARS.append(star)
        starlist.append(star)
    CONSTELLATION[cons] = starlist

    for i, succ in c['topology']:
        i = (cons, i)
        for j in succ:
            j = (cons, j)
            assert j not in PRED
            PRED[j] = i


    AFFINITY_REQ[cons] = dict(c['affinity_required'])
    AFFINITY_BONUS[cons] = dict(c['affinity_bonus'])

objective = {
    'energy regenerated per second' : 5,
    '% energy regeneration' : 2,
    '% aether damage' : .1,
    '% elemental damage' : .2,
}

for kind in objective:
    assert kind in BONUS_KINDS, f"no such bonus: `{kind}` "
celestial_powers = [

]

model = Model()

# Amount of each affinity we have
Q = { a: model.addVar(name=f"Q[{a}]") for a in AFFINITIES}

# Do we take star s?
X = { s: model.addVar(vtype=GRB.BINARY, name=f"X[{s[0]},{s[1]}]") for s in STARS}

# do we finish constellation c?
Y = { c: model.addVar(vtype=GRB.BINARY, name=f"Y[{c}]") for c in CONSTELLATION }

NUM_POINTS = 55

constraints = {}
constraints['finish_constellation'] = {
    s: model.addConstr(Y[s[0]] <= X[s])
    for s in STARS
}

constraints['pred'] = {
    (s1, s2): model.addConstr(X[s1] <= X[s2])
    for s1, s2 in PRED.items()
}

constraints['affinity_req'] = {
    (s, a): model.addConstr(X[s] * amount <= Q[a])
    for s in STARS
    for a, amount in AFFINITY_REQ[s[0]].items()
}

constraints['affinity_bonus'] = {
    a: model.addConstr(Q[a] == quicksum(Y[c] * bonus.get(a, 0) for c, bonus in AFFINITY_BONUS.items()))
    for a in AFFINITIES
}

constraints['num_points'] = model.addConstr(quicksum(X.values()) == NUM_POINTS)

model.setObjective(quicksum(
    objective.get(b.kind, 0) * b.value * X[s]
    for s, blist in BONUSES.items()
    for b in blist
), GRB.MAXIMIZE)
model.optimize()


chosen_stars = [s for s, var in X.items() if var.x > .9]
chosen_stars.sort()

print('STARS')
for c, i in chosen_stars:
    print(f'{c} {i}')
print()

print('COMPLETED CONSTELLATIONS')
for c, var in Y.items():
    if var.x > .9:
        print(c)
print()

print('FINAL AFFINITY')
for a in AFFINITIES:
    print(round(Q[a].x), a.capitalize())
print()

print("TOTAL BONUSES")
total_bonus = {}
for s in chosen_stars:
    for b in BONUSES.get(s, []):
        try:
            total_bonus[b.kind] += b.value
        except KeyError:
            total_bonus[b.kind] = b.value

total_bonus = [(v * objective.get(k, 0), k, v)  for k, v in total_bonus.items()]
total_bonus.sort(reverse=True)

for val, kind, amt in total_bonus:
    print(f"{amt} {kind} ({val})")

