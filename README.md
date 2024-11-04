# Chicago_1_Assignment_3_MSDS_460
Algorithmic redistricting group assignment for Northwestern University MSDS 460 

## Overview

To algorithmically redistrict Indiana, this script uses Census data to distribute counties into districts with the goal of equal population distribution.

Census data is processed into a dictionary mapping each county's GEOID to its name and population.

A linear programming problem is defined using pulp, with the objective to minimize population deviations. Each country/district combination has a binary variable, and each district has a deviation from an equal population target. 

The solution constraints include that each county is assigned to one district, and district populations stay within 10% of the target. The objective function minimizes the sum of deviations from the target population.


## Setup
- Request an [API key](https://api.census.gov/data/key_signup.html) from the US Census Bureau
- create a `.env` file modeled after the `.env_example` file
    - paste the API key in the given quotes
- in the respository directory, create and activate a virtual environment (assuming powershell)
    - ` py -m venv .venv`
    - `./.venv/scripts/activate`
- install dependencies with
    - `py -m pip install --upgrade pip`
    - `py -m pip install -r requirements.txt`

- execute the main program
    - `py redistrict_indiana.py`