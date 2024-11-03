from census import Census
from us import states
from pulp import LpProblem, LpMinimize, LpVariable, lpSum, LpStatus
import os
import requests
import pandas as pd
import io
from dotenv import load_dotenv

load_dotenv()

CENSUS_API_KEY = os.getenv("CENSUS_API_KEY")

c = Census(key=CENSUS_API_KEY)
indiana = states.IN
counties_data = c.acs5.state_county(
    fields=(
        "NAME",
        "B01003_001E",  #Total pop
    ),
    state_fips=indiana.fips,
    county_fips="*",
    year=2022
)
counties_data.remove(counties_data[48])

county_data = {}
for county in counties_data:
    geoid = county['state'] + county['county']
    county_data[geoid] = {
        'NAME': county['NAME'],
        'population': int(county['B01003_001E']),
    }

# set up a dict for each county/district combo
prob = LpProblem("Indiana Redistricting", LpMinimize)
counties = list(county_data.keys())
districts = range(8)
x = LpVariable.dicts("county_district", 
                     [(i, j) for i in counties for j in districts], 
                     cat='Binary')




#pull country adjaceny data
adj_url = "https://www2.census.gov/geo/docs/reference/county_adjacency.txt"
county_adj_response = requests.get(adj_url)
county_adj_txt = county_adj_response.text
county_adj = pd.read_csv(io.StringIO(county_adj_txt), sep = '\t', names = ['county', 'county_num', 'adj_county', 'adj_county_num'])
county_adj_df = pd.DataFrame(data = county_adj)
county_adj_df.fillna(method = 'ffill', inplace = True)
in_county_adj_df = county_adj_df[(county_adj_df['county'].str.contains('IN')) & (county_adj_df['adj_county'].str.contains('IN'))]
in_county_adj_df = in_county_adj_df.replace('IN', 'Indiana', regex = True)
in_county_adj_df = in_county_adj_df.drop(in_county_adj_df[in_county_adj_df.county_num == 18097.0].index)
in_county_adj_df = in_county_adj_df.drop(in_county_adj_df[in_county_adj_df.adj_county_num == 18097.0].index)

#create adjacent county dictionary
in_county_adj = {key : value['adj_county'].tolist() for key, value in in_county_adj_df.groupby('county')}
for key in in_county_adj:
    if key in in_county_adj[key]:
        in_county_adj[key].remove(key)






# With population, we know what the best case for equal pop distribution is
# Constraints need to look to the deviation from this target
deviation = LpVariable.dicts("deviation", districts, lowBound=0)
total_population = sum(county_data[c]['population'] for c in counties)
target_pop = total_population / len(districts)

# Objective function: Minimize the sum of deviations
prob += lpSum(deviation[d] for d in districts)

# each county should be in one district only
for c in counties:
    prob += lpSum(x[c, d] for d in districts) == 1

for d in districts:
    total_pop_d = lpSum(county_data[c]['population'] * x[c, d] for c in counties)
    prob += total_pop_d - target_pop <= deviation[d]
    prob += target_pop - total_pop_d <= deviation[d]
    
    # Enforce population to be within 5% of the target
    prob += total_pop_d >= 0.90 * target_pop
    prob += total_pop_d <= 1.10 * target_pop

prob.solve()
print("Status:", LpStatus[prob.status])

# Output pop results
district_populations = {d: 0 for d in districts}
for c in counties:
    for d in districts:
        if x[c, d].varValue == 1:
            district_populations[d] += county_data[c]['population']

for d in districts:
    print(f"District {d + 1} population: {district_populations[d]}")
