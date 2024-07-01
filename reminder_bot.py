from telebot import TeleBot, types
from logging import basicConfig, INFO, getLogger
from sqlite3 import connect
from datetime import datetime
from threading import Thread
from time import sleep
from calendar import monthrange
from flask import Flask, request

bot = TeleBot('your_bot_token') # Вставьте сюда токен от @FatherBot из телеграмма
app = Flask(__name__)
WEBHOOK_URL = 'your_web_server_url/webhook' # Вставьте сюда ссылку на веб-сервер (/webhook надо оставить)
connection = connect('users.db', check_same_thread=False) #Подключение к базе данных с информацией о пользователях

# Создаем хранилище состояний в виде словаря
user_state = {}
user_data = {}
numbers = "0123456789"
# Настройка логирования
basicConfig(
    filename='bot.log',  # Имя файла для записи логов
    filemode='a',        # Режим записи (a - добавление к существующему, w - перезапись файла)
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=INFO
)
logger = getLogger(__name__)

# Исключение для неотрицательных целых чисел
class PositiveNumbers(Exception):
    def __init__(self, text):
        self.text = text

# Исключение для проверки даты
class CorrectDate(Exception):
    def __init__(self, text):
        self.text = text

# Состояния пользователя
class UserState:
    DATE = 1
    TIME = 2
    REMIND = 3
    DEL = 4


def set_state(user_id, state):
    user_state[user_id] = state


def get_state(user_id):
    return user_state.get(user_id)

# Вебхук для получения сообщений
@app.route("/webhook", methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_str = request.get_data().decode('UTF-8')
        try:
            update = types.Update.de_json(json_str)
            bot.process_new_updates([update])
        except Exception as e:
            print(f"Ошибка обработки обновления: {e}")
            return 'Ошибка', 500
        return 'OK', 200
    else:
        return 'Неподдерживаемый тип данных', 415

# inline-клавиатура основного меню
def show_buttons(id):
    keys = []
    keyboard = types.InlineKeyboardMarkup()
    keys.append(types.InlineKeyboardButton(text='Добавить напоминание', callback_data='choice_add'))
    keys.append(types.InlineKeyboardButton(text='Убрать напоминание', callback_data='choice_del'))
    keys.append(types.InlineKeyboardButton(text='Посмотреть список напоминаний', callback_data='choice_show'))
    keys.append(types.InlineKeyboardButton(text='Посмотреть дела на сегодня', callback_data='choice_show_today'))
    for j in range(len(keys)):
        keyboard.add(keys[j])
    bot.send_message(id, text='Выбери пункт', reply_markup=keyboard)

# Проверка наличия пользователя в базе
def check_new_user(id):
    cursor = connection.cursor()
    cursor.execute('select * from users where id = ?', (id,))
    check = cursor.fetchall()
    if len(check) == 0:
        cursor.execute('insert into users (id) values (?)', (id,))
    cursor.close()

# проверка того, есть ли у пользователя напоминания
def check_list(id):
    cursor = connection.cursor()
    cursor.execute('select * from schedule where user = ?', (id,))
    check = cursor.fetchall()
    cursor.close()
    if len(check) == 0:
        return False
    return True

# вывод напоминаний
def show_list(id, day):
    cursor = connection.cursor()
    if day == "today":
        time_now = datetime.now()
        date = str(time_now.strftime('%d.%m.%Y'))
        cursor.execute('select * from schedule where user = ? and date = ? order by time(time) asc', (id, date))
    else:
        cursor.execute('select * from schedule where user = ? order by date(date) desc', (id,))
    list = cursor.fetchall()
    cursor.close()
    message = ""
    for remind in list:
        message += f'ID:{remind[0]} Дата:{remind[2]},{remind[3]},\n{remind[4]}\n'
    bot.send_message(id, message)


# Обработчик нажатий на кнопки
@bot.callback_query_handler(func=lambda call: True)
def callback_worker(call):
    user_id = call.from_user.id
    if call.data == "choice_add":
        bot.send_message(call.message.chat.id, "Напишите дату (день.месяц.год)")
        set_state(user_id, UserState.DATE)

    if call.data == "choice_del":
        if check_list(call.message.chat.id):
            bot.send_message(call.message.chat.id, "Напиши id напоминания, которое надо удалить")
            set_state(user_id, UserState.DEL)
        else:
            bot.send_message(call.message.chat.id, "Напоминаний нет")
            show_buttons(call.message.chat.id)

    if call.data == "choice_show":
        if check_list(call.message.chat.id):
            bot.send_message(call.message.chat.id, "Вот Ваши напоминания")
            show_list(call.message.chat.id, "not today")
        else:
            bot.send_message(call.message.chat.id, "Напоминаний нет")
        show_buttons(call.message.chat.id)
    if call.data == "choice_show_today":
        if check_list(call.message.chat.id):
            bot.send_message(call.message.chat.id, "Вот Ваши напоминания")
            show_list(call.message.chat.id, "today")
        else:
            bot.send_message(call.message.chat.id, "Напоминаний нет")
        show_buttons(call.message.chat.id)


@bot.message_handler(func=lambda message: get_state(message.from_user.id) == UserState.DEL)
def handle_del(message):
    user_id = message.from_user.id
    try:
        int(message.text)
        if int(message.text) < 0:
            raise PositiveNumbers("ID должен быть не меньше 0")
    except ValueError:
        bot.send_message(user_id, "Значение должно быть числом")
        bot.send_message(user_id, "Введите ID еще раз")
    except PositiveNumbers as pn:
        bot.send_message(user_id, str(pn))
        bot.send_message(user_id, "Введите ID еще раз")
    else:
        cursor = connection.cursor()
        cursor.execute('select user from schedule where id = ?', (message.text,))
        user = cursor.fetchall()
        if len(user) != 0:
            set_state(user_id, None)  # Сброс состояния
            cursor.execute('delete from schedule where id = ?', (message.text,))
            bot.send_message(message.chat.id, "Напоминание удалено")
            connection.commit()
            cursor.close()
            show_buttons(message.chat.id)
        else:
            keys = []
            keyboard = types.InlineKeyboardMarkup()
            keys.append(types.InlineKeyboardButton(text='Посмотрите список напоминаний', callback_data='choice_show'))
            for j in range(len(keys)):
                keyboard.add(keys[j])
            bot.send_message(message.chat.id, "У Вас нет такого ID.\nВведите ID снова или", reply_markup=keyboard)


@bot.message_handler(func=lambda message: get_state(message.from_user.id) == UserState.DATE)
def handle_date(message):
    user_id = message.from_user.id
    date = message.text.replace(" ", "")
    try:
        for i in range(len(date)):
            if date[i] not in numbers and date[i] not in ".":
                raise CorrectDate("Введите только цифры и точки")
        if date.count(".") != 2:
            raise CorrectDate("Введите только 2 точки между числами")
        if len(date) < 8 or len(date) > 10:
            raise CorrectDate("Введите корректную дату")
        date = date.split(".")
        if int(date[2]) < 2024 or len(date[2]) != 4:
            raise CorrectDate("Введите корректный год")

        if int(date[1]) < 1 or int(date[1]) > 12:
            raise CorrectDate("Введите корректный месяц")
        if len(date[1]) < 2:
            date[1] = "0" + date[1]

        if int(date[0]) < 1 or int(date[0]) > monthrange(int(date[2]), int(date[1]))[1]:
            raise CorrectDate("Введите корректный день")
        if len(date[0]) < 2:
            date[0] = "0" + date[0]

    except CorrectDate as cd:
        bot.send_message(user_id, str(cd))
        bot.send_message(user_id, "Введите дату еще раз")
    else:
        user_data[user_id] = {'date': ".".join(date)}
        bot.send_message(message.chat.id, "Напишите время")
        set_state(user_id, UserState.TIME)


@bot.message_handler(func=lambda message: get_state(message.from_user.id) == UserState.TIME)
def handle_time(message):
    user_id = message.from_user.id
    time = message.text.replace(" ", "")
    try:
        for i in range(len(time)):
            if time[i] not in numbers and time[i] not in ":":
                raise CorrectDate("Введите только цифры и :")
        if time.count(":") != 1:
            raise CorrectDate("Введите только 1 : между часами и минутами")
        if len(time) < 3 or len(time) > 5:
            raise CorrectDate("Введите корректное время")
        time = time.split(":")
        if int(time[0]) < 0 or int(time[0]) > 23:
            raise CorrectDate("Введите корректный час")
        if len(time[0]) < 2:
            time[0] = "0" + time[0]

        if int(time[1]) < 0 or int(time[1]) > 59:
            raise CorrectDate("Введите корректную минуту")
        if len(time[1]) < 2:
            time[1] = "0" + time[1]

    except CorrectDate as cd:
        bot.send_message(user_id, str(cd) + ".\n" + "Введите время еще раз")
    else:
        user_data[user_id]['time'] = ":".join(time)
        bot.send_message(message.chat.id, "Напишите текст напоминания")
        set_state(user_id, UserState.REMIND)


@bot.message_handler(func=lambda message: get_state(message.from_user.id) == UserState.REMIND)
def handle_remind(message):
    user_id = message.from_user.id
    remind = message.text
    user_data[user_id]['remind'] = remind
    bot.send_message(message.chat.id, f"Напоминание создано")
    set_state(user_id, None)  # Сброс состояния
    date = user_data[user_id]['date']
    time = user_data[user_id]['time']
    text = user_data[user_id]['remind']
    cursor = connection.cursor()
    cursor.execute('INSERT INTO schedule (user, date, time, business) VALUES (?, ?, ?, ?)', (user_id, date, time, text))
    connection.commit()
    cursor.close()
    del user_data[user_id]
    show_buttons(message.chat.id)


@bot.message_handler(func=lambda message: True)
def get_text_messages(message):
    user_id = message.from_user.id
    check_new_user(user_id)
    show_buttons(user_id)

# Проверка, надо ли отправлять пользователю напоминание или нет
def run_scheduler():
    while True:
        time_now = datetime.now()
        time_now = str(time_now.strftime('%d.%m.%Y %H:%M')).split(" ")
        cursor = connection.cursor()
        cursor.execute("select * from schedule")
        reminders = cursor.fetchall()
        cursor.close()
        for i in range(len(reminders)):
            if time_now[0] == reminders[i][2]:
                if time_now[1] == reminders[i][3]:
                    message = ""
                    remind = reminders[i]
                    message += f'ID:{remind[0]} Дата:{remind[2]},{remind[3]},\n{remind[4]}\n'
                    bot.send_message(remind[1], message)
        sleep(58)


if __name__ == '__main__':
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    scheduler_thread = Thread(target=run_scheduler)
    scheduler_thread.start()
    app.run(host='0.0.0.0', port=8443)

