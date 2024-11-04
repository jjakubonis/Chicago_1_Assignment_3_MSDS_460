from census import Census
from us import states
from pulp import LpProblem, LpMinimize, LpVariable, lpSum, LpStatus, PULP_CBC_CMD
import os
import requests
import pandas as pd
import io
from dotenv import load_dotenv
import geopandas as gpd
import plotly.express as px
import json

load_dotenv()

CENSUS_API_KEY = os.getenv("CENSUS_API_KEY")

c = Census(key=CENSUS_API_KEY)
indiana = states.IN
counties_data = c.acs5.state_county(
    fields=(
        "NAME",
        "B01003_001E",  # Total pop
        "B02001_002E",  # White pop
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
        'white_population': int(county['B02001_002E']),
    }

# set up a dict for each county/district combo
prob = LpProblem("Indiana Redistricting", LpMinimize)
counties = list(county_data.keys())
districts = range(8)
x = LpVariable.dicts("county_district", 
                     [(i, j) for i in counties for j in districts], 
                     cat='Binary')

# pull county adjacency data
adj_url = "https://www2.census.gov/geo/docs/reference/county_adjacency.txt"
county_adj_response = requests.get(adj_url)
county_adj_txt = county_adj_response.text
county_adj = pd.read_csv(io.StringIO(county_adj_txt), sep='\t', names=['county', 'county_num', 'adj_county', 'adj_county_num'])
county_adj_df = pd.DataFrame(data=county_adj)
county_adj_df.fillna(method='ffill', inplace=True)
in_county_adj_df = county_adj_df[(county_adj_df['county'].str.contains('IN')) & (county_adj_df['adj_county'].str.contains('IN'))]
in_county_adj_df = in_county_adj_df.replace('IN', 'Indiana', regex=True)
in_county_adj_df = in_county_adj_df.drop(in_county_adj_df[in_county_adj_df.county_num == 18097.0].index)
in_county_adj_df = in_county_adj_df.drop(in_county_adj_df[in_county_adj_df.adj_county_num == 18097.0].index)

# create adjacent county dictionary
in_county_adj = {
    str(int(key)): [str(int(adj)) for adj in value['adj_county_num'].tolist()]
    for key, value in in_county_adj_df.groupby('county_num')
}
for key in in_county_adj:
    if key in in_county_adj[key]:
        in_county_adj[key].remove(key)
        
# cut edges variable
y = LpVariable.dicts("adj", 
                     [(i, j) for i in counties for j in in_county_adj.get(i, [])], 
                     cat='Binary')

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

# Variable for white population percentage
white_percentage = LpVariable.dicts("white_percentage", districts, lowBound=0, upBound=1)

for d in districts:
    total_pop_d = lpSum(county_data[c]['population'] * x[c, d] for c in counties)
    total_white_pop_d = lpSum(county_data[c]['white_population'] * x[c, d] for c in counties)
    
    # Define white percentage as a constraint
    prob += white_percentage[d] == total_white_pop_d / total_population
    
    prob += total_pop_d - target_pop <= deviation[d]
    prob += target_pop - total_pop_d <= deviation[d]
    
    # Enforce population to be within 5% of the target
    prob += total_pop_d >= 0.90 * target_pop
    prob += total_pop_d <= 1.10 * target_pop

    # Enforce white pop to be no more than 85%
    prob += white_percentage[d] <= .85

# cut edges constraint
for c in counties:
    for d in districts:
        # adjacency constraint
        prob += lpSum(x[adj, d] for adj in in_county_adj.get(c, [])) >= x[c, d]
        for adj in in_county_adj.get(c, []):
            prob += x[c, d] - x[adj, d] <= y[c, adj]
            prob += x[adj, d] - x[c, d] <= y[c, adj]



prob.solve(PULP_CBC_CMD(timeLimit=600))
print("Status:", LpStatus[prob.status])

# Output pop results
district_populations = {d: 0 for d in districts}
district_white_populations = {d: 0 for d in districts}
for c in counties:
    for d in districts:
        if x[c, d].varValue == 1:
            district_populations[d] += county_data[c]['population']
            district_white_populations[d] += county_data[c]['white_population']

for d in districts:
    print(f"District {d + 1} population: {district_populations[d]}")
    print(f"District {d + 1} white percentage: {district_white_populations[d] / district_populations[d]}")

us_counties = gpd.read_file("https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json")
indiana_counties = us_counties[us_counties['id'].str.startswith('18')]

# Add Marion County as its own district
district_assignments = {c: -1 for c in counties}  
district_assignments["18097"] = 0  

# Assign other counties to districts based on the optimization result
for c in counties:
    for d in districts:
        if x[c, d].varValue == 1:
            district_assignments[c] = d + 1  

districts_df = pd.DataFrame({
    'FIPS': list(district_assignments.keys()),
    'District': list(district_assignments.values())
})

districts_df['FIPS'] = districts_df['FIPS'].apply(lambda x: str(x).zfill(5))
indiana_counties['id'] = indiana_counties['id'].apply(lambda x: str(x).zfill(5))

indiana_counties = indiana_counties.merge(districts_df, left_on='id', right_on='FIPS', how='left')
fig = px.choropleth(
    indiana_counties,
    geojson=json.loads(indiana_counties.to_json()),
    locations='id',
    color='District',
    featureidkey='properties.id',
    labels={'District': 'District'},
    title='Indiana Redistricting Map',
)

fig.update_geos(fitbounds="locations", visible=False)
fig.write_image('Indiana-Districts.png')