# Devotion Solver for [Grim Dawn](https://grimdawn.fandom.com/wiki/Grim_Dawn)
![image](./banner.png)

## Installation
The main `solve.py` requires a [Gurobi](https://www.gurobi.com/downloads/end-user-license-agreement-academic/) license to run.  All the scripts require Python 3.7 or later.

### Using `virtualenv`
After cloning the repo, run this from the directory of this file: 
```bash
virtualenv venv
pip install -r requirements.txt
source venv/bin/activate
```


## Usage
Grim Dawn's Devotion system is pretty complicated.  The `solve.py` script will:
1. Figure out the best combination of stars in to end up with, subject which bonuses you decide are important (bigger weights = more important)
2. Calculate a way to reach that final combination by adding and possible refunding constellations (refunding a few Devotion points as possible)

In the config file `config.yaml`
```yaml
points: 37
bonuses:
- bonus: energy regenerated per second
  weight: 10
- bonus: '% lightning damage'
  weight: 2.5
- bonus: -% skill energy cost
  weight: 10
- bonus: '% energy regeneration'
  weight: 5
celestial_powers: 
  - "Black Blood of Yugol"
stars: 
ignore_stars:
  - "Oklaine's Lantern 0"
```

Running `./solve.py` will figure out the best allocation of your available Devoution points and figure out how to get there:
```
Add Constellations
    + Crossroads (Chaos)
    + Crossroads (Eldritch)
    + Crossroads (Order)

Add Constellations
    + Lotus
    + Quill

Remove Constellations
    - Crossroads (Order)

Add Constellations
    + Owl
    + Rat
    + Scholar's Light
    + Spider
    + Vulture

Unlocked Stars
    Hyrian
    (*) 40% elemental damage
     |  40% to all retaliation damage
    
    Rhowan's Crown
    (*) 6-9 elemental damage
     |  30% elemental damage
    
Remove Constellations
    - Crossroads (Chaos)

Unlocked Stars
    Yugol
    (*) 80% cold damage
     |  25 offensive ability
     |  
    (*) 80% acid damage
     |  25 offensive ability
     |  
    (*) 25% vitality resistance
     |  10% reflected damage reduction
     |  
    (*) 5 cold damage
     |  5 acid damage
     |  6% attack damage converted to health
     |  40% life leech resistance
     |  
    (*) Black Blood of Yugol (30% Chance when Hit)
    
Total Bonuses
[    392.5] 157% elemental damage
[     75.0] 15% energy regeneration
[     50.0] -5% skill energy cost
[     32.0] 3.2 energy regenerated per second
```

Each section of output must be completed in order; for example, Crossroads (Chaos), Crossroads (Eldritch) and Crossroads (Order) must all be picked before Lotus or Quill.  There are three types of section (excluding the summary at the end).  
- **Add Constellation**: Each of constellations in the group must be completed, but their order within the group doesn't matter
- **Remove Constellation**: Each of constellations in the group must be refunded, but their order within the group doesn't matter
- **Unlocked Stars**: These stars are part of constellations which are never finished.  They shown from the moment it becomes possible to choose them.  You can take them immediately, or focus on completing constellations instead.  In the example above, the star from Hyrian could have been chosen immediately, or after removing Crossroads (Chaos), or after getting Black Blood of Yugol.

The number on left in the **Total Bonuses** is the total objective value (`weight * value`) for the bonus type.

`configure.py` will create a config file for you.  For example,
```bash
./configure.py -b "fire damage"
```
will create a config file pre-filled with bonuses related to "fire damage". `./info.py b` will list all bonuses.