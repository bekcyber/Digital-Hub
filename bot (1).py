import os
import sqlite3
import telebot

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

# =========================================================
# SOZLAMALAR
# =========================================================

TOKEN = "8839436278:AAFe_LPMB1VdGl6TfKPsG5uD9qcQNrk_7P4"

WEB_APP_URL = "https://cozy-gelato-2487b2.netlify.app"

PORT = int(os.environ.get("PORT", 5000))

UPLOAD_FOLDER = "uploads"
AVATAR_FOLDER = os.path.join(UPLOAD_FOLDER, "avatars")
POST_FOLDER = os.path.join(UPLOAD_FOLDER, "posts")

os.makedirs(AVATAR_FOLDER, exist_ok=True)
os.makedirs(POST_FOLDER, exist_ok=True)

DATABASE = "database.db"


# =========================================================
# TELEGRAM BOT
# =========================================================

bot = telebot.TeleBot(TOKEN)


# =========================================================
# FLASK SERVER
# =========================================================

app = Flask(__name__)
CORS(app)


# =========================================================
# DATABASE
# =========================================================

def get_db():

    db = sqlite3.connect(
        DATABASE,
        check_same_thread=False
    )

    db.row_factory = sqlite3.Row

    return db


def init_db():

    db = get_db()

    db.execute("""
        CREATE TABLE IF NOT EXISTS users (

            telegram_id INTEGER PRIMARY KEY,

            first_name TEXT DEFAULT '',

            last_name TEXT DEFAULT '',

            username TEXT DEFAULT '',

            age TEXT DEFAULT '',

            birth TEXT DEFAULT '',

            phone TEXT DEFAULT '',

            bio TEXT DEFAULT '',

            avatar TEXT DEFAULT '',

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS posts (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            telegram_id INTEGER NOT NULL,

            text TEXT DEFAULT '',

            image TEXT DEFAULT '',

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY(telegram_id)
            REFERENCES users(telegram_id)

        )
    """)

    db.commit()

    db.close()


# =========================================================
# USER DATABASEGA QO'SHISH
# =========================================================

def save_telegram_user(user):

    db = get_db()

    old = db.execute(
        "SELECT telegram_id FROM users WHERE telegram_id=?",
        (user.id,)
    ).fetchone()

    if old:

        db.execute("""
            UPDATE users
            SET
                first_name=?,
                last_name=?,
                username=?
            WHERE telegram_id=?
        """, (
            user.first_name or "",
            user.last_name or "",
            user.username or "",
            user.id
        ))

    else:

        db.execute("""
            INSERT INTO users
            (
                telegram_id,
                first_name,
                last_name,
                username
            )
            VALUES (?, ?, ?, ?)
        """, (
            user.id,
            user.first_name or "",
            user.last_name or "",
            user.username or ""
        ))

    db.commit()

    db.close()


# =========================================================
# USERNI JSONGA O'GIRISH
# =========================================================

def user_to_dict(user):

    return {
        "telegram_id": user["telegram_id"],
        "first_name": user["first_name"],
        "last_name": user["last_name"],
        "username": user["username"],
        "age": user["age"],
        "birth": user["birth"],
        "phone": user["phone"],
        "bio": user["bio"],
        "avatar_url": user["avatar"]
    }


# =========================================================
# START
# =========================================================

@bot.message_handler(commands=["start"])
def start(message):

    save_telegram_user(message.from_user)

    markup = telebot.types.ReplyKeyboardMarkup(
        resize_keyboard=True
    )

    web_button = telebot.types.KeyboardButton(
        text="🌐 Veb-ilovaga kirish",
        web_app=telebot.types.WebAppInfo(
            url=WEB_APP_URL
        )
    )

    services = telebot.types.KeyboardButton(
        "🛒 Xizmatlar"
    )

    profile = telebot.types.KeyboardButton(
        "👤 Mening profilim"
    )

    about = telebot.types.KeyboardButton(
        "ℹ️ Biz haqimizda"
    )

    help_button = telebot.types.KeyboardButton(
        "📞 Yordam / Aloqa"
    )

    markup.add(web_button)

    markup.add(
        services,
        profile
    )

    markup.add(
        about,
        help_button
    )

    name = message.from_user.first_name or "do‘st"

    text = f"""
Assalomu alaykum, {name}! 🌟

Yangi Mahalliy Xizmatlar platformasiga xush kelibsiz!

👇 Veb-ilovani ochish uchun tugmani bosing.
"""

    bot.send_message(
        message.chat.id,
        text,
        reply_markup=markup
    )


# =========================================================
# BOT TUGMALARI
# =========================================================

@bot.message_handler(
    func=lambda message: message.text == "🛒 Xizmatlar"
)
def services(message):

    bot.send_message(
        message.chat.id,
        "🛠 Xizmatlarni veb-ilovadan ko‘rishingiz mumkin."
    )


@bot.message_handler(
    func=lambda message: message.text == "👤 Mening profilim"
)
def profile(message):

    save_telegram_user(message.from_user)

    bot.send_message(
        message.chat.id,
        f"""
👤 Sizning profilingiz

Ism: {message.from_user.first_name or ''}
Familiya: {message.from_user.last_name or ''}
Username: @{message.from_user.username or 'yo‘q'}

Telegram ID:
{message.from_user.id}
"""
    )


@bot.message_handler(
    func=lambda message: message.text == "ℹ️ Biz haqimizda"
)
def about(message):

    bot.send_message(
        message.chat.id,
        """
✨ Biz yosh va innovatsion jamoamiz.

Maqsadimiz — foydalanuvchilarga
foydali raqamli xizmatlarni bir joyda taqdim qilish.
"""
    )


@bot.message_handler(
    func=lambda message: message.text == "📞 Yordam / Aloqa"
)
def help_user(message):

    bot.send_message(
        message.chat.id,
        "📞 Savol yoki taklif bo‘lsa, administrator bilan bog‘laning."
    )


# =========================================================
# REGISTER API
# =========================================================

@app.route("/api/register", methods=["POST"])
def api_register():

    data = request.get_json(silent=True) or {}

    init_data = data.get("initData", "")

    # Telegram WebAppdan userni olish
    telegram_user = None

    if init_data:

        try:

            user_part = init_data.split("user=", 1)[1]

            user_part = user_part.split("&", 1)[0]

            from urllib.parse import unquote

            import json

            telegram_user = json.loads(
                unquote(user_part)
            )

        except Exception:
            telegram_user = None

    if not telegram_user:

        return jsonify({
            "message": "Telegram foydalanuvchisi topilmadi."
        }), 400

    telegram_id = telegram_user.get("id")

    if not telegram_id:

        return jsonify({
            "message": "Telegram ID topilmadi."
        }), 400

    db = get_db()

    old = db.execute(
        "SELECT * FROM users WHERE telegram_id=?",
        (telegram_id,)
    ).fetchone()

    if old:

        db.execute("""
            UPDATE users
            SET
                first_name=?,
                last_name=?,
                username=?
            WHERE telegram_id=?
        """, (
            telegram_user.get("first_name", ""),
            telegram_user.get("last_name", ""),
            telegram_user.get("username", ""),
            telegram_id
        ))

    else:

        db.execute("""
            INSERT INTO users
            (
                telegram_id,
                first_name,
                last_name,
                username
            )
            VALUES (?, ?, ?, ?)
        """, (
            telegram_id,
            telegram_user.get("first_name", ""),
            telegram_user.get("last_name", ""),
            telegram_user.get("username", "")
        ))

    db.commit()

    user = db.execute(
        "SELECT * FROM users WHERE telegram_id=?",
        (telegram_id,)
    ).fetchone()

    db.close()

    return jsonify({
        "user": user_to_dict(user)
    })


# =========================================================
# BARCHA USERS
# =========================================================

@app.route("/api/users", methods=["GET"])
def get_users():

    db = get_db()

    users = db.execute("""
        SELECT *
        FROM users
        ORDER BY created_at DESC
    """).fetchall()

    db.close()

    return jsonify({
        "users": [
            user_to_dict(user)
            for user in users
        ]
    })


# =========================================================
# BITTA USER PROFILE
# =========================================================

@app.route(
    "/api/users/<int:telegram_id>",
    methods=["GET"]
)
def get_user(telegram_id):

    db = get_db()

    user = db.execute(
        "SELECT * FROM users WHERE telegram_id=?",
        (telegram_id,)
    ).fetchone()

    db.close()

    if not user:

        return jsonify({
            "message": "Foydalanuvchi topilmadi."
        }), 404

    return jsonify({
        "user": user_to_dict(user)
    })


# =========================================================
# PROFILE UPDATE
# =========================================================

@app.route("/api/profile", methods=["POST"])
def update_profile():

    init_data = request.form.get(
        "initData",
        ""
    )

    if not init_data:

        return jsonify({
            "message": "Telegram ma'lumotlari yo‘q."
        }), 400

    try:

        user_part = init_data.split(
            "user=",
            1
        )[1]

        user_part = user_part.split(
            "&",
            1
        )[0]

        from urllib.parse import unquote

        import json

        telegram_user = json.loads(
            unquote(user_part)
        )

        telegram_id = telegram_user["id"]

    except Exception:

        return jsonify({
            "message": "Telegram foydalanuvchisini aniqlab bo‘lmadi."
        }), 400


    first_name = request.form.get(
        "first_name",
        ""
    )

    last_name = request.form.get(
        "last_name",
        ""
    )

    age = request.form.get(
        "age",
        ""
    )

    birth = request.form.get(
        "birth",
        ""
    )

    phone = request.form.get(
        "phone",
        ""
    )

    bio = request.form.get(
        "bio",
        ""
    )


    db = get_db()


    old = db.execute(
        "SELECT avatar FROM users WHERE telegram_id=?",
        (telegram_id,)
    ).fetchone()


    avatar = old["avatar"] if old else ""


    file = request.files.get("avatar")


    if file and file.filename:

        filename = secure_filename(
            file.filename
        )

        filename = (
            str(telegram_id)
            + "_avatar_"
            + filename
        )

        path = os.path.join(
            AVATAR_FOLDER,
            filename
        )

        file.save(path)

        avatar = "/uploads/avatars/" + filename


    db.execute("""
        UPDATE users
        SET
            first_name=?,
            last_name=?,
            age=?,
            birth=?,
            phone=?,
            bio=?,
            avatar=?
        WHERE telegram_id=?
    """, (
        first_name,
        last_name,
        age,
        birth,
        phone,
        bio,
        avatar,
        telegram_id
    ))

    db.commit()


    user = db.execute(
        "SELECT * FROM users WHERE telegram_id=?",
        (telegram_id,)
    ).fetchone()

    db.close()


    return jsonify({
        "user": user_to_dict(user)
    })


# =========================================================
# POST YARATISH
# =========================================================

@app.route("/api/posts", methods=["POST"])
def create_post():

    init_data = request.form.get(
        "initData",
        ""
    )

    if not init_data:

        return jsonify({
            "message": "Telegram ma'lumotlari yo‘q."
        }), 400


    try:

        user_part = init_data.split(
            "user=",
            1
        )[1]

        user_part = user_part.split(
            "&",
            1
        )[0]

        from urllib.parse import unquote

        import json

        telegram_user = json.loads(
            unquote(user_part)
        )

        telegram_id = telegram_user["id"]

    except Exception:

        return jsonify({
            "message": "Telegram foydalanuvchisini aniqlab bo‘lmadi."
        }), 400


    text = request.form.get(
        "text",
        ""
    ).strip()


    image = request.files.get(
        "image"
    )


    if not text and not image:

        return jsonify({
            "message": "Postga matn yoki rasm qo‘shing."
        }), 400


    image_url = ""


    if image and image.filename:

        filename = secure_filename(
            image.filename
        )

        filename = (
            str(telegram_id)
            + "_post_"
            + str(abs(hash(filename)))
            + "_"
            + filename
        )

        path = os.path.join(
            POST_FOLDER,
            filename
        )

        image.save(path)

        image_url = "/uploads/posts/" + filename


    db = get_db()


    # User borligini tekshirish
    user = db.execute(
        "SELECT * FROM users WHERE telegram_id=?",
        (telegram_id,)
    ).fetchone()


    if not user:

        db.execute("""
            INSERT INTO users
            (
                telegram_id,
                first_name,
                last_name,
                username
            )
            VALUES (?, ?, ?, ?)
        """, (
            telegram_id,
            telegram_user.get("first_name", ""),
            telegram_user.get("last_name", ""),
            telegram_user.get("username", "")
        ))

        db.commit()


    cursor = db.execute("""
        INSERT INTO posts
        (
            telegram_id,
            text,
            image
        )
        VALUES (?, ?, ?)
    """, (
        telegram_id,
        text,
        image_url
    ))


    post_id = cursor.lastrowid

    db.commit()


    post = db.execute("""
        SELECT
            posts.*,
            users.first_name,
            users.last_name,
            users.username,
            users.avatar
        FROM posts

        JOIN users
        ON posts.telegram_id = users.telegram_id

        WHERE posts.id=?
    """, (
        post_id,
    )).fetchone()


    db.close()


    return jsonify({
        "post": {
            "id": post["id"],
            "text": post["text"],
            "image_url": post["image"],
            "created_at": post["created_at"],

            "author": {
                "telegram_id": post["telegram_id"],
                "first_name": post["first_name"],
                "last_name": post["last_name"],
                "username": post["username"],
                "avatar_url": post["avatar"]
            }
        }
    })


# =========================================================
# BARCHA POSTLAR
# =========================================================

@app.route("/api/posts", methods=["GET"])
def get_posts():

    db = get_db()

    posts = db.execute("""
        SELECT
            posts.*,

            users.first_name,
            users.last_name,
            users.username,
            users.avatar

        FROM posts

        JOIN users
        ON posts.telegram_id = users.telegram_id

        ORDER BY posts.id DESC
    """).fetchall()

    db.close()


    result = []


    for post in posts:

        result.append({

            "id": post["id"],

            "text": post["text"],

            "image_url": post["image"],

            "created_at": post["created_at"],

            "author": {

                "telegram_id":
                    post["telegram_id"],

                "first_name":
                    post["first_name"],

                "last_name":
                    post["last_name"],

                "username":
                    post["username"],

                "avatar_url":
                    post["avatar"]

            }

        })


    return jsonify({
        "posts": result
    })


# =========================================================
# UPLOADS
# =========================================================

@app.route(
    "/uploads/<path:filename>"
)
def uploads(filename):

    return send_from_directory(
        UPLOAD_FOLDER,
        filename
    )


# =========================================================
# SERVERNI ISHGA TUSHIRISH
# =========================================================

if __name__ == "__main__":

    init_db()

    print("================================")
    print("BOT + SERVER ISHLAYAPTI")
    print("================================")

    # Botni alohida threadda ishga tushirish
    import threading

    bot_thread = threading.Thread(
        target=bot.infinity_polling,
        daemon=True
    )

    bot_thread.start()


    app.run(
        host="0.0.0.0",
        port=PORT
          )
