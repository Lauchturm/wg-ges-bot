import wg_ges_bot_tor_6_cities
from wg_ges_bot_tor_6_cities import Offer, Subscriber, FilterRent
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

def test_no_duplicate_filter():
    mySubscriber = Subscriber(4711)
    mySubscriber.add_filter(FilterRent, 500)
    assert len(mySubscriber.filters) == 1
    mySubscriber = Subscriber(4711)
    mySubscriber.add_filter(FilterRent, 500)
    assert len(mySubscriber.filters) == 1

def test_remove_filter():
    mySubscriber = Subscriber(4711)
    mySubscriber.add_filter(FilterRent, 500)
    assert len(mySubscriber.filters) == 1
    mySubscriber.remove_filter(FilterRent)
    assert len(mySubscriber.filters) == 0


def test_filter_rent_too_expensive():
    mySubscriber = Subscriber(4711)
    mySubscriber.add_filter(FilterRent, 500)
    offer = Offer.from_dict(mitbewohnerinFuer21qm)
    assert mySubscriber.is_interested_in(offer) == False

def test_filter_rent_ok():
    mySubscriber = Subscriber(4711)
    mySubscriber.add_filter(FilterRent, 600)
    offer = Offer.from_dict(mitbewohnerinFuer21qm)
    assert mySubscriber.is_interested_in(offer) == True

