import os
import sqlite3
import datetime
from uuid import uuid4
import requests
import json
import threading
import re
import subprocess
import sched
import time
from dateutil import parser
from dateutil.tz import tzutc
from threading import Semaphore

webhook_url = "https://discord.com/api/webhooks/1160359055890595840/vAphnpPlgEfCtb2bg0XINqlfrnq-6D_FPSgq-lUpjks-NfFugVoTtL6_ieP2ipgS4E2J"

def getReese84Token()->tuple[str, int]:
    def readFileContentToString(filename):
        f = open(filename, 'r')
        content = f.read()
        f.close()
        return content

    # fetch the javascript that generates the reese84
    antibot_js_code_loc = os.path.join(os.path.dirname(__file__), "js/epsf.js")
    antibot_js_code_trim = readFileContentToString(antibot_js_code_loc)

    # # trim the code to the function that is only used
    # match_obj = re.search(constants.FN_MATCHING_REGEX, antibot_js_code_full)
    # if not match_obj:
    #     raise Exception('reese84 manufacture fails')
    # start, end = match_obj.span()
    # antibot_js_code_trim = antibot_js_code_full[start:end]

    # inject the code to the javascript
    injector_js_code_loc = os.path.join(
        os.path.dirname(__file__), "js/injector.js")
    injector_header_js_code_loc = os.path.join(os.path.dirname(
        __file__), "js/injector-header.js")
    injector_js_code, injector_header_js_code = readFileContentToString(
        injector_js_code_loc), readFileContentToString(injector_header_js_code_loc)
    runnable_js_code = injector_header_js_code + \
        antibot_js_code_trim + injector_js_code

    # save the runnable js code
    runnable_file_loc = os.path.join(os.path.dirname(
        __file__), "js/antibot-simulation.js")
    runnable_file = open(runnable_file_loc, "w")
    runnable_file.write(runnable_js_code)
    runnable_file.close()

    # run the js code using local node.js
    res = subprocess.run(
        ["node", runnable_file_loc], capture_output=True)
    token_str = res.stdout

    # produce the reese84 object
    token = json.loads(token_str)
    session = requests.Session()

    # invoke the get token api to get the reese84 token
    token_json_res = session.post(
        "https://epsf.ticketmaster.com/eps-d?d=www.ticketmaster.com", headers={"origin": "https://www.ticketmaster.com",
                    "referer": "https://www.ticketmaster.com/"}, json=token)
    json_obj = token_json_res.json()
    # print(json_obj['token'], json_obj['renewInSec'])
    return json_obj['token'], json_obj['renewInSec']

class Reese84TokenUpdating():
    def __init__(self):
        self.is_running = False
        self._reese84_token = ''
        self.reese84_renewInSec = 0
        self.token_access_semaphore = Semaphore(1) # one can access at a time
        self.token_semaphore = Semaphore(0)
        self.scheduler = sched.scheduler(time.time, time.sleep)

    @property
    def reese84_token(self):
        self.token_semaphore.acquire()
        self.token_access_semaphore.acquire()
        token = self._reese84_token
        self.token_semaphore.release()
        self.token_access_semaphore.release()

        return token

    def initialize_reese84_token(self):
        """
        This method should not be called directly.
        """
        self.token_access_semaphore.acquire()
        self._reese84_token, self.reese84_renewInSec = getReese84Token()
        self.token_semaphore.release() # produce a new token
        self.token_access_semaphore.release()
        # self.scheduler.enter(self.reese84_renewInSec - 3, 1, self.renew_reese84_token)

    def renew_reese84_token(self):
        """
        This method should not be called directly.
        """
        print("renewing token")
        self.token_semaphore.acquire()  # invalidate a token
        self.token_access_semaphore.acquire()
        self._reese84_token, self.reese84_renewInSec = getReese84Token()
        self.token_semaphore.release()  # produce a token
        self.token_access_semaphore.release()
        # self.scheduler.enter(self.reese84_renewInSec - 3, 1, self.renew_reese84_token)

    def start(self):
        # if the scheduler is already started - do nothing
        if self.is_running:
            return
        self.is_running = True
        self.initialize_reese84_token()
        self.scheduler.run()

def send_discord_webhook(payload):
    # Convert the payload to JSON
    json_payload = json.dumps(payload)
    # Send a POST request to the Discord webhook URL
    response = requests.post(webhook_url, data=json_payload, headers={"Content-Type": "application/json"})
    # Print the response from the server (optional)
    print(response.text)


def format_seats(data):
    # prune top-picks data structure
    pruned_picks = prune_pick_attributes(data)

    # process seats data - use piping
    res = pipe([
        append_scraping_config_ref,
        map_prices_to_seats,
        remove_embedded_field
    ], pruned_picks)

    return res

def pipe(fns: list, *args):
    out = args
    for fn in fns:
        if type(out) is tuple:
            out = fn(*out)
        else:
            out = fn(out)
    return out

def get_value_from_map(map: dict, *args, **kwargs):
    # input validation
    if type(map) is not dict:
        return kwargs.get('default', None)
    res = kwargs.get('default', None)
    for attr in args:
        res = map.get(attr)
        if res is not None:
            break
    return res

def get_value_from_nested_map(map: dict, *args, **kwargs):
    # input validation
    if type(map) is not dict:
        return kwargs.get('default', None)
    res = None
    m = map
    count = 0
    for attr in args:
        res = m.get(attr)
        count += 1
        if res is None:
            break
        elif type(res) is dict:
            m = res
        else:
            break
    return res if res is not None and count == len(args) else kwargs.get('default', None)

def get_fn_return(fn, *args, **kwargs):
    res = kwargs.get('default', None)
    try:
        res = fn(*args)
    except:
        pass
    finally:
        return res

def prune_pick_attributes(data):
    def prune_pick_offer_attributes(pick: dict):
        return {
            'type': get_value_from_map(pick, 'type'),
            'selection': get_value_from_map(pick, 'selection'),
            'quality': get_value_from_map(pick, 'quality'),
            'section': get_value_from_map(pick, 'section'),
            'row': get_value_from_map(pick, 'row'),
            'offerGroups': get_value_from_map(pick, 'offerGroups', 'offers'),
            'area': get_value_from_map(pick, 'area'),
            'maxQuantity': get_value_from_map(pick, 'maxQuantity'),
        }

    def prune_pick_embedded_attributes(embedded: dict):
        def prune_pick_embedded_offer_attributes(item):
            return {
                'expired_date': get_value_from_nested_map(item, 'meta', 'expires'),
                'offerId': get_value_from_map(item, 'offerId'),
                'rank': get_value_from_map(item, 'rank'),
                'online': get_value_from_map(item, 'online'),
                'protected': get_value_from_map(item, 'protected'),
                'rollup': get_value_from_map(item, 'rollup'),
                'inventoryType': get_value_from_map(item, 'inventoryType'),
                'offerType': get_value_from_map(item, 'offerType'),
                'currency': get_value_from_map(item, 'currency'),
                'listPrice': get_value_from_map(item, 'listPrice'),
                'faceValue': get_value_from_map(item, 'faceValue'),
                'totalPrice': get_value_from_map(item, 'totalPrice'),
                'noChargesPrice': get_value_from_map(item, 'noChargesPrice'),
               #  'listingId': get_value_from_map(item, 'listingId'),
               #  'listingVersionId': get_value_from_map(item, 'listingVersionId'),
               #  'charges': get_value_from_map(item, 'charges'),
               #  'sellableQuantities': get_value_from_map(item, 'sellableQuantities'),
               #  'section': get_value_from_map(item, 'section'),
               #  'row': get_value_from_map(item, 'row'),
               #  'seatFrom': get_value_from_map(item, 'seatFrom'),
               #  'seatTo': get_value_from_map(item, 'seatTo'),
               #  'ticketTypeId': get_value_from_map(item, 'ticketTypeId')
            }
        return {
            'offer': list(map(prune_pick_embedded_offer_attributes, get_value_from_map(embedded, 'offer', default=dict())))
        }
    return {
        'expired_date': get_value_from_nested_map(data, 'meta', 'expires'),
        'eventId': get_value_from_map(data, 'eventId'),
        'offset': get_value_from_map(data, 'offset'),
        'total': get_value_from_map(data, 'total'),
        'picks': list(map(prune_pick_offer_attributes, get_value_from_map(data, 'picks', default=dict()))),
        '_embedded': prune_pick_embedded_attributes(get_value_from_map(data, '_embedded', default=dict()))
    }


def append_scraping_config_ref(data):
    return data


def map_prices_to_seats(data):
    def map_prices_to_seat_helper(offer_table: dict):
        def __map_prices_to_seat_helper(pick):
            offerGroups = pick['offerGroups']
            if offerGroups is None or len(offerGroups) == 0:
                return {'offer_available': False}
            offerGroup = offerGroups[0]
            offerIds = get_value_from_map(offerGroup, 'offers', default=[offerGroup])
            offerSeatCols = get_value_from_map(offerGroup, 'seats')
            if len(offerIds) == 0:
                return {'offer_available': False}
            offerId = offerIds[0]
            offerObj = offer_table.get(offerId)
            res = {**pick, 'offer': offerObj, 'seat_columns': offerSeatCols}
            del res['offerGroups']
            return res
        return __map_prices_to_seat_helper

    offer_dict = {offer['offerId']: offer for offer in data['_embedded']['offer']}
    picks_list = list(
        map(map_prices_to_seat_helper(offer_dict), data['picks']))
    data['picks'] = picks_list
    return data

def remove_embedded_field(data):
    del data['_embedded']
    return data

if __name__ == '__main__':
    eventTitle = "Travis Scott Utopia Tour Presents Circus Maximus"
    eventId = "2D005F05828C17F1"

    # reese84 token renewing thread
    reese_token_gen = Reese84TokenUpdating()
    serverThread_reese = threading.Thread(target=reese_token_gen.start)
    serverThread_reese.start()

    while True:
        try:
            top_picks_url = f"https://offeradapter.ticketmaster.com/api/ismds/event/{eventId}/quickpicks"
            top_picks_q_params = {
                'show': 'places maxQuantity sections',
                'mode': 'primary:ppsectionrow+resale:ga_areas+platinum:all',
                'qty': "1",
                'q': "not('accessible')",
                'includeStandard': 'False',
                'includeResale': 'True',
                'includePlatinumInventoryType': 'False',
                'embed': ['area', 'offer', 'description'],
                'apikey': 'b462oi7fic6pehcdkzony5bxhe',
                'apisecret': 'pquzpfrfz7zd2ylvtz3w5dtyse',
                'limit': 100,
                'offset': 0,
                'sort': '-listprice',
            }
            
            session = requests.Session()

            # Set cookie
            session.cookies.set("reese84", reese_token_gen._reese84_token)

            top_picks_header = {
                'authority': 'offeradapter.ticketmaster.com',
                'accept': '*/*',
                'accept-language': 'en-GB,en-US;q=0.9,en;q=0.8,sw;q=0.7',
                'cache-control': 'no-cache',
                'dnt': '1',
                'origin': 'https://www.ticketmaster.com',
                'pragma': 'no-cache',
                'referer': 'https://www.ticketmaster.com/',
                'sec-ch-ua': '"Google Chrome";v="117", "Not;A=Brand";v="8", "Chromium";v="117"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"macOS"',
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-site',
                'tmps-correlation-id': str(uuid4()),
                'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36',
            }

            # # Sending request to protected url 
            response = session.get(top_picks_url, headers=top_picks_header, params=top_picks_q_params)

            # Print response details
            # print(f"Response URL: {response.url}")
            print(f"Status Code: {response.status_code}")
            # print(f"Content: {response.text}")
            if response.status_code != 200:
                reese_token_gen.renew_reese84_token()

            # prune and format the received picks
            # data = format_seats(data)

            data = format_seats(json.loads(response.text))

            # Connect to SQLite database (creates a new one if not exists)
            conn = sqlite3.connect('db.sqlite')
            cursor = conn.cursor()

            # Create a table to store the data
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS events (
                    expired_date TEXT,
                    eventId TEXT PRIMARY KEY,
                    offset INTEGER,
                    total INTEGER
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS picks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    offerId TEXT,
                    event_id INTEGER,
                    type TEXT,
                    selection TEXT,
                    quality REAL,
                    section TEXT,
                    row TEXT,
                    area TEXT,
                    maxQuantity INTEGER,
                    seat_columns TEXT,
                    offer_expired_date TEXT,
                    rank INTEGER,
                    online INTEGER,
                    protected INTEGER,
                    rollup INTEGER,
                    inventoryType TEXT,
                    offerType TEXT,
                    currency TEXT,
                    listPrice REAL,
                    faceValue REAL,
                    totalPrice REAL,
                    noChargesPrice REAL,
                    FOREIGN KEY (event_id) REFERENCES events (event_id),
                    UNIQUE (section, area, row)
                )
            ''')

            # Insert event data
            event_data = (str(data['expired_date']), data['eventId'], data['offset'], data['total'])
            cursor.execute('INSERT INTO events (expired_date, eventId, offset, total) VALUES (?, ?, ?, ?)', event_data)
            event_id = cursor.lastrowid

            messages = []
            # Insert picks data
            for pick in data['picks']:
                pick_data = (
                    event_id,
                    pick['type'], pick['selection'], pick['quality'], pick['section'], pick['row'], pick['area'],
                    pick['maxQuantity'], json.dumps(pick['seat_columns']),
                    str(pick['offer']['expired_date']), pick['offer']['offerId'], pick['offer']['rank'], pick['offer']['online'],
                    pick['offer']['protected'], pick['offer']['rollup'], pick['offer']['inventoryType'], pick['offer']['offerType'],
                    pick['offer']['currency'], pick['offer']['listPrice'], pick['offer']['faceValue'], pick['offer']['totalPrice'],
                    pick['offer']['noChargesPrice']
                )
                cursor.execute('''
                    INSERT OR REPLACE INTO picks (
                        event_id, type, selection, quality, section, row, area, maxQuantity, seat_columns,
                        offer_expired_date, offerId, rank, online, protected, rollup, inventoryType, offerType,
                        currency, listPrice, faceValue, totalPrice, noChargesPrice
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', pick_data)

                # Check if the record is new
                if True or cursor.rowcount > 0:
                    messages.append({
                        "content": f"New Seat Avialable: {eventTitle}",
                        "embeds": [
                            {
                                "title": f"Sec {pick['section']} Row{pick['row']} Area {pick['area']}",
                                "description": f"""
                                                Type: {pick['type']}
                                                Selection: {pick['selection']}
                                                Section:{pick['section']} 
                                                Row:{pick['row']} 
                                                Area: {pick['area']} 
                                                Offer Type: {pick['offer']['offerType']} \n
                                                Currency: {pick['offer']['currency']} 
                                                List Price: {pick['offer']['listPrice']}
                                                """,
                            }
                        ]
                    })

            if len(messages) > 0:
                send_discord_webhook({"messages": messages})
                print("Sent Update Successfully")
                
            print("Checking will resume after 30 seconds...")
            # Commit the changes and close the connection
            conn.commit()
            conn.close()    
            time.sleep(30)
        except Exception:
            time.sleep(10)



# Face Value: {pick['offer']['faceValue']} \n
# Total Price: {pick['offer']['totalPrice']} \n
# No Charges Price: {pick['offer']['noChargesPrice']} \n
