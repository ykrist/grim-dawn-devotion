import dataclasses
import json
from pathlib import Path
from typing import *

@dataclasses.dataclass(frozen=True, eq=True)
class Bonus:
    apply_to_pets: bool
    value: float
    kind: str
    prob: Optional[float] = None
    duration: Optional[float] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None


@dataclasses.dataclass(frozen=True, eq=True)
class CelestialPower:
    desc: str

def serialize_json(obj):
    if dataclasses.is_dataclass(obj):
        return {
            "_type": obj.__class__.__name__,
            "data" : dataclasses.asdict(obj)
        }

    raise NotImplementedError

def deserialize_json(data: dict):
    try:
        typename = data["_type"]
    except KeyError:
        return data
    else:
        cls = globals()[typename]
        return cls(**data['data'])

def load_json(p: Path) -> dict:
    with open(p, 'r') as fp:
        return json.load(fp, object_hook=deserialize_json)

def dump_json(obj, p: Path) -> dict:
    with open(p, 'w') as fp:
        return json.dump(obj, fp, default=serialize_json, indent="  ")
