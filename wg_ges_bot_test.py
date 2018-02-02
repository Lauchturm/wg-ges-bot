import wg_ges_bot_tor_6_cities
from collections import defaultdict

mitbewohnerinFuer21qm = {
    'title': 'Mitbewohnerin für 21 qm² Zimmer + gemeinsames Wohnzimmer + Balkon gesucht :)',
    'size': '21m²',
    'rent': '545',
    'availability': 'Verfügbar: 01.03.2018 - 01.10.2018',
    'wg_details': '2er WG (1w,0m) in Berlin Charlottenburg, Horstweg',
    'searching_for': '🚺 gesucht'
}

def test_empty_filters():
    wg_ges_bot_tor_6_cities.filters = defaultdict(dict)
    assert wg_ges_bot_tor_6_cities.check_filters(4711, mitbewohnerinFuer21qm) == True

def test_filter_rent():
    wg_ges_bot_tor_6_cities.filters = defaultdict(dict)
    wg_ges_bot_tor_6_cities.filters[4711] = {'rent': 400}
    assert wg_ges_bot_tor_6_cities.check_filters(4711, mitbewohnerinFuer21qm) == False

