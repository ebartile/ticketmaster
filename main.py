import sqlite3
import requests
import time
from bs4 import BeautifulSoup
import json

def update_database(json_data):

    # Connect to SQLite database (creates a new one if not exists)
    conn = sqlite3.connect('db.sqlite')
    cursor = conn.cursor()

    # Insert data into tables
    cursor.execute('''
        INSERT OR REPLACE INTO events (eventId, description, modified, expires)
        VALUES (?, ?, ?, ?)
    ''', (json_data['eventId'], json_data['facets'][0]['description'], json_data['meta']['modified'], json_data['meta']['expires']))

    for offer in json_data['_embedded']['offer']:
        # Insert offer data into the offers table
        cursor.execute('''
            INSERT OR REPLACE INTO offers (
                offerId, name, rank, online, protected, rollup, inventoryType, offerType,
                ticketTypeId, auditPriceLevel, priceLevelId, priceLevelSecname, description,
                currency, listPrice, faceValue, totalPrice, noChargesPrice, section, row,
                seatFrom, seatTo, sellerNotes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            offer["offerId"], offer.get("name", ""), offer["rank"],
            offer["online"], offer["protected"], offer["rollup"],
            offer["inventoryType"], offer["offerType"], offer["ticketTypeId"],
            offer.get("auditPriceLevel", ""), offer.get("priceLevelId", ""),
            offer.get("priceLevelSecname", ""), offer.get("description", ""),
            offer["currency"], offer["listPrice"], offer["faceValue"],
            offer["totalPrice"], offer["noChargesPrice"], offer.get("section", ""),
            offer.get("row", ""), offer.get("seatFrom", ""), offer.get("seatTo", ""),
            offer.get("sellerNotes", "")
        ))    
    
    for facet in json_data['facets']:
        cursor.execute('''
                INSERT OR REPLACE INTO facets (eventId, description, available, count, inventoryTypes, offerTypes, offers, shapes, placeGroups)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                json_data['eventId'],
                facet['description'],
                facet['available'],
                facet['count'],
                ','.join(facet['inventoryTypes']),
                ','.join(facet['offerTypes']),
                ','.join(facet['offers']),
                ','.join(facet['shapes']),
                ','.join(facet['placeGroups'])
            ))

    conn.commit()
    conn.close()    

def create_database():
    # Connect to SQLite database (creates a new one if not exists)
    conn = sqlite3.connect('db.sqlite')
    cursor = conn.cursor()

    # Create tables
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS events (
            eventId TEXT PRIMARY KEY,
            description TEXT,
            modified TEXT,
            expires TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS facets (
            id INTEGER PRIMARY KEY,
            eventId TEXT,
            description TEXT,
            available INTEGER,
            count INTEGER,
            inventoryTypes TEXT,
            offerTypes TEXT,
            offers TEXT,
            shapes TEXT,
            places TEXT,
            placeGroups TEXT,
            tracking INTEGER DEFAULT 0, 
            FOREIGN KEY (eventId) REFERENCES events (eventId)
            UNIQUE (inventoryTypes, offers, shapes)
        )
    ''')

    # Create offers table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS offers (
            offerId TEXT PRIMARY KEY,
            name TEXT,
            rank INTEGER,
            online INTEGER,
            protected INTEGER,
            rollup INTEGER,
            inventoryType TEXT,
            offerType TEXT,
            ticketTypeId TEXT,
            auditPriceLevel TEXT,
            priceLevelId TEXT,
            priceLevelSecname TEXT,
            description TEXT,
            currency TEXT,
            listPrice REAL,
            faceValue REAL,
            totalPrice REAL,
            noChargesPrice REAL,
            section TEXT,
            row TEXT,
            seatFrom TEXT,
            seatTo TEXT,
            sellerNotes TEXT
        )
    ''')

    conn.commit()
    conn.close()    

def load_event_ids():
    with open("events.txt", "r") as f:
        return [line.strip() for line in f.readlines()]

def load_discord_webhook():
    with open("webhook.txt", "r") as f:
        return f.read().strip()

def scrape_data_from_url(event_id):
    api_key = "89ad59bd-3157-4945-99ed-0604c4d42801"
    base_url = "https://proxy.scrapeops.io/v1/"
    params = {
        "api_key": api_key,
        "url": f"https://www.ticketmaster.com/event/{event_id}",
        "render_js": "true",
        "bypass": "perimeterx"
    }

    response = requests.get(base_url, params=params)
    soup = BeautifulSoup(response.text, "html.parser")
    
    # Extracting Time and Date
    event_date_div = soup.find("div", class_="event-header__event-date")
    event_date = event_date_div.get_text(strip=True) if event_date_div else ""
    
    # Extracting Title
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""
    
    # Extracting Link
    link_meta = soup.find("meta", property="al:web:url")
    link = link_meta["content"] if link_meta else ""
    
    return {
        "event_date": event_date,
        "title": title,
        "link": link
    }

def send_discord_webhook(event_id, scraped_data):
    webhook_url = load_discord_webhook()

    # Connect to SQLite database (creates a new one if not exists)
    conn = sqlite3.connect('db.sqlite')
    cursor = conn.cursor()

    # Execute the query
    cursor.execute('''
        SELECT f.id, o.name, f.inventoryTypes, f.offerTypes, f.offers, f.tracking, o.section, o.row, o.currency, o.listPrice, o.totalPrice
        FROM facets f
        JOIN offers o ON f.offers = o.offerId
        WHERE f.tracking = 0;
    ''')


    # Fetch and print the results
    results = cursor.fetchall()

    for row in results:
        id, name, inventory_types, offer_types, offers, tracking, section, row_val, currency, list_price, totalPrice = row

        if name:
            data = {
                "content": f"New Seat Avialable: {scraped_data['title']}",
                "embeds": [
                    {
                        "title": f"This is a {name}",
                        "description": f"""
                                        ID: {offers}
                                        Selection: {inventory_types}
                                        Offer Type: {offer_types} \n
                                        Currency: {currency} 
                                        List Price: {list_price}
                                        Fees: {round(float(totalPrice - list_price), 2)}
                                        Total Price: {totalPrice}
                                        """,
                        "url": scraped_data['link'],
                        "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime()),
                        "footer": {
                            "text": "Ticketmaster Restock Notifier"
                        },
                        "color": 32768  # This is green.
                    }
                ]
            }
        else:
            data = {
                "content": f"New Seat Avialable: {scraped_data['title']}",
                "embeds": [
                    {
                        "title": f"Sec {section} Row{row_val}",
                        "description": f"""
                                        ID: {offers}
                                        Selection: {inventory_types}
                                        Section:{section} 
                                        Row:{row_val} 
                                        Offer Type: {offer_types} \n
                                        Currency: {currency} 
                                        List Price: {list_price}
                                        Fees: {round(float(totalPrice - list_price), 2)}
                                        Total Price: {totalPrice}
                                        """,
                        "url": scraped_data['link'],
                        "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime()),
                        "footer": {
                            "text": "Ticketmaster Restock Notifier"
                        },
                        "color": 32768  # This is green.
                    }
                ]
            }
        response = requests.post(webhook_url, json=data)
        if response.status_code == 204:
            print(f"Notification sent for Event ID {event_id}!")
        else:
            print(f"Failed to send notification for Event ID {event_id}!")

        cursor.execute('''
            UPDATE facets
            SET tracking = 1
            WHERE id = ?;
        ''', (id,))

    conn.commit()
    conn.close()    

def get_ticketmaster_data(event_id, scraped_data):
    url = f"https://services.ticketmaster.com/api/ismds/event/{event_id}/facets?by=shape+attributes+available+accessibility+offer+placeGroups+inventoryType+offerType+description&show=places&embed=description&q=available&compress=places&resaleChannelId=internal.ecommerce.consumer.desktop.web.browser.ticketmaster.us&apikey=b462oi7fic6pehcdkzony5bxhe&apisecret=pquzpfrfz7zd2ylvtz3w5dtyse&embed=offer"
    payload = {}
    headers = {
        'c-reese84': '3:8hHwF7w9eimSR86uN6lrLQ==:bZyC8E+nG8kbBhdFgXbOcurOmRQjHnmulKJy7e+TKv6zHDscC2ebiNHEQnkq0AA8ehJovjbXdgy485le82xqaeKnFD/Tm3DMZ4qcNQTMuKiG4er6BbjfWJHreQUM2E56/oGJv0mKX9FqlwyYvN9/BcS3X/KNxxfLdkgh49oXRpcKWSlHM5S+TqwFXRuLm8VKNU7ApYp63Be4yY/c/+0LkwWIkO++brK6eNlOeFziSOwFAg1qbpqQoBDiv6qeTYTITXdV+fOBttHg4XznHTdBcVFjZBGYE1iEMCBulrqnq5OnyVJGEDO3vVQyknjQQ4erCAj7u3anDpkdnRo/4qwhocZv0ApejOf5zQz69KyW+UIpVsRR7OXPr4lQ5BEzU1ZOEPdJr62R42qE/7e14uy3K90HZ/Arx+0lni9OVQq728Y9cegXYtEHTqXGNvDwLuWzPP4Mn8hejql/cTNFRwfb0A==:1ACSOfGUAjPbCl+9Ml5+frVnTAEkgeoUWLcApzxfyfM=',
        'Referer': 'https://www.ticketmaster.com/',
        'TMPS-Correlation-Id': '0eb99df4-0f8c-4a74-89d3-a1b814117fdb',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36'
    }
    response = requests.request("GET", url, headers=headers, data=payload)

    if response.status_code == 200:
        try:
            create_database()
            update_database(response.json())
            send_discord_webhook(event_id, scraped_data)
        except json.JSONDecodeError:
            print(f"Event ID: {event_id} - Error decoding JSON!")
    else:
        # print(f"Event ID: {event_id} - Status code: {response.status_code}")
        print(f"Event ID: {event_id} - Status code: {response.status_code}")

event_ids = load_event_ids()
scraped_data_dict = {event_id: scrape_data_from_url(event_id) for event_id in event_ids}

while True:
    for event_id in event_ids:
        get_ticketmaster_data(event_id, scraped_data_dict[event_id])
        time.sleep(60)  # wait for 60 seconds (1 minute) before checking the next event
