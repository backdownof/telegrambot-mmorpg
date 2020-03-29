#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import logging
import ssl
import psycopg2
import telebot
import urllib
import time
from contextlib import closing
from datetime import datetime
from abc import ABC, abstractmethod
import random
import sqlalchemy
from sqlalchemy import create_engine

from aiohttp import web
from telebot import apihelper
from telebot import types

API_TOKEN = '1026555302:AAFnEUlCRPohaK5HOnLN6znuUmjx1DXjU2A'

WEBHOOK_HOST = '35.228.188.61'
WEBHOOK_PORT = 8443  # 443, 80, 88 or 8443 (port need to be 'open')
WEBHOOK_LISTEN = '0.0.0.0'  # In some VPS you may need to put here the IP addr

WEBHOOK_SSL_CERT = './sslsert/webhook_cert.pem'  # Path to the ssl certificate
WEBHOOK_SSL_PRIV = './sslsert/webhook_pkey.pem'  # Path to the ssl private key

connection =  psycopg2.connect(dbname='webhook-bot-1', user='postgres', password='23O3l995', host='127.0.0.1')

# Quick'n'dirty SSL certificate generation:
#
# openssl genrsa -out webhook_pkey.pem 2048
# openssl req -new -x509 -days 3650 -key webhook_pkey.pem -out webhook_cert.pem
#
# When asked for "Common Name (e.g. server FQDN or YOUR name)" you should reply
# with the same value in you put in WEBHOOK_HOST

WEBHOOK_URL_BASE = "https://{}:{}".format(WEBHOOK_HOST, WEBHOOK_PORT)
WEBHOOK_URL_PATH = "/{}/".format(API_TOKEN)

logger = telebot.logger
telebot.logger.setLevel(logging.INFO)
# tb = telebot.AsyncTeleBot("TOKEN")
bot = telebot.AsyncTeleBot(API_TOKEN)
# bot = telebot.TeleBot(API_TOKEN)

app = web.Application()

START_PLAYER_LOCATION = 1
player_id = None
character_id = None
chat_id = None
username = None
current_location_id = None

db_string = "postgres://postgres:23O3l995@localhost/webhook-bot-1"
db = create_engine(db_string)

result_set = db.execute("SELECT * FROM player")  
for r in result_set:  
    print(r)

class Unit(ABC):
    @abstractmethod
    def fight(self):
        raise NotImplementedError("Subclass must implement abstract method")


class Mob(Unit):
    def __init__(self, mob_id):
        try:
            conn = getConnection()
            c = conn.cursor()
            c.execute("SELECT atk, def, hp, exp_drop, name FROM mobs WHERE mob_id = "+ str(mob_id) +";")
            stats = c.fetchall()
            c.close()
            conn.close()
            if stats is not None:
                self.mob_id = mob_id
                self.damage = stats[0][0]
                self.armor = stats[0][1]
                self.hp = stats[0][2]
                self.exp_drop = stats[0][3]
                self.name = stats[0][4]
        except (Exception, psycopg2.DatabaseError) as error:
            print("Mob init error " + error)

    def fight(self):
        pass


class Player(Unit):
    def __init__(self, character_id):
        try:
            conn = getConnection()
            c = conn.cursor()
            c.execute("SELECT damage, armor, exp, class_id, level, hp, max_hp, regen_hp, class_id FROM character WHERE character_id = "+ str(character_id) +";")
            stats = c.fetchall()
            c.close()
            if stats is not None:
                self.damage = stats[0][0]
                self.armor = stats[0][1]
                self.exp = stats[0][2]
                self.class_id = stats[0][3]
                self.level = stats[0][4]
                self.hp = stats[0][5]
                self.max_hp = stats[0][6]
                self.regen_hp = stats[0][7]
                self.class_id = stats[0][8]
                self.character_id = character_id
                self.name = "xxx"

                equiped_items = self.get_equpied_items(conn, self.character_id)
                
                with conn.cursor():
                    for item in equiped_items:
                        c.execute("SELECT dmg, def FROM items WHERE item_id = "+ str(item) +";")
                        items = c.fetchall()
                        c.close()
                        conn.close()
                        if items is not None:
                            for item in items:
                                if item[0] is not None:
                                    self.damage = self.damage + item[0]
                                if item[1] is not None:
                                    self.armor = self.armor + item[1]
            
                

                c.execute("SELECT str, agi, int, body FROM classes WHERE class_id = "+ str(self.class_id) +";")
                class_stats = c.fetchone()

                if self.class_id == 1:
                    self.damage = self.damage + class_stats[0] + (class_stats[0] * self.level * 0.2)
                    self.armor = self.armor + class_stats[0] + (class_stats[0] * self.level * 0.2)
                    self.hp = self.hp + class_stats[3] * 10
                elif self.class_id == 2:
                    self.damage = self.damage + class_stats[1] + (class_stats[1] * self.level * 0.2)
                    self.armor = self.armor + class_stats[0] + (class_stats[0] * self.level * 0.2)
                    self.hp = self.hp + class_stats[3] * 10
                else:
                    self.damage = self.damage + class_stats[2] + (class_stats[2] * self.level * 0.2)
                    self.armor = self.armor + class_stats[0] + (class_stats[0] * self.level * 0.2)
        except (Exception, psycopg2.DatabaseError) as error:
            print("Mob init error " + error)


    def fight(self, other):
        global current_location_id
        log_txt = ""

        if type(other) is Mob:
            print("\nmob exp drop = " + str(other.exp_drop))
            with conn.cursor() as c:
                c.execute("SELECT unit_id FROM location_mobs WHERE killed = false AND fighting = FALSE AND mob_id = "+ str(other.mob_id) +" LIMIT 1")
                unit = c.fetchone()
                if unit is not None:
                    unit_id = unit[0]
                    c.execute("UPDATE location_mobs SET fighting = true WHERE unit_id = "+ str(unit_id) +";")
                    i = 1
                    while True:
                        time.sleep(1)
                        if i == 0 and random.random < 0.5:
                            self.hp = self.hp - other.damage
                            log_txt += ("**" + other.name + "** нанес тебе " + str(other.damage) + " урона\n")
                            i += 1
                            continue

                        if i % 2 == 1:
                            self.hp = self.hp - other.damage
                            log_txt += ("**" + other.name + "** нанес тебе " + str(other.damage) + " урона\n")
                        else:
                            other.hp = other.hp - self.damage
                            log_txt += ("**Ты** нанес " + other.name + " " + str(self.damage) + " урона\n")

                        if self.hp <= 0:
                            log_txt += "Ты проиграл :(\n"
                            break
                        if other.hp <= 0:
                            sql = "UPDATE location_mobs SET killed = true, fighting = false, kill_time = %s WHERE unit_id = %s;"
                            c.execute(sql, (datetime.now(), unit_id))
                            update_stack_at_loc(conn, other.mob_id)
                            log_txt += "Победа!\n"
                            c.execute("SELECT item_id, drop_chance FROM mobs_drop WHERE mob_id = " + str(other.mob_id) + ";")
                            drops = c.fetchall()
                            if drops is not None:
                                for drop in drops:
                                    if random.random() <= drop[1]:
                                        c.execute("SELECT name FROM items WHERE item_id = " + str(drop[0]) + ";")
                                        add_item_to_inventory(conn, drop[0])
                                        log_txt += "Ты получил " + c.fetchone()[0] 
                            break
                        i += 1
                else:
                    print("нема росянок")
        log_txt += "\n\n"
        get_markup(conn, current_location_id, log_txt)

    def get_equpied_items(self,conn, character_id):
        equip_items = []
        with conn.cursor() as c:
            c.execute("SELECT item_id FROM inventory WHERE character_id = "+ str(character_id) +" AND is_equiped = true;")
            items = c.fetchall()
            if items is not None:
                for item in items:
                    equip_items.append(item[0])
            return equip_items


def update_stack_at_loc(conn, mob):
    global current_location_id
    with conn.cursor() as c:
        c.execute("SELECT unit_id, kill_time FROM location_mobs WHERE location_id = "+ str(current_location_id) +" AND killed = true;")
        locs_stats = c.fetchall()
        for loc_stat in locs_stats:
            c.execute("SELECT respawn_time FROM mobs WHERE mob_id = "+ str(mob) +";")
            resp_time = c.fetchone()[0]
            kill_time = loc_stat[1]
            time_now = datetime.now()
            if ((time_now - kill_time).seconds >= resp_time):
                c.execute("UPDATE location_mobs SET killed = false WHERE unit_id = " + str(loc_stat[0]) +";")
            

# Process webhook calls
async def handle(request):
    if request.match_info.get('token') == bot.token:
        request_body_dict = await request.json()
        update = telebot.types.Update.de_json(request_body_dict)
        bot.process_new_updates([update])
        return web.Response()
    else:
        return web.Response(status=403)


app.router.add_post('/{token}/', handle)


@bot.message_handler(commands=['start'])
def echo_message(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    itembtncreate = types.KeyboardButton('👶 Создать персонажа')
    markup.row(itembtncreate)
    send_msg_markup(message.chat.id, "Дорогой искатель приключений,\nДобро пожаловать в MMORPG Chrome Age 3\nДля создания персонажа нажимай кнопку и погнали", markup, None)


@bot.message_handler(func=lambda message: True, content_types=['text'])
def echo_message(message):
    if message.text == "x":
        print("Версия SQLAlchemy:", sqlalchemy.__version__)
    global chat_id, username, player_id
    chat_id = message.chat.id
    username = message.from_user.username
    
    conn = getConnection()
    cursor = conn.cursor()
    in_action = check_player_id(username)
    if in_action is True:
        get_player_location(player_id)
        cursor.execute("UPDATE player SET in_action = true WHERE player_id = "+ str(player_id) +";")
        if message.text == '👶 Создать персонажа':
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            itembtnwar = types.KeyboardButton('🎅 Воин')
            itembtnmage = types.KeyboardButton('👰 Маг')
            itembtnassasign = types.KeyboardButton('💂 Убийца')
            markup.row(itembtnwar, itembtnmage, itembtnassasign)
            send_msg_markup(chat_id, "Выбери класс персонажа: \n\n🎅 Воин\n👰 Маг\n💂 Убийца\n", markup, cursor)

        elif message.text == '🎅 Воин':
            set_char_class(1, message.from_user.username, chat_id, conn)
        elif message.text == '👰 Маг':
            set_char_class(3, message.from_user.username, chat_id, conn)
        elif message.text == '💂 Убийца':
            set_char_class(2, message.from_user.username, chat_id, conn)
        elif message.text == '👣 Идти':
            send_near_locations(conn, username)
        elif '⚔️ Драться с ' in message.text:
            mob = message.text.split('⚔️ Драться с ')
            fight(conn, character_id, mob[1])
        else:
            cursor.execute("SELECT location_id FROM location WHERE name = '"+ message.text +"';")
            rows = cursor.fetchone()
            if rows is not None:
                change_player_location(conn, rows[0])
    else:
        send_msg_error(chat_id, "Что-то пошло не так. Подождите")
    cursor.close()
    conn.commit()
                    
                
def check_player_id(username):
    global player_id, character_id
    try:
        conn = getConnection()
        cursor = conn.cursor()
        cursor.execute("SELECT player_id, character_id, in_action FROM player WHERE username = '"+ username +"'")
        rows = cursor.fetchone()
        if rows is not None and rows[2] is False:
            player_id = rows[0]
            character_id = rows[1]
            return True
        else:
            return False
    except (Exception, psycopg2.DatabaseError) as error:
        print ("Error while check player_id: ", error)
    finally:
        cursor.close()

def get_player_location(player_id):
    global current_location_id
    try:
        conn = getConnection()
        cursor = conn.cursor()
        cursor.execute("SELECT location_id FROM player_location WHERE player_id = "+ str(player_id) +";")
        loc = cursor.fetchone()
        if loc is not None:
            current_location_id = loc[0]
            return True
        else:
            return False
    except (Exception, psycopg2.DatabaseError) as error:
        print ("Error while getting player location: ", error)
    finally:
        cursor.close()


def fight(char_id, mob):
    global current_location_id
    if current_location_id is not None:
        try:
            conn = getConnection()
            c = conn.cursor()
            c.execute("SELECT mob_id FROM mobs WHERE name = '"+ mob +"';")
            mob_to_fight = c.fetchone()[0]
            c.close()
            if mob_to_fight is not None:
                update_stack_at_loc(mob_to_fight)
                monster = Mob(mob_to_fight)
                player = Player(char_id)
                player.fight(monster)
        except (Exception, psycopg2.DatabaseError) as error:
            print ("Error while getting player location: ", error)


def set_char_class(char_class, username, chat_id):
    cr_player = """INSERT INTO player(username)
             VALUES(%s) RETURNING player_id;"""
    global player_id

    try:
        conn = getConnection()
        cursor = conn.cursor()
        cursor.execute("SELECT player_id FROM player WHERE username = '"+ username +"'")
        rows = cursor.fetchone()
        cursor.close()
        if rows is not None:
            for row in rows:
                player_id = row
                send_msg(chat_id, 'Дружище, у тебя уже есть ' + str(row) + '. \nНового персонажа ты создать пока не можешь.', cursor)
        else:
            cursor.execute(cr_player, (username,))
            rows = cursor.fetchone()
            for row in rows:
                player_id = row

            create_char(conn, char_class)
            conn = getConnection()
            cursor = conn.cursor()
            cursor.execute("UPDATE player SET character_id = (%s) WHERE player_id = (%s);", (character_id, player_id,))
            conn.commit()
            cursor.close()
            add_item_to_inventory(conn, 1, True)
            change_player_location(conn, START_PLAYER_LOCATION)
            
            set_last_action_time(conn, player_id)
    except (Exception, psycopg2.DatabaseError) as error:
        print ("Error while getting player location: ", error)   
    
        
def send_near_locations(username):
    global chat_id, current_location_id
    try:
        rows = get_near_locations(current_location_id)
        if rows is not None:
            for row in rows:
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                keys = []
                for loc in row:
                    conn = getConnection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT name FROM location WHERE location_id = " + str(loc) + ";")
                    loc_name = cursor.fetchone()[0]
                    cursor.close()
                    keys.append(types.KeyboardButton(loc_name))

                markup.row(*keys)
                send_msg_markup(chat_id, "Куда пойдем?", markup, cursor)
    except (Exception, psycopg2.DatabaseError) as error:
        print ("Error while getting player location: ", error)    

                    
def get_near_locations(current_location):
    try:
        conn = getConnection()
        cursor = conn.cursor()
        cursor.execute("SELECT near_locations FROM location WHERE location_id = "+ str(current_location_id) +";")
        rows = cursor.fetchone()
        cursor.close()
        return rows
    except (Exception, psycopg2.DatabaseError) as error:
        print ("Error while getting player location: ", error) 
    



def equip_item(item):
    global character_id
    try:
        conn = getConnection()
        cursor = conn.cursor()
        cursor.execute("SELECT character_id, item_id FROM inventory WHERE character_id = %s AND item_id = %s;", (character_id, item,))
        rows = cursor.fetchone()
        cursor.close()
        if rows is not None:
            cursor.execute("UPDATE inventory SET is_equiped = True WHERE character_id = %s AND item_id = %s;", (character_id, item,))
    except (Exception, psycopg2.DatabaseError) as error:
        print ("Error while getting player location: ", error) 


def add_item_to_inventory(item, is_equiped=False):
    global character_id
    try:
        conn = getConnection()
        cursor = conn.cursor()
        sql_add_item = "INSERT INTO inventory (character_id, item_id, is_equiped) VALUES(%s, %s, %s);"
        cursor.execute(sql_add_item, (character_id, item, is_equiped,))
        conn.commit()
        cursor.close()
    except (Exception, psycopg2.DatabaseError) as error:
        print ("Error while getting player location: ", error) 



def change_player_location(loc):
    global player_id, current_location_id
    try:
        if loc in get_near_locations(current_location_id)[0]:
            conn = getConnection()
            cursor = conn.cursor()
            cursor.execute("SELECT player_id FROM player_location WHERE player_id = %s;", (player_id,))
            rows = cursor.fetchone()
            if rows is None:
                sql_insert_player_location = "INSERT INTO player_location (player_id, location_id) VALUES(%s, %s);"
                cursor.execute(sql_insert_player_location, (player_id, loc))
            else:
                cursor.execute("UPDATE player_location SET location_id = (%s) WHERE player_id = (%s);", (loc, player_id,))

            cursor.execute("SELECT visited_locations FROM player WHERE player_id = "+ str(player_id) +";")
            vis_locs = cursor.fetchone()
            if vis_locs is not None:
                if loc not in vis_locs:
                    cursor.execute("UPDATE player SET visited_locations = array_append(visited_locations, " + str(loc) + ") WHERE player_id = %s;", (player_id,))

            get_markup(loc)
    except (Exception, psycopg2.DatabaseError) as error:
        print ("Error while getting player location: ", error) 


def get_markup(loc, msg=""):
    global chat_id
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    msg_text = msg
    
    try:
        conn = getConnection()
        cursor = conn.cursor()
        cursor.execute("SELECT description, welcomemsg, type FROM location WHERE location_id = %s;", (loc,))
        rows = cursor.fetchone()
        cursor.close()
        if rows is not None:
            if 'non_city' in rows:
                btns_mobs = []
                monsters = get_mobs_at_loc(conn, loc)
                msg_text += "Мобы в локации:\n\n"

                for mob in monsters:
                    cursor.execute("SELECT name, level FROM mobs WHERE mob_id = " + str(mob) + ";")
                    mob_desc = cursor.fetchall()
                    mob_txt = ""
                    
                    for x in mob_desc:
                        mob_txt = mob_txt + x[0] + " (" + str(x[1]) + " уровень)" + str(monsters[mob]) + "шт."
                        btns_mobs.append(types.KeyboardButton('⚔️ Драться с ' + x[0]))
                    msg_text = msg_text + mob_txt + "\n"
                    
                btns_mobs.append(types.KeyboardButton('👣 Идти'))
                markup.row(*btns_mobs)
                    
            elif 'city' in rows:
                btn_go = types.KeyboardButton('👣 Идти')
                btn_inventory = types.KeyboardButton('🎒 Инвентарь')
                markup.row(btn_go, btn_inventory)
                msg_text = msg_text + str(rows[0]).replace('\\n', '\n') + "\n\n"

        send_msg_markup(chat_id, msg_text, markup, cursor)
    except (Exception, psycopg2.DatabaseError) as error:
        print ("Error while getting player location: ", error) 


def get_mobs_at_loc(loc):
    d = {}
    with conn.cursor() as c:
        c.execute("SELECT DISTINCT mob_id FROM location_mobs WHERE location_id = "+ str(loc) +";")
        mobs = c.fetchall()
        if mobs is not None:
            for mob in mobs:
                c.execute("SELECT COUNT (mob_id) FROM location_mobs WHERE mob_id = "+ str(mob[0]) +";")
                d[mob[0]] = c.fetchone()[0]
        
    return d
                


def create_char(conn, char_class):
    sql_create_char = """INSERT INTO character (damage, armor, exp, class_id, level, atk_speed, crit_chance, hp, max_hp, regen_hp)
                        VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING character_id;
                    """
    with conn.cursor() as cursor:
        cursor.execute(sql_create_char, (1, 0, 0, char_class, 1, 1.0, 0.1, 100, 100, 1))
        rows = cursor.fetchone()

        if rows is not None:
            for row in rows:
                global character_id
                character_id = row


def set_last_action_time(conn, player_id):
    sql_upd_time = """UPDATE player SET last_action = %s WHERE player_id = %s;"""

    dateTimeObj = datetime.utcnow()
    with conn.cursor() as cursor:
        cursor.execute(sql_upd_time, (dateTimeObj, player_id))

def send_msg_error(telegram_id, msg):
    try:
        bot.send_message(telegram_id, msg, parse_mode="Markdown")
    except (ConnectionAbortedError, ConnectionResetError, ConnectionRefusedError, ConnectionError):
        print("ConnectionError - Sending again after 5 seconds!!!")
        time.sleep(5)
        bot.send_message(telegram_id, msg)

def send_msg(telegram_id, msg, cursor):
    global player_id
    try:
        bot.send_message(telegram_id, msg, parse_mode="Markdown")
        cursor.execute("UPDATE player SET in_action = false WHERE player_id = "+ str(player_id) +";")
    except (ConnectionAbortedError, ConnectionResetError, ConnectionRefusedError, ConnectionError):
        print("ConnectionError - Sending again after 5 seconds!!!")
        time.sleep(5)
        bot.send_message(telegram_id, msg)


def send_msg_markup(telegram_id, msg, markup, cursor):
    global player_id
    try:
        cursor.execute("UPDATE player SET in_action = false WHERE player_id = "+ str(player_id) +";")
        bot.send_message(telegram_id, msg, reply_markup=markup, parse_mode="Markdown")
    except (ConnectionAbortedError, ConnectionResetError, ConnectionRefusedError, ConnectionError):
        print("ConnectionError - Sending again after 5 seconds!!!")
        time.sleep(5)
        bot.send_message(telegram_id, msg)

# Remove webhook, it fails sometimes the set if there is a previous webhook
bot.remove_webhook()

# Set webhook
bot.set_webhook(url=WEBHOOK_URL_BASE + WEBHOOK_URL_PATH,
                certificate=open(WEBHOOK_SSL_CERT, 'r'))

# Build ssl context
context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
context.load_cert_chain(WEBHOOK_SSL_CERT, WEBHOOK_SSL_PRIV)

# Start aiohttp server
web.run_app(
    app,
    host=WEBHOOK_LISTEN,
    port=WEBHOOK_PORT,
    ssl_context=context,
)