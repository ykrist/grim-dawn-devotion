import heapq

from common import *
import numpy as np
from heapq import heappop
AFFINITIES = ["chaos", "primordial", "eldritch", "order", "ascendant"]

@dataclasses.dataclass(frozen=True)
class Data:
    affinity_req: Dict[str, np.ndarray]
    affinity_bonus: Dict[str, np.ndarray]
    constellation_size: Dict[str, int]
    max_points: int
    target: FrozenSet[str]

def load_data(target: Iterable[str]) -> Data:
    def _convert_affinity(alist: List[Tuple[str, int]]) -> np.ndarray:
        v = np.zeros(5, dtype='u8')
        for a, val in alist:
            k = AFFINITIES.index(a)
            v[k] = val
        return v

    raw_data = load_json("data/main.json")

    affinity_req = {}
    affinity_bonus = {}
    cons_size = {}

    for c in raw_data:
        name = c['name']
        bonus = _convert_affinity(c['affinity_bonus'])
        req = _convert_affinity(c['affinity_required'])
        sz = len(c['bonus'])
        affinity_req[name] = req
        affinity_bonus[name] = bonus
        cons_size[name] = sz

    return Data(
        affinity_req=affinity_req,
        affinity_bonus=affinity_bonus,
        constellation_size=cons_size,
        max_points=55,
        target=frozenset(target),
    )



@dataclasses.dataclass(frozen=True, eq=True, order=True)
class Label:
    points_refunded: int
    affinities: np.ndarray = dataclasses.field(compare=False)
    points_remaining: int = dataclasses.field(compare=False)
    active_constellations: FrozenSet[str] = dataclasses.field(compare=False)
    history: Tuple[str,...] = dataclasses.field(compare=False)

    @classmethod
    def empty(cls, data: Data):
        return Label(
            points_refunded=0,
            affinities=np.zeros(5, dtype='u8'),
            points_remaining=data.max_points,
            active_constellations=frozenset(),
            history=tuple(),
        )

    def iter_removals(self, data: Data):
        for c in self.active_constellations:
            new_affinity = self.affinities - data.affinity_bonus[c]
            new_active_constellations = self.active_constellations - { c }
            if all(np.all(new_affinity >= data.affinity_req[c2]) for c2 in new_active_constellations):
                sz = data.constellation_size[c]
                yield Label(
                    points_refunded=self.points_refunded + sz,
                    affinities=new_affinity,
                    points_remaining=self.points_remaining + sz,
                    active_constellations=new_active_constellations,
                    history=self.history + ("[-] " + c,)
                )

    def iter_additions(self, data: Data):
        for c, sz in data.constellation_size.items():
            if c not in self.active_constellations:
                if sz <= self.points_remaining:
                    if np.all(data.affinity_req[c] <= self.affinities):
                        new_affinity = self.affinities + data.affinity_bonus[c]
                        yield Label(
                            points_refunded=self.points_refunded,
                            affinities=new_affinity,
                            points_remaining=self.points_remaining - sz,
                            active_constellations=self.active_constellations | { c },
                            history=self.history + ("[+] " + c,)
                        )

    def value(self, data):
        return len(data.target - self.active_constellations), self.points_refunded


TARGET = [
    "Alladrah's Phoenix",
    "Harpy",
    "Harvestman's Scythe",
    "Oklaine's Lantern",
    "Panther",
    "Quill",
    "Scholar's Light",
    "Toad",
]

data = load_data(TARGET)
empty = Label.empty(data)
heap = [(empty.value(data), empty)]

while True:
    _, label = heapq.heappop(heap)

    if label.active_constellations >= data.target:
        break

    for l in label.iter_additions(data):
        heapq.heappush(heap, (l.value(data), l))

    for l in label.iter_removals(data):
        heapq.heappush(heap, (l.value(data), l))

    print(l.points_refunded, l.points_remaining, len(heap))


