from wg_ges_bot import Ad, Subscriber, FilterRent, FilterGender, FilterAvailability, FilterCity
from collections import defaultdict
import pytest
import datetime

mitbewohnerinFuer21qm = {
    'city': 'ber',
    'url': 'https://www.wg-gesucht.de/wg-zimmer-in-Berlin-Charlottenburg.5761535.html',
    'title': 'Mitbewohnerin für 21 qm² Zimmer + gemeinsames Wohnzimmer + Balkon gesucht :)',
    'size': '21m²',
    'rent': '545',
    'availability': 'Verfügbar: 25.02.2018',
    'wg_details': '2er WG (1w,0m) in Berlin Charlottenburg, Horstweg',
    'searching_for': '🚺 gesucht'
}

nettenMenschenDict = {
    'city': 'ber',
    'url': 'https://www.wg-gesucht.de/wg-zimmer-in-Berlin-Charlottenburg-Wilmersdorf.6400226.html',
    'title': 'Schönes helles WG Zimmer frei für netten Menschen! :)',
    'size': '16m²',
    'rent': '350',
    'availability': 'Verfügbar: 01.03.2018 - 31.03.2018',
    'wg_details': '2er WG (1w,0m) in Berlin Charlottenburg-Wilmersdorf, Quellweg',
    'searching_for': '🚺 oder 🚹 gesucht'
}
nettenMenschenString = 'Schönes helles WG Zimmer frei für netten Menschen! :)\n16m² - 350€\n2er WG (1w,0m) in Berlin Charlottenburg-Wilmersdorf, Quellweg\nVerfügbar: 01.03.2018 - 31.03.2018\n🚺 oder 🚹 gesucht'

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
    ad = Ad.from_dict(mitbewohnerinFuer21qm)
    assert mySubscriber.is_interested_in(ad) == False

def test_filter_rent_ok():
    mySubscriber = Subscriber(4711)
    mySubscriber.add_filter(FilterRent, 600)
    ad = Ad.from_dict(mitbewohnerinFuer21qm)
    assert mySubscriber.is_interested_in(ad)

def test_filter_gender_female_only():
    mySubscriber = Subscriber(4711)
    mySubscriber.add_filter(FilterGender, 'm')
    ad = Ad.from_dict(mitbewohnerinFuer21qm)
    assert mySubscriber.is_interested_in(ad) == False

def test_filter_gender_ok():
    mySubscriber = Subscriber(4711)
    mySubscriber.add_filter(FilterGender, 'w')
    ad = Ad.from_dict(mitbewohnerinFuer21qm)
    assert mySubscriber.is_interested_in(ad)

def test_ad_to_chat_message():
    ad = Ad.from_dict(nettenMenschenDict)
    assert ad.to_chat_message() == nettenMenschenString

def test_parsing_of_availability():
    ad = Ad.from_dict(nettenMenschenDict)
    assert ad.available_from() == datetime.datetime(day=1,  month=3, year=2018)
    assert ad.available_to()   == datetime.datetime(day=31, month=3, year=2018)

def test_parsing_of_availability():
    ad = Ad.from_dict(mitbewohnerinFuer21qm)
    assert ad.available_from() == datetime.datetime(day=25, month=2, year=2018)
    assert ad.available_to()   == None

def test_filter_available_3months_is_ok_forever():
    ad = Ad.from_dict(mitbewohnerinFuer21qm)
    mySubscriber = Subscriber(4711)
    mySubscriber.add_filter(FilterAvailability, datetime.timedelta(weeks=12))
    assert mySubscriber.is_interested_in(ad)

def test_filter_available_3months_not_ok():
    ad = Ad.from_dict(nettenMenschenDict)
    mySubscriber = Subscriber(4711)
    mySubscriber.add_filter(FilterAvailability, datetime.timedelta(weeks=12))
    assert mySubscriber.is_interested_in(ad) == False

def test_filter_available_2months_ok():
    ad = Ad.from_dict(nettenMenschenDict)
    mySubscriber = Subscriber(4711)
    mySubscriber.add_filter(FilterAvailability, datetime.timedelta(weeks=4))
    assert mySubscriber.is_interested_in(ad)

def test_subscriber_constructor_parses_int():
    mySubscriber = Subscriber('4711')
    assert mySubscriber.chat_id == 4711

def test_subscriber_review_ads_returns_empty_set_on_first_run():
    mySubscriber = Subscriber(4711)
    ad1 = Ad.from_dict(nettenMenschenDict)
    ad2 = Ad.from_dict(mitbewohnerinFuer21qm)
    # this behaviour will prevent current ads to be sent to the user
    assert mySubscriber.review_ads({ad1, ad2}, 'ber') == set()

def test_subscriber_review_ads_returns_new_ads():
    mySubscriber = Subscriber(4711)
    ad1 = Ad.from_dict(nettenMenschenDict)
    ad2 = Ad.from_dict(mitbewohnerinFuer21qm)
    mySubscriber.review_ads({}, 'ber')
    assert mySubscriber.review_ads({ad1}, 'ber') == {ad1}
    assert mySubscriber.review_ads({ad1, ad2}, 'ber') == {ad2}
    assert mySubscriber.review_ads({ad1, ad2}, 'ber') == set()
    assert mySubscriber.review_ads({ad1, ad2}, 'ber') == set()

def test_subscriber_review_ads_drops_old_ads():
    mySubscriber = Subscriber(4711)
    ad1 = Ad.from_dict(nettenMenschenDict)
    ad2 = Ad.from_dict(mitbewohnerinFuer21qm)
    mySubscriber.review_ads({ad1,ad2}, 'ber')
    # empty, because ad2 was in the list before
    assert mySubscriber.review_ads({ad2}, 'ber') == set()
    # now, this behaviour happens if an ad was updated after a day
    # it was not scraped the last time, but now it should be resent
    assert mySubscriber.review_ads({ad1, ad2}, 'ber') == {ad1}

def test_subscriber_review_ads_drops_old_ads_for_that_city():
    mySubscriber = Subscriber(4711)
    ad1 = Ad.from_dict(nettenMenschenDict)
    ad2 = Ad.from_dict(mitbewohnerinFuer21qm)
    assert mySubscriber.review_ads({ad1}, 'ber') == set()
    assert mySubscriber.review_ads({ad2}, 'muc') == set()
    assert mySubscriber.review_ads({ad1}, 'ber') == set()
    assert mySubscriber.review_ads({},    'ber') == set()
    assert mySubscriber.review_ads({ad1}, 'ber') == {ad1}
    # these two sets are completely independent of each other
    assert mySubscriber.review_ads({ad2}, 'muc') == set()

def test_subscriber_review_ads_drops_old_ads_for_that_city():
    mySubscriber = Subscriber(4711)
    ad1 = Ad.from_dict(nettenMenschenDict)
    ad2 = Ad.from_dict(mitbewohnerinFuer21qm)
    mySubscriber.review_ads({ad1}, 'ber') == set()
    assert mySubscriber.already_had(ad1)
    assert mySubscriber.already_had(ad2) == False


def test_filter_city_ok():
    mySubscriber = Subscriber(4711)
    mySubscriber.add_filter(FilterCity, ['ber'])
    ad = Ad.from_dict(mitbewohnerinFuer21qm)
    assert mySubscriber.is_interested_in(ad)

def test_filter_city_not_ok():
    mySubscriber = Subscriber(4711)
    mySubscriber.add_filter(FilterCity, ['muc', 'stuggi'])
    ad = Ad.from_dict(mitbewohnerinFuer21qm)
    assert mySubscriber.is_interested_in(ad) == False

def test_filter_to_string():
    assert str(FilterRent(500)) == 'FilterRent: 500'

def test_admin_filters_to_string():
    admin = Subscriber(4711)
    admin.add_filter(FilterRent, 300)
    admin.add_filter(FilterGender, 'm')
    admin.add_filter(FilterAvailability, datetime.timedelta(weeks=4))
    assert admin.all_filters() == "['FilterRent: 300', 'FilterGender: m', 'FilterAvailability: 28 days, 0:00:00']"
