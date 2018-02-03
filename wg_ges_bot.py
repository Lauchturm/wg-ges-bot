import datetime

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

    def from_dict(info):
        url = info['url']
        title = info['title']
        city = info['city']
        size = info['size']
        wg_details = info['wg_details']
        availability = info['availability'].replace('Verfügbar: ', '').split(' - ')
        availability = list(map(lambda s: datetime.datetime.strptime(s, Ad.datetime_format), availability))
        availability.extend([None] * (2 - len(availability))) # pad with None
        rent = int(info['rent'])
        genders = []
        if '🚺' in info['searching_for']:
            genders.append('w')
        if '🚹' in info['searching_for']:
            genders.append('m')
        return Ad(url, title, city, size, rent, genders, availability, wg_details)

    def to_chat_message(self):
        gender_mapping = { 'w': '🚺', 'm': '🚹' }
        return '{}\n{} - {}€\n{}\n{}\n{}'.format(
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
            ) + ' gesucht'
        )

class FilterRent:
    def __init__(self, max):
        self.max = max
    def allows(self, ad):
        return ad.rent <= self.max

class FilterCity:
    def __init__(self, cities):
        self.cities = cities
    def allows(self, ad):
        return ad.city in self.cities

class FilterGender:
    def __init__(self, gender):
        self.gender = gender
    def allows(self, ad):
        return self.gender in ad.genders

class FilterAvailability:
    def __init__(self, minimal_availability):
        self.minimal_availability = minimal_availability
    def allows(self, ad):
        if not (ad.available_to()):
            return True
        else:
            duration = ad.available_to() - ad.available_from()
            return duration >= self.minimal_availability

class Subscriber:
    def __init__(self, chat_id):
        self.chat_id = int(chat_id)
        self.filters = {}
        self.known_ads = None
        self.cities = {}

    def subscribe(self, city, known_ads = []):
        self.cities[city] = known_ads

    def unsubscribe(self, city):
        self.cities.pop(city)

    def add_filter(self, filter_class, param):
        self.filters[filter_class] = filter_class(param)

    def remove_filter(self, filter_class):
        self.filters.pop(filter_class)

    def is_interested_in(self, ad):
        return all(filter.allows(ad) for filter in self.filters.values())

    def already_had(self, ad):
        return ad in self.known_ads

    def review_ads(self, ads):
        if self.known_ads is None:
            # special case
            # prevent notification of current ads right after subscription
            self.known_ads = set(ads)
            return set()
        unknown_ads = set(filter(lambda ad: ad not in self.known_ads, ads))
        self.known_ads = set(ads)
        return unknown_ads
