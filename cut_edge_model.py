from census import Census
from us import states
from pulp import LpProblem, LpMinimize, LpVariable, lpSum, PULP_CBC_CMD, LpStatus
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

county_data = pd.DataFrame.from_dict(counties_data)
county_data.columns = ['name', 'population', 'state_num', 'county_num']
county_data['name'] = county_data['name'].str.replace(', Indiana', '')

#pull country adjacency data
adj_url = "https://www2.census.gov/geo/docs/reference/county_adjacency.txt"
county_adj_response = requests.get(adj_url)
county_adj_txt = county_adj_response.text
county_adj = pd.read_csv(io.StringIO(county_adj_txt), sep = '\t', names = ['county', 'county_num', 'adj_county', 'adj_county_num'])
county_adj_df = pd.DataFrame(data = county_adj)
county_adj_df.fillna(method = 'ffill', inplace = True)
in_county_adj_df = county_adj_df[(county_adj_df['county'].str.contains('IN')) & (county_adj_df['adj_county'].str.contains('IN'))]
in_county_adj_df = in_county_adj_df.replace(', IN', '', regex = True)

#create adjacent county dictionary
in_county_adj = {key : value['adj_county'].tolist() for key, value in in_county_adj_df.groupby('county')}
for key in in_county_adj:
    if key in in_county_adj[key]:
        in_county_adj[key].remove(key)




# set up a dict for each county/district combo
prob = LpProblem("Indiana Redistricting", LpMinimize)
counties = county_data['name']
districts = range(9)
x = LpVariable.dicts("county_district", 
                     [(i, j) for i in counties for j in districts], 
                     cat='Binary')


#cut edges variable
y = LpVariable.dicts("adj", 
                     [(i, j) for i in counties for j in in_county_adj[i]], 
                     cat='Binary')

# With population, we know what the best case for equal pop distribution is
# Constraints need to look to the deviation from this target

total_population = sum(county_data['population'])
target_pop = total_population / len(districts)

# Objective function: Minimize the sum of cut edges
prob += lpSum(y[i, j] for i in counties for j in in_county_adj[i])

# each county should be in one district only
for c in counties:
    prob += lpSum(x[c, d] for d in districts) == 1


for d in districts:
    total_pop_d = lpSum(int(county_data['population'][county_data['name'] == c]) * x[c, d] for c in counties)
    
    # Enforce population to be within 10% of the target
    prob += total_pop_d >= 0.70 * target_pop
    prob += total_pop_d <= 1.3 * target_pop



#cut edges constraint
for c in counties:
        for d in districts:
            for adj in in_county_adj[c]:
                prob += x[c, d] - x[adj, d] <= y[c, adj]
                prob += x[adj, d] - x[c, d] <= y[c, adj]


prob.solve(PULP_CBC_CMD(gapRel = .02))
print("Status:", LpStatus[prob.status])

# Output pop results
district_populations = {d: 0 for d in districts}
for c in counties:
    for d in districts:
        if x[c, d].varValue == 1:
            district_populations[d] += int(county_data['population'][county_data['name'] == c])

for d in districts:
    print(f"District {d + 1} population: {district_populations[d]}")