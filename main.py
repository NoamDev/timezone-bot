import re
from pony.orm.core import Entity
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pony.orm import *
import pytz
from datetime import date, datetime
from geopy.geocoders import Nominatim
from tzwhere import tzwhere
import base64
import os

g=Nominatim(user_agent='localzone_bot')
tzwhere_instance = tzwhere.tzwhere()
API_ID=os.environ['API_ID']
API_HASH=os.environ['API_HASH']
BOT_TOKEN = os.environ['BOT_TOKEN']
USERNAME = os.environ['USERNAME']
ONLY_GROUP = int(os.environ['ONLY_GROUP']) if 'ONLY_GROUP' in os.environ else None

time_regex=re.compile('([0-9]|0[0-9]|1[0-9]|2[0-3])(?:[:.]([0-5][0-9]))? ?(a\.?m\.?|p\.?m\.?)? ?([a-z]{2,}(?:/[a-z]{2,})?)', flags=re.IGNORECASE)

def parse_timezone(text):
    try:
        tz = pytz.timezone(text)
        return tz
    except:
        try:
            place, (lat,lng) = g.geocode(text)
            tz = pytz.timezone(tzwhere_instance.tzNameAt(lat,lng))
            return tz
        except:
            return None    

def first_with_basic_timezone(times):
    for tpl in times:
        *args,timezone = tpl
        try:
            tz=pytz.timezone(timezone)
            return *args,tz
        except:
            pass

db = Database()

class Preference(db.Entity):
    user_id = PrimaryKey(int)
    timezone = Optional(str)

if 'DATABASE_URL' in os.environ:
    user,password,host,port,db_name = re.match('postgres://(.*):(.*)@(.*):(.*)/(.*)', os.environ['DATABASE_URL']).groups()
    db.bind(
    provider='postgres',
    user=user,
    password=password,
    host=host,
    port=port,
    database=db_name
    )
else:
    db.bind(provider='sqlite', filename='db.sqlite', create_db=True)

db.generate_mapping(create_tables=True)

app = Client(
    'my_bot',
    bot_token=BOT_TOKEN,
    api_id=API_ID,
    api_hash=API_HASH
)

@app.on_message(filters.regex(time_regex, flags=re.IGNORECASE) & filters.group)
def group_time_message(client: Client, message: Message):
    if ONLY_GROUP is not None and message.chat.id != ONLY_GROUP:
        return
    times=time_regex.findall(message.text or message.caption)

    tpl = first_with_basic_timezone(times)
    if tpl is None:
        return
    
    hours,minutes,am_pm,tz = first_with_basic_timezone(times)

    hours = int(hours)
    if minutes == '':
        minutes = '00'
    minutes = int(minutes)
    am_pm = am_pm.lower().replace('.','')
    if am_pm == '':
        am_pm = None

    # handle am/pm
    if am_pm :
        if hours>12:
            return
        parsed_dt = datetime.strptime(f'{hours} {am_pm}','%I %p')
        hours = parsed_dt.hour
    
    now=datetime.now()
    dt = datetime(now.year, now.month, now.day, hours, minutes)
    utc = dt - tz.utcoffset(now)

    keyboard=InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(
                text='show in my local timezone',
                callback_data=utc.strftime('%H:%M')
            )]
        ]
    )
    message.reply_text(text=f'{dt.strftime("%H:%M")} {tz.zone}', reply_markup=keyboard)

@app.on_callback_query()
def on_time_button(client: Client, callback_query: CallbackQuery):
    time=callback_query.data

    parsed = datetime.strptime(time, '%H:%M')
    now=datetime.now()
    dt = datetime(now.year, now.month, now.day, parsed.hour, parsed.minute)

    user_id = callback_query.from_user.id
    with db_session():
         preference = Preference.get(user_id=user_id)
    if preference is not None and preference.timezone is not None:
        tz=pytz.timezone(preference.timezone)
        localized = dt + tz.utcoffset(dt)

        callback_query.answer(f"{time} UTC, which is {localized.strftime('%H:%M')} in {tz.zone}", show_alert=True)
    else:
#        encoded_link = base64.urlsafe_b64encode(callback_query.message.link.encode('utf8')).decode('utf8')
        callback_query.answer(time, show_alert=True, url=f't.me/{USERNAME}?start=a')

@app.on_message(filters=filters.private & filters.command('start'))
def on_start_command(client: Client, message: Message):
    if len(message.command) > 1:
        encoded_link=message.command[1]
        #link = base64.urlsafe_b64decode(encoded_link).decode('utf8')
        message.reply_text(f"""Please set your timezone.
with the command /set timezone
for example: /set Europe/Berlin, /set Israel
then, go back to where you came from and click the button again""")

@app.on_message(filters=filters.private & filters.command('set'))
def set_timezone(client: Client, message: Message):
    uid = message.from_user.id
    if len(message.command) > 1:
        tz = parse_timezone(message.command[1])
        if tz is not None:
            with db_session():
                preference = Preference.get(user_id=uid) or Preference(user_id=uid)
                preference.timezone = tz.zone
            message.reply(f'Your timezone was set to {tz.zone}')
        else:
                message.reply_text("""Please use this format /set timezone
for example: /set Europe/Berlin, /set Israel""")
    else:
        message.reply_text("""Please use this format /set timezone
for example: /set Europe/Berlin, /set Israel""")

app.run()