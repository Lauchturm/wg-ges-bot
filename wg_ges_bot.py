import datetime
from collections import defaultdict
from itertools import groupby


class Ad:
    datetime_format = '%d.%m.%Y'

    def __init__(self, url, title, city, size, rent, genders, availability, wg_details):
        self.url = url
        self.title = title
        self.city = city
        self.size = size
        self.rent = rent
        self.genders = genders
        self.wg_details = wg_details
        self.availability = availability

    def __hash__(self):
        return hash(self.url)

    def __eq__(self, other):
        """Overrides the default implementation"""
        if isinstance(self, other.__class__):
            return self.url == other.url
        return False

    def available_from(self):
        return self.availability[0]

    def available_to(self):
        return self.availability[1]

    @staticmethod
    def from_dict(info):
        url = info['url']
        title = info['title']
        city = info['city']
        size = info['size']
        wg_details = info['wg_details']
        availability = info['availability'].replace('Verfügbar: ', '').split(' - ')
        availability = list(map(lambda s: datetime.datetime.strptime(s, Ad.datetime_format), availability))
        availability.extend([None] * (2 - len(availability)))  # pad with None
        rent = int(info['rent'])
        genders = []
        if '🚺' in info['searching_for']:
            genders.append('w')
        if '🚹' in info['searching_for']:
            genders.append('m')
        return Ad(url, title, city, size, rent, genders, availability, wg_details)

    def to_chat_message(self):
        gender_mapping = {'w': '🚺', 'm': '🚹'}
        return '{}\n{} - {}€\n{}\n{}\n{}\n{}'.format(
            self.title,
            self.size,
            self.rent,
            self.wg_details,
            'Verfügbar: {}'.format(
                ' - '.join(
                    map(
                        lambda d: d.strftime(Ad.datetime_format),
                        [d for d in self.availability if d is not None])
                )
            ),
            ' oder '.join(
                map(
                    lambda g: gender_mapping[g],
                    self.genders
                )
            ) + ' gesucht',
            self.url
        )


class Filter:
    def __str__(self):
        return '{}: {}'.format(self.__class__.__name__, self.param)


class FilterRent(Filter):
    def __init__(self, max):
        self.param = max

    def allows(self, ad):
        return ad.rent <= self.param


class FilterCity(Filter):
    def __init__(self, cities):
        self.param = cities

    def allows(self, ad):
        return ad.city in self.param


class FilterGender(Filter):
    def __init__(self, gender):
        self.param = gender

    def allows(self, ad):
        return self.param in ad.genders


class FilterAvailableFrom(Filter):
    def __init__(self, needed_from):
        self.param = needed_from

    def allows(self, ad):
        if not ad.available_from():
            return True
        else:
            return self.param <= ad.available_from()


class FilterAvailableTo(Filter):
    def __init__(self, needed_until):
        self.param = needed_until

    def allows(self, ad):
        if not ad.available_to():
            return True
        else:
            return self.param <= ad.available_to()


class FilterAvailability(Filter):
    def __init__(self, minimal_availability):
        self.param = minimal_availability

    def allows(self, ad):
        if not (ad.available_to()) and not (ad.available_from()):
            return True
        else:
            duration = ad.available_to() - ad.available_from()
            return duration >= self.param


class Subscriber:
    def __init__(self, chat_id):
        self.chat_id = int(chat_id)
        self.filters = {}
        self.known_ads = defaultdict(lambda: None)
        self.cities = set()

    def add_filter(self, filter_class, param):
        self.filters[filter_class] = filter_class(param)

    def remove_filter(self, filter_class):
        self.filters.pop(filter_class)

    def is_interested_in(self, ad):
        return all(filter.allows(ad) for filter in self.filters.values())

    def subscribe(self, city):
        self.cities.add(city)
        self.add_filter(FilterCity, self.cities)

    def is_subscribed(self, city):
        return city in self.cities

    def review_ads(self, ads, city):
        if self.known_ads[city] is None:
            # special case
            # prevent notification of current ads right after subscription
            self.known_ads[city] = set(ads)
            return set()
        unknown_ads = set(filter(lambda ad: ad not in self.known_ads[city], ads))
        self.known_ads[city] = set(ads)
        return unknown_ads

    def already_had(self, ad):
        return any(ad in known_ads for known_ads in self.known_ads.values())
