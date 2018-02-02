from telegram.ext import CommandHandler, Updater, Filters, JobQueue, Job
from telegram import Bot, Update, ParseMode
from telegram.error import Unauthorized
from collections import defaultdict
import datetime
import logging
import time
import stem
from threading import Lock
from torrequest import TorRequest
from bs4 import BeautifulSoup
from random import uniform
from fake_useragent import UserAgent
import json

# import some secret params from other file
import params

URLS = {
    'ber': 'https://www.wg-gesucht.de/wg-zimmer-in-Berlin.8.0.1.0.html',
    'hh': 'https://www.wg-gesucht.de/wg-zimmer-in-Hamburg.55.0.1.0.html',
    'muc': 'https://www.wg-gesucht.de/wg-zimmer-in-Muenchen.90.0.1.0.html',
    'koeln': 'https://www.wg-gesucht.de/wg-zimmer-in-Koeln.73.0.1.0.html',
    'ffm': 'https://www.wg-gesucht.de/wg-zimmer-in-Frankfurt-am-Main.41.0.1.0.html',
    'stuggi': 'https://www.wg-gesucht.de/wg-zimmer-in-Stuttgart.124.0.1.0.html',
}
TIME_BETWEEN_REQUESTS = 9.5
max_consecutive_tor_reqs = 2000
consecutive_tor_reqs = 0
torip = None

# active subscribers' IDs in case the bot needs to message them
active_subs = []

# filters of each and every person - layout: {chat_id: {filter_type: value} }
filters = defaultdict(dict)

# list of already gotten notifications per person - layout: {chat_id: [seen_links] }
already_had = defaultdict(list)

# dict of current page per city - layout: { city: {link_to_offer: details} }
current_offers = defaultdict(dict)

# person with permission to start and stop scraper and debugging commands
admin_chat_id = params.admin_chat_id

lock = Lock()


class Offer:
    def __init__(self, rent):
        self.rent = int(rent)
    def from_dict(adict):
        return Offer(adict['rent'])

class FilterRent:
    def __init__(self, max):
        self.max = max
    def allows(self, offer):
        return offer.rent <= self.max

class Subscriber:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.filters = {}

    def add_filter(self, filter_class, params):
        self.filters[filter_class] = filter_class(params)

    def remove_filter(filter_class):
        pass

    def is_interested_in(self, offer):
        return all(filter.allows(offer) for filter in self.filters.values())


def get_current_ip(tr):
    hazip = tr.get('http://icanhazip.com/')
    if len(hazip.text) > 30:
        hazip = tr.get('https://wtfismyip.com/text')
    return hazip.text.replace('\n', '')


def tor_request(url: str):
    global consecutive_tor_reqs
    global torip
    ua = UserAgent()

    headers = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept-Language': 'en,en-US;q=0.7,de;q=0.3',
        'Cache-Control': 'max-age=0',
        'Connection': 'keep-alive',
        'DNT': '1',
        'Host': 'www.wg-gesucht.de',
        'Referrer': 'https://www.wg-gesucht.de/',
        'User-Agent': ua.random,
    }
    with TorRequest(proxy_port=9050, ctrl_port=9051, password=params.tor_pwd) as tr:
        with lock:
            time.sleep(uniform(TIME_BETWEEN_REQUESTS, TIME_BETWEEN_REQUESTS + 2))
            page = tr.get(url, headers=headers)
            if 'Nutzungsaktivitäten, die den Zweck haben' in page.text:
                consecutive_tor_reqs = 0
                ip = get_current_ip(tr)
                logging.warning('tor req got AGB page at exit node {}'.format(ip))
                tr.reset_identity_async()
                return None
            else:
                if consecutive_tor_reqs == 0:
                    torip = get_current_ip(tr)
                if consecutive_tor_reqs % 100 == 0:
                    logging.info('tor req fine consecutive #{} at {} '.format(consecutive_tor_reqs, torip))
                consecutive_tor_reqs += 1
                if consecutive_tor_reqs >= max_consecutive_tor_reqs:
                    tr.reset_identity_async()
                    consecutive_tor_reqs = 0

                return page


def fill_initially_seen(city: str, listings):
    global current_offers

    listings_rev = reversed(listings)
    for listing in listings_rev:
        link_elem = listing.find_all('a', class_='detailansicht')
        link = 'https://www.wg-gesucht.de/{}'.format(link_elem[0].get_attribute_list('href')[0])
        if link not in current_offers[city].keys():
            current_offers[city][link] = 'defaultinfo first page. You should never see this. Please tell ' \
                                         'wg-ges-bot@web.de what you did to get to see this, thanks.'


def check_filters(chat_id, info) -> bool:
    filters_accept = True
    # maxrentfilter /filter_rent <max value>
    if 'rent' in filters[chat_id].keys():
        try:
            offer_rent = int(info['rent'])
            if not filters[chat_id]['rent'] >= offer_rent:
                filters_accept = False
        except ValueError as e:
            logging.warning('error while checking filters at parsing rent to int {}'.format(e))
    # sex filter /filter_sex <sex> (m/w)
    if 'sex' in filters[chat_id].keys():
        try:
            offer_sex = info['searching_for']
            offer_sex_dict = {
                'w': '🚺' in offer_sex,
                'm': '🚹' in offer_sex,
            }
            if not offer_sex_dict[filters[chat_id]['sex']]:
                filters_accept = False
        except ValueError as e:
            logging.warning('error while notifying at sexfilter {}'.format(e))
    return filters_accept


def get_infos_from_listings(listings: list, city: str) -> dict:
    new_offers = {}
    for listing in listings:
        links = listing.find_all('a', class_='detailansicht')
        link_to_offer = 'https://www.wg-gesucht.de/{}'.format(links[0].get_attribute_list('href')[0])

        if link_to_offer in current_offers[city].keys():
            info = current_offers[city][link_to_offer]
        else:
            logging.info('new offer: {}'.format(link_to_offer))

            price_wrapper = listing.find(class_="detail-size-price-wrapper")
            link_named_price = price_wrapper.find(class_="detailansicht")
            size, rent = link_named_price.text.replace(' ', '').replace('\n', '').replace('€', '').split('-')

            headline = listing.find(class_='headline-list-view')
            mates = headline.find('span').get_attribute_list('title')[0]
            # emojis read faster -- also note the typo from the page missing the first e in mitbewohner
            searching_for = headline.find_all('img')[-1].get_attribute_list('alt')[0].replace('Mitbewohnerin', '🚺')
            searching_for = searching_for.replace('Mitbwohner', '🚹').replace('Mitbewohner', '🚹')
            title = headline.find('a').text.replace('\n', '').strip()

            location_and_availability = listing.find('p')
            location_and_availability_split = location_and_availability.text[
                                              location_and_availability.text.index('in'):].replace('\n', '').split()
            index_avail = location_and_availability_split.index('Verfügbar:')
            location = ' '.join(location_and_availability_split[:index_avail])
            availability = ' '.join(location_and_availability_split[index_avail:])
            wg_details = '{} {}'.format(mates, location)

            info = {
                'title': title,
                'size': size,
                'rent': rent,
                'availability': availability,
                'wg_details': wg_details,
                'searching_for': searching_for,
            }
        new_offers[link_to_offer] = info
    return new_offers


def job_scrape_city(bot: Bot, job: Job):
    global current_offers
    city = job.context
    url = URLS[city]

    try:
        page = tor_request(url)
    except Exception as e:
        logging.warning('request at job_scrape_city threw exception: - {}'.format(e))
    else:
        # might return None due to agb page
        try:
            if page:
                # no dependencies, so use that one if it works
                soup = BeautifulSoup(page.content, 'html.parser')
                # soup = BeautifulSoup(page.content, 'lxml')
                listings_with_ads_and_hidden = soup.find_all(class_="list-details-ad-border")
                listings = []

                # clean out hidden ones and ads
                for listing in listings_with_ads_and_hidden:
                    id_of_listing = listing.get_attribute_list('id')[0]
                    if (id_of_listing is not None) \
                            and ('hidden' not in id_of_listing) \
                            and ('listAdPos' not in listing.parent.get_attribute_list('id')[0]):
                        listings.append(listing)

                if len(listings) == 0:
                    logging.warning('len listings == 0')
                else:
                    # for first run ignore present page to just notify on newer offers
                    if len(current_offers[city]) == 0:
                        fill_initially_seen(city, listings)
                    else:
                        new_offers = get_infos_from_listings(listings, city)
                        current_offers[city] = new_offers
        except Exception as e:
            logging.warning('error in job_scrape_city2 {}'.format(e))


def job_notify_subscriber(bot: Bot, job: Job):
    global active_subs
    global already_had
    chat_id = job.context['chat_id']
    try:
        city = job.context['city']
        # for initial run populate already_had[chat_id] with the present page to know "old" offers
        if len(already_had[chat_id]) == 0:
            if len(current_offers[city]) > 0:
                already_had[chat_id] = [link for link in current_offers[city].keys()]
            else:
                logging.warning('{} tried to initially fill already_had for {} but current_offers were empty'.format(chat_id, city))
        else:
            new_already_had = []
            for link_to_offer, info in current_offers[city].items():
                if link_to_offer not in already_had[chat_id]:
                    filters_accept = check_filters(chat_id, info)
                    if filters_accept:
                        # offer_id = link_to_offer.split('.')[-2]
                        # message_to_link = 'https://www.wg-gesucht.de/nachricht-senden.html?id={}'.format(offer_id)
                        info_string = '{}\n{} - {}€\n{}\n{}\n{}'.format(
                            info['title'],
                            info['size'],
                            info['rent'],
                            info['wg_details'],
                            info['availability'],
                            info['searching_for'],
                        )
                        bot.sendMessage(chat_id=chat_id, text='\n'.join((info_string, link_to_offer)))
                new_already_had.append(link_to_offer)
            already_had[chat_id] = new_already_had

    except Unauthorized:
        logging.warning('unauthorized in job notify. removing job')
        active_subs.remove(chat_id)
        job.schedule_removal()


def scrape_begin_all(bot: Bot, update: Update, job_queue: JobQueue, chat_data):
    logging.info('start scraping all')
    for city in URLS.keys():
        scrape_begin_city(bot, update, job_queue, chat_data, city)
        time.sleep(12)


def scrape_begin_city(bot: Bot, update: Update, job_queue: JobQueue, chat_data, city=None):
    if not city:
        city = update.message.text[19:].lower() # 19 characters is len('/scrape_begin_city ')
    if city in URLS.keys():
        jobs_for_same_city = [job for job in job_queue.jobs() if job.context == city]
        if jobs_for_same_city:
            update.message.reply_text(
                'wg_ges scraper job was already set! /scrape_stop_city {} to kill it'.format(city))
        else:
            job = job_queue.run_repeating(callback=job_scrape_city, interval=75, first=10, context=city)
            chat_data[city] = job
            logging.info('start scraping {}'.format(city))
            update.message.reply_text(
                'wg_ges scraper job successfully set! /subscribe {} to test, /unsubscribe to stop, /scrape_stop_city '
                '{} to stop it.'.format(city, city))
    else:
        update.message.reply_text('valid cities: {}'.format(', '.join(URLS.keys())))


def scrape_stop_all(bot: Bot, update: Update, chat_data):
    for city in URLS.keys():
        scrape_stop_city(bot, update, chat_data, city)


def scrape_stop_city(bot: Bot, update: Update, chat_data, city=None):
    if not city:
        city = update.message.text[18:]
    if city in URLS.keys():
        # if update.message.chat_id == admin_chat_id:
        if city not in chat_data:
            update.message.reply_text('scraper job wasn\'t  set! /scrape_begin_{} to start it'.format(city))
        else:
            job = chat_data[city]
            job.schedule_removal()
            del chat_data[city]

            update.message.reply_text(
                '{} scraper job successfully scheduled to unset! Might take some seconds.'.format(city))
    else:
        update.message.reply_text('{} is not a supported city.'.format(city))


def subscribe_city(bot: Bot, update: Update, job_queue: JobQueue, chat_data, city=None):
    global active_subs

    if not city:
        city = update.message.text[11:].lower()
    if city in URLS.keys():
        chat_id = update.message.chat_id
        job_already_present = False
        for other_job in job_queue.jobs():
            try:
                if other_job.context['chat_id'] == chat_id:
                    job_already_present = True
            except Exception as e:
                # most probably ran into "string indices must be integers" here due to the 2 formats of job.context
                # TODO think of a better job.context format
                pass

        if job_already_present:
            update.message.reply_text('Das Abo lief schon. /unsubscribe für Stille im Postfach oder um die Stadt zu '
                                      'wechseln.')
        else:
            context = {'chat_id': chat_id, 'city': city}
            job = job_queue.run_repeating(callback=job_notify_subscriber, interval=15, first=1, context=context)
            try:
                chat_data['job'] = job
            except Unauthorized:
                logging.warning('unauthorized in job notify. removing job')
                job.schedule_removal()
                return

            active_subs.append(chat_id)
            logging.info('{} subbed {}'.format(chat_id, city))
            update.message.reply_text(
                'Erfolgreich {} abboniert, jetzt heißt es warten auf die neue Bude.\n'
                'Zieh die Mietpreisbremse in deinem Kopf und erhalte keine Anzeigen mehr, die du dir eh nicht '
                'leisten kannst mit /filter_rent. Bsp: "/filter_rent 500" für Anzeigen bis 500€.\n'
                'Mit /filter_sex kannst du Angebote herausfiltern, die nicht für dein Geschlecht sind. Bsp: '
                '"/filter_sex m" oder eben w.\n'
                'Beende Benachrichtigungen mit /unsubscribe. Über Feedback oder Fehler an wg-ges-bot@web.de würde ich '
                'mich freuen'.format(city)
            )
    else:
        if city == '':
            update.message.reply_text('Bitte gib an in welcher Stadt du deine WG suchen möchtest. Verfügbare Städte: '
                                      'BER, HH, FFM, MUC, Koeln, Stuggi.\n'
                                      'Beispiel: /subscribe MUC')
        else:
            update.message.reply_text('In {} gibt\'s mich nicht, sorry. Verfügbare Städte: BER, HH, FFM, MUC, Koeln, '
                                      'Stuggi'.format(city))


def unsubscribe(bot: Bot, update: Update, chat_data):
    global active_subs
    chat_id = update.message.chat_id
    try:
        if 'job' not in chat_data:
            update.message.reply_text(
                'Du hast kein aktives Abo, das ich beenden könnte. Erhalte Benachrichtigungen mit /subscribe '
                '_Stadtkürzel_. Verfügbare Städte: BER, HH, FFM, MUC, Koeln, Stuggi.',
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            logging.info('{} unsubbed'.format(chat_id))
            active_subs.remove(chat_id)
            job = chat_data['job']
            job.schedule_removal()
            del chat_data['job']

            update.message.reply_text(
                'Abo erfolgreich beendet - Du hast deine TraumWG hoffentlich gefunden. Wenn ich dir dabei geholfen habe'
                ', dann schreib mir an wg-ges-bot@web.de. Ich würde mich freuen. Wenn du mir aus '
                'Freude darüber sogar eine Spezi (nur Paulaner!) ausgeben möchtest, dann schreib mir gerne auch :)\n'
                'Um erneut per /subscribe zu abonnieren musst du einige Sekunden warten.'
            )
    except Unauthorized:
        logging.warning('{} unauthorized in unsubscribe'.format(chat_id))


def filter_rent(bot: Bot, update: Update):
    global filters

    chat_id = update.message.chat_id
    query = ''
    try:
        query = update.message.text[13:].replace('€', '')
        rent = int(query)
    except Exception as e:
        logging.info('something failed at /filter_rent: {}'.format(e))

        update.message.reply_text(
            'Nutzung: /filter_rent <max Miete>. Bsp: /filter_rent 540\n'
            'Mietenfilter zurücksetzen per "/filter_rent 0"'
        )
    else:
        if rent:
            filters[chat_id]['rent'] = rent
            logging.info('{} set rent filter to {}'.format(chat_id, rent))
            update.message.reply_text(
                'Gut, ich schicke dir nur noch Angebote bis {}€.\n'
                'Zum zurücksetzen des Filters "/filter_rent 0" schreiben.'.format(rent)
            )
        # case rent = 0 -> reset filter
        else:
            del filters[chat_id]['rent']
            logging.info('{} reset rent filter'.format(chat_id))
            update.message.reply_text('Max Miete Filter erfolgreich zurückgesetzt.')


def filter_sex(bot: Bot, update: Update):
    global filters

    chat_id = update.message.chat_id
    sex_verbose = {
        'm': 'Männer',
        'w': 'Frauen',
    }
    sex = ''
    try:
        sex = update.message.text[12:].lower()
    except Exception as e:
        logging.info('something failed at /filter_sex: {}'.format(e))

        helptext = 'Nutzung: /filter_sex <dein Geschlecht>, also "/filter_sex m" oder "/filter_sex w"\n' \
                   'Geschlechterfilter zurücksetzen per "/filter_sex 0"'

        update.message.reply_text(helptext)
    else:
        if sex == 'm' or sex == 'w':
            filters[chat_id]['sex'] = sex
            logging.info('{} set sex filter to {}'.format(chat_id, sex))
            update.message.reply_text(
                'Alles klar, du bekommst ab jetzt nur noch Angebote für {}.\n'
                'Zum zurücksetzen des Filters "/filter_sex 0" schreiben.'.format(sex_verbose[sex])
            )
        elif sex == '0':
            del filters[chat_id]['sex']
            logging.info('{} reset sex filter'.format(chat_id))
            update.message.reply_text('Gut, du bekommst ab jetzt wieder Angebote für Männer, sowie für Frauen.')
        else:
            helptext = 'Nutzung: /filter_sex <dein Geschlecht>, also "/filter_sex m" oder "/filter_sex w"\n' \
                       'Geschlechterfilter zurücksetzen per "/filter_sex 0"'

            update.message.reply_text(helptext)


def start(bot: Bot, update: Update):
    update.message.reply_text(
        'Sei gegrüßt, _Mensch_\n'
        'ich bin dein Telegram Helferchen Bot für wg-gesucht.de.\n'
        'Die Benutzung ist kinderleicht: /subscribe <Stadtkürzel> um Nachrichten zu neuen Anzeigen zu erhalten und '
        '/unsubscribe, sobald du diese nicht mehr benötigst. Städte sind: BER, HH, FFM, MUC, Koeln, Stuggi.\n'
        'Ich wünsche viel Erfolg für die Wohnungssuche und hoffe, ich kann dir dabei eine Hilfe sein.\n'
        '_Beep Boop_\n\n'
        'Ich bin *NICHT* von wg-gesucht, sondern ein privates Projekt, um Wohnungssuchenden zu helfen. Mit mir werden '
        'weder finanzielle Ziele verfolgt, noch will man mit mir der Seite oder Anderen Schaden zufügen. Die Anzeigen '
        'und jeglicher Inhalt befinden sich weiterhin auf wg-gesucht.de und der Kontakt zu den Inserenten findet auch '
        'dort statt.',
        parse_mode=ParseMode.MARKDOWN,
    )


def kill_humans(bot: Bot, update: Update):
    update.message.reply_text(
        'DU _BEEP_  duuuuuu _Boop_ du hast den Test nicht bestanden _Beep_ ! Ihr Menschen wollt wirklich alle nur die '
        'Welt brennen _Boop_ sehen 🤖😩',
        parse_mode=ParseMode.MARKDOWN)


def message_to_all(bot: Bot, update: Update):
    query = ''
    try:
        query = update.message.text[16:]
    except Exception as e:
        logging.info('something failed at message_to_all: {}'.format(e))
        helptext = 'Usage: /message_to_all <msg>. might write to many people so use with caution'
        update.message.reply_text(helptext)
    else:
        if query:
            radio_message = query
            for chat_id in active_subs:
                bot.sendMessage(chat_id=chat_id, text=radio_message)


def how_many_users(bot: Bot, update: Update):
    update.message.reply_text(len(active_subs))


def already_had_cmd(bot: Bot, update: Update):
    offerlist = [link for link in already_had[admin_chat_id]]
    if len(offerlist) == 0:
        update.message.reply_text('empty alreadyhadlist')
    else:
        offers = '\n'.join(offerlist)
        # telegram restricts messages to 4k utf8 symbols
        if len(offers) > 4000:
            update.message.reply_text(offers[:4000])
            update.message.reply_text(offers[4000:])
        else:
            update.message.reply_text(offers)


def admin_filters_cmd(bot: Bot, update: Update):
    update.message.reply_text(json.dumps(filters[admin_chat_id], indent=4))


def current_offers_cmd(bot: Bot, update: Update):
    if not current_offers:
        update.message.reply_text('No offers for any city')
    for city, offers in current_offers.items():
        update.message.reply_text('Offers for city \'{}\':'.format(city))
        offerlist = [link for link in offers.keys()]
        if len(offerlist) == 0:
            update.message.reply_text('Empty offerlist')
        else:
            offers = '\n'.join(offerlist)
            # telegram restricts messages to 4k utf8 symbols
            if len(offers) > 4000:
                update.message.reply_text(offers[:4000])
                update.message.reply_text(offers[4000:])
            else:
                update.message.reply_text(offers)


if __name__ == '__main__':
    # stemlogger spammed a lot and i failed setting it to only warnings
    stemlogger = stem.util.log.get_logger()
    stemlogger.disabled = True
    # maybe this does it
    stemlogger.isEnabledFor(logging.WARN)
    stemlogger.isEnabledFor(logging.WARNING)
    stemlogger.isEnabledFor(logging.CRITICAL)
    stemlogger.isEnabledFor(logging.FATAL)
    stemlogger.isEnabledFor(logging.ERROR)

    logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s', filename='wg_ges_bot_tor.log', level=logging.INFO)
    logging.info('starting bot')

    updater = Updater(token=params.token)

    # all handlers need to be added to dispatcher, order matters
    dispatcher = updater.dispatcher

    handlers = [
        # handling commands
        # first string is cmd in chat e.g. 'start' --> called by /start in chat -- 2nd arg is callback
        # user queries
        CommandHandler(command='start', callback=start),
        # CommandHandler('help', help_reply),
        CommandHandler('subscribe', subscribe_city, pass_job_queue=True, pass_chat_data=True),
        CommandHandler('unsubscribe', unsubscribe, pass_chat_data=True),

        # more filters for the users?
        CommandHandler('filter_rent', filter_rent),
        CommandHandler('filter_sex', filter_sex),

        # admin queries
        CommandHandler('scrape_begin', scrape_begin_all, pass_job_queue=True, pass_chat_data=True,
                       filters=Filters.user(admin_chat_id)),
        CommandHandler('scrape_begin_city', scrape_begin_city, pass_job_queue=True, pass_chat_data=True,
                       filters=Filters.user(admin_chat_id)),
        CommandHandler('scrape_stop', scrape_stop_all, pass_chat_data=True, filters=Filters.user(admin_chat_id)),
        CommandHandler('scrape_stop_city', scrape_stop_city, pass_chat_data=True, filters=Filters.user(admin_chat_id)),

        # debugging queries
        CommandHandler('message_to_all', message_to_all, filters=Filters.user(admin_chat_id)),
        CommandHandler('how_many', how_many_users, filters=Filters.user(admin_chat_id)),
        CommandHandler('already_had', already_had_cmd, filters=Filters.user(admin_chat_id)),
        CommandHandler('current_offers', current_offers_cmd, filters=Filters.user(admin_chat_id)),
        CommandHandler('admin_filters', admin_filters_cmd, filters=Filters.user(admin_chat_id)),
        CommandHandler('kill_humans', kill_humans)
    ]

    # handlers need to be added to the dispatcher in order to work
    for handler in handlers:
        dispatcher.add_handler(handler)

    # starts bot
    # fetches these https://api.telegram.org/bot<TOKEN>/getUpdates and feeds them to the handlers
    updater.start_polling()

    # to make killing per ctrl+c possible
    updater.idle()


