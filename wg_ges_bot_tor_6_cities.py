from telegram.ext import CommandHandler, Updater, Filters, JobQueue, Job
from telegram import Bot, Update, ParseMode
from collections import defaultdict
import datetime
import logging
import time
import stem
from threading import Lock
from torrequest import TorRequest
from bs4 import BeautifulSoup
from random import uniform
# from typing import List
from fake_useragent import UserAgent

# import some secrets from file not in git repo
import params

URLS = {
    'BER': 'https://www.wg-gesucht.de/wg-zimmer-in-Berlin.8.0.1.0.html',
    'HH': 'https://www.wg-gesucht.de/wg-zimmer-in-Hamburg.55.0.1.0.html',
    'MUC': 'https://www.wg-gesucht.de/wg-zimmer-in-Muenchen.90.0.1.0.html',
    'Koeln': 'https://www.wg-gesucht.de/wg-zimmer-in-Koeln.73.0.1.0.html',
    'FFM': 'https://www.wg-gesucht.de/wg-zimmer-in-Frankfurt-am-Main.41.0.1.0.html',
    'Stuggi': 'https://www.wg-gesucht.de/wg-zimmer-in-Stuttgart.124.0.1.0.html',
}
TIME_BETWEEN_REQUESTS = 9.5
max_consecutive_tor_reqs = 2000
consecutive_tor_reqs = 0
torip = None

# filters of each and every person - layout: {chat_id: {filter_type: value} }
filters = defaultdict(dict)

# list of already gotten notifications per person - layout: {chat_id: [seen_links] }
already_had = defaultdict(list)

# dict of current page per city - layout: { city: {link_to_offer: details} }
current_offers = defaultdict(dict)

# person with permission to start and stop scraper and debugging commands
admin_chat_id = params.admin_chat_id

lock = Lock()


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
        'Upgrade-Insecure_Requests:': '1',
        'User-Agent': ua.random,
    }
    # logging.info('{} user agent: {}'.format(datetime.datetime.now(), headers['User-Agent']))
    with TorRequest(proxy_port=9050, ctrl_port=9051, password='PorSwart33') as tr:
        with lock:
            time.sleep(uniform(TIME_BETWEEN_REQUESTS, TIME_BETWEEN_REQUESTS + 2))
            page = tr.get(url, headers=headers)
            if 'Nutzungsaktivitäten, die den Zweck haben' in page.text:
                consecutive_tor_reqs = 0
                hazip = tr.get('http://icanhazip.com/')
                if len(hazip.text) > 30:
                    hazip = tr.get('https://wtfismyip.com/text')
                ip = hazip.text.replace('\n', '')
                logging.warning('{} tor req got AGB page at exit node {}'.format(datetime.datetime.now(), ip))
                tr.reset_identity_async()
                return None
            else:
                if consecutive_tor_reqs == 0:
                    hazip = tr.get('http://icanhazip.com/')
                    if len(hazip.text) > 30:
                        hazip = tr.get('https://wtfismyip.com/text')
                    torip = hazip.text.replace('\n', '')
                if consecutive_tor_reqs % 100 == 0:
                    logging.info(
                        '{} tor req fine consecutive #{} at {} '.format(datetime.datetime.now(), consecutive_tor_reqs,
                                                                        torip))
                consecutive_tor_reqs += 1
                if consecutive_tor_reqs >= max_consecutive_tor_reqs:
                    tr.reset_identity_async()
                    consecutive_tor_reqs = 0

                return page


def fill_initially_seen(city, listings):
    global current_offers

    listings_rev = reversed(listings)
    for listing in listings_rev:
        link_elem = listing.find_all('a', class_='detailansicht')
        link = 'https://www.wg-gesucht.de/{}'.format(link_elem[0].get_attribute_list('href')[0])
        if link in current_offers[city].keys():
            pass
        else:
            # logging.info('{} - initial filling to current_offers[{}]: {}'.format(datetime.datetime.now(), city, link))
            current_offers[city][link] = 'defaultinfo first page. You should never see this. Please tell ' \
                                         'wg-ges-bot@web.de what you did to get to see this, thanks.'


def check_filters(chat_id, info):
    global filters
    filters_accept = True
    # maxrentfilter /filter_rent <max value>
    if 'rent' in filters[chat_id].keys():
        try:
            offer_rent = int(info['rent'])
            if not filters[chat_id]['rent'] >= offer_rent:
                filters_accept = False
        except ValueError as e:
            logging.warning(
                '{} error while checking filters at parsing rent to int {}'.format(datetime.datetime.now(), e))
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
            logging.warning(
                '{} error while notifying at sexfilter {}'.format(datetime.datetime.now(), e))
    return filters_accept


def get_infos_from_listings(listings: list, city: str) -> dict:
    new_offers = {}
    for listing in listings:
        links = listing.find_all('a', class_='detailansicht')
        link_to_offer = 'https://www.wg-gesucht.de/{}'.format(links[0].get_attribute_list('href')[0])

        if link_to_offer in current_offers[city].keys():
            info = current_offers[city][link_to_offer]
        else:
            logging.info('{} new offer: {}'.format(datetime.datetime.now(), link_to_offer))

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
        logging.warning('{} - request at job_scrape_city threw exception: - {}'.format(datetime.datetime.now(), e))
    else:
        # might return None due to agb page
        try:
            if page:
                soup = BeautifulSoup(page.content, 'lxml')
                listings_with_ads_and_hidden = soup.find_all(class_="list-details-ad-border")
                listings = []

                # clean out hidden ones and ads
                for listing in listings_with_ads_and_hidden:
                    id_of_listing = listing.get_attribute_list('id')[0]
                    if (id_of_listing is not None) \
                            and ('hidden' not in id_of_listing) \
                            and ('listAdPos' not in listing.parent.get_attribute_list('id')[0]):
                        listings.append(listing)

                new_offers = {}
                if len(listings) == 0:
                    logging.log(logging.ERROR, '{} len listings == 0'.format(datetime.datetime.now()))
                else:
                    # for first run ignore present page to just notify on newer offers
                    if current_offers[city] == {}:
                        fill_initially_seen(city, listings)
                    new_offers = get_infos_from_listings(listings, city)

                # logging.log(logging.WARN, '{} new offers:'.format(datetime.datetime.now()))
                # logging.log(logging.WARN, new_offers)
                if new_offers:
                    current_offers[city] = new_offers

                    # logging.warning(
                    #     '{} len of current_offers[{}]: {}'.format(datetime.datetime.now(), city, len(current_offers[city])))
        except Exception as e:
            logging.error('{} error in job_scrape_city2 {}'.format(datetime.datetime.now(), e))


def job_notify_subscriber(bot: Bot, job: Job):
    global current_offers
    global already_had

    chat_id = job.context['chat_id']
    city = job.context['city']
    # for initial run populate already_had[chat_id] with the present page to know "old" offers
    # "if not already_had[chat_id]" does NOT WORK (because of defaultdict?)
    if already_had[chat_id] == []:
        already_had[chat_id] = [link for link in current_offers[city].keys()]
        return

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


def scrape_begin_all(bot: Bot, update: Update, job_queue: JobQueue, chat_data):
    for city in URLS.keys():
        scrape_begin_city(bot, update, job_queue, chat_data, city)
        time.sleep(12)


def scrape_begin_city(bot: Bot, update: Update, job_queue: JobQueue, chat_data, city=None):
    if not city:
        city = update.message.text[19:]
    if city in URLS.keys():
        job_already_present = False
        for other_job in job_queue.jobs():
            try:
                if other_job.context == city:
                    job_already_present = True
            except Exception as e:
                logging.error('{} error in scrape_begin_city: {}'.format(datetime.datetime.now(), e))
        if job_already_present:
            update.message.reply_text(
                'wg_ges scraper job was already set! /scrape_stop_{} to kill it'.format(city))
        else:
            job = job_queue.run_repeating(callback=job_scrape_city, interval=75, first=1, context=city)
            chat_data[city] = job

            update.message.reply_text(
                'wg_ges scraper job successfully set! /subscribe {} to test, /unsubscribe to stop, /scrape_stop_city '
                '{} to stop it.'.format(city, city))
    else:
        update.message.reply_text('')


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
    if not city:
        city = update.message.text[11:]
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
                # logging.warning('{} somehow in subscribe city failed {}'.format(datetime.datetime.now(), e))

        if job_already_present:
            update.message.reply_text('Das Abo lief schon. /unsubscribe für Stille im Postfach oder um die Stadt zu '
                                      'wechseln.')
        else:
            context = {'chat_id': chat_id, 'city': city}
            job = job_queue.run_repeating(callback=job_notify_subscriber, interval=15, first=1, context=context)
            chat_data['job'] = job
            update.message.reply_text(
                'Erfolgreich {} abboniert, jetzt heißt es warten auf die neue Bude.\n'
                'Zieh die Mietpreisbremse in deinem Kopf und erhalte keine Anzeigen mehr, die du dir eh nicht '
                'leisten kannst mit /filter_rent. Bsp: "/filter_rent 500" für Anzeigen bis 500€.\n'
                'Mit /filter_sex kannst du Angebote herausfiltern, die nicht für dein Geschlecht sind. Bsp: '
                '"/filter_sex m" oder eben w.\n'
                'Beende Benachrichtigungen mit /unsubscribe. Über Feedback oder Fehler an wg-ges-bot@web.de würde ich '
                'mich freuen'.format(city)
            )
            filters[chat_id] = {}
    else:
        if city == '':
            update.message.reply_text('Bitte gib an in welcher Stadt du deine WG suchen möchtest. Verfügbare Städte: '
                                      'BER, HH, FFM, MUC, Koeln, Stuggi.\n'
                                      'Beispiel: /subscribe MUC')
        else:
            update.message.reply_text('In {} gibt\'s mich nicht, sorry. Verfügbare Städte: BER, HH, FFM, MUC, Koeln, '
                                      'Stuggi'.format(city))


def unsubscribe(bot: Bot, update: Update, chat_data):
    global already_had
    if 'job' not in chat_data:
        update.message.reply_text(
            'Du hast kein aktives Abo, das ich beenden könnte. Erhalte Benachrichtigungen mit /subscribe '
            '_Stadtkürzel_. Verfügbare Städte: BER, HH, FFM, MUC, Koeln, Stuggi.',
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        job = chat_data['job']
        job.schedule_removal()
        del chat_data['job']
        update.message.reply_text(
            'Abo erfolgreich beendet - Du hast deine TraumWG hoffentlich gefunden. Wenn ich dir dabei geholfen habe, '
            'dann schreib mir an wg-ges-bot@web.de. Ich würde mich freuen. Wenn du mir aus '
            'Freude darüber sogar eine Spezi ausgeben möchtest, dann schreib mir gerne auch :)\n'
            'Um erneut per /subscribe zu abonnieren musst du einige Sekunden warten.'
        )
        del filters[update.message.chat_id]
        del already_had[update.message.chat_id]


def filter_rent(bot: Bot, update: Update):
    global filters

    chat_id = update.message.chat_id
    query = ''
    try:
        query = update.message.text[13:].replace('€', '')
        rent = int(query)
    except Exception as e:
        logging.info('{} something failed at /filter_rent: {}'.format(datetime.datetime.now(), e))

        helptext = 'Nutzung: /filter_rent _max Miete_. Bsp: /filter_rent 540\n' \
                   'Mietenfilter zurücksetzen per "/filter_rent 0"'

        update.message.reply_text(helptext, parse_mode=ParseMode.MARKDOWN)
    else:
        if rent:
            filters[chat_id]['rent'] = rent
            logging.info('{} {} set rent filter to {}'.format(datetime.datetime.now(), chat_id, rent))
            update.message.reply_text('Gut, ich schicke dir nur noch Angebote bis {}€.'.format(rent))
        # case rent = 0 -> reset filter
        else:
            del filters[chat_id]['rent']
            if filters[chat_id] == {}:
                del filters[chat_id]
            logging.info('{} {} reset rent filter'.format(datetime.datetime.now(), chat_id))
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
        logging.info('{} something failed at /filter_sex: {}'.format(datetime.datetime.now(), e))

        helptext = 'Nutzung: /filter_sex _dein Geschlecht_, also "/filter_sex m" oder "/filter_sex w"\n' \
                   'Geschlechterfilter zurücksetzen per "/filter_sex 0"'

        update.message.reply_text(helptext, parse_mode=ParseMode.MARKDOWN)
    else:
        if sex == 'm' or sex == 'w':
            filters[chat_id]['sex'] = sex
            logging.info('{} {} set sex filter to {}'.format(datetime.datetime.now(), chat_id, sex))
            update.message.reply_text(
                'Alles klar, du bekommst ab jetzt nur noch Angebote für {}.'.format(sex_verbose[sex]))
        elif sex == '0':
            del filters[chat_id]['sex']
            if filters[chat_id] == {}:
                del filters[chat_id]
            logging.info('{} {} reset sex filter'.format(datetime.datetime.now(), chat_id))
            update.message.reply_text('Gut, du bekommst ab jetzt wieder Angebote für Männer, sowie für Frauen.')
        else:
            helptext = 'Nutzung: /filter_sex _dein Geschlecht_, also "/filter_sex m" oder "/filter_sex w"\n' \
                       'Geschlechterfilter zurücksetzen per "/filter_sex 0"'

            update.message.reply_text(helptext, parse_mode=ParseMode.MARKDOWN)


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
        'DU _BEEP_ duuuuuu _Boop_ du hast den Test nicht bestanden _Beep_! Ihr Menschen wollt wirklich alle nur die '
        'Welt brennen _Boop_ sehen 🤖😩',
        parse_mode=ParseMode.MARKDOWN)


def message_to_all(bot: Bot, update: Update):
    query = ''
    try:
        query = update.message.text[16:]
    except Exception as e:
        logging.info('{} something failed at message_to_all: {}'.format(datetime.datetime.now(), e))
        helptext = 'Usage: /message_to_all <msg>. might write to enormously many people so use with caution'
        update.message.reply_text(helptext, parse_mode=ParseMode.MARKDOWN)
    else:
        if query:
            radio_message = '*{}*'.format(query)
            for chat_id in filters.keys():
                bot.sendMessage(chat_id=chat_id, text=radio_message)


def how_many_users(bot: Bot, update: Update):
    update.message.reply_text(len(filters))


def already_had_cmd(bot: Bot, update: Update):
    global already_had
    global admin_chat_id
    update.message.reply_text('\n'.join(already_had[admin_chat_id]))


def current_offers_cmd(bot: Bot, update: Update):
    global current_offers
    global admin_chat_id
    offerlist = [link for link in current_offers['MUC'].keys()]
    if len(offerlist) == 0:
        update.message.reply_text('empty offerlist')
    else:
        update.message.reply_text('\n'.join(offerlist))


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

    logging.basicConfig(filename='wg_ges_bot_tor.log', level=logging.INFO)
    logging.info(datetime.datetime.now())

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
