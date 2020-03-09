import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")

most_common_passwords = [
    "123456",
    "123456789",
    "qwerty",
    "password",
    "1234567",
    "12345678",
    "12345",
    "iloveyou",
    "1111111",
    "123123"
]

@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    shares = []
    share = db.execute("SELECT symbol, SUM(shares) as total_shares FROM transactions WHERE user_id = :user_id GROUP BY symbol HAVING SUM(shares) > 0", user_id=session["user_id"])
    total = 0
    for share in share:
        quote = lookup(share["symbol"])
        value = quote["price"] * share["total_shares"]
        row ={"symbol":share["symbol"],
            "name": quote["name"],
            "shares": share["total_shares"],
            "price": quote["price"],
            "total": value}
        shares.append(row)
        total = total + value
    cash = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])[0]["cash"]
    total = total + cash
    return render_template("index.html", shares = shares, cash = cash, total = total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        quote = lookup(symbol)
        if quote == None:
            return apology("symbol does not exist", 400)
        shares = request.form.get("shares")
        if not shares:
            return apology("you need to specify a number of shares", 400)
        else:
            shares = int(shares)
            if shares < 1:
                return apology("you cannot buy less than 1 share", 400)
        cash = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])[0]["cash"]
        total = quote["price"] * float(shares)
        if total > cash:
            return apology("insuficient funds", 400)
        else:
            db.execute("INSERT INTO transactions (user_id, symbol, shares, quote) VALUES (:user_id, :symbol, :shares, :quote)", user_id = session["user_id"], symbol = symbol, shares = shares, quote = quote["price"])
            db.execute("UPDATE users SET cash = cash - :price WHERE id = :user_id", price = total, user_id = session["user_id"])
            flash("Bought!")
            return redirect("/") 
    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    trans_dicts = []
    transactions = db.execute("SELECT * FROM transactions WHERE user_id = :user_id", user_id = session["user_id"])
    for transaction in transactions:
        row = {
            "symbol": transaction["symbol"],
            "shares": transaction["shares"],
            "price": transaction["quote"],
            "datetime": transaction["date_time"]
        }
        trans_dicts.append(row)
    return render_template("history.html", transactions = trans_dicts)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        quote = lookup(request.form.get("symbol"))
        if quote == None:
            return apology("symbol does not exist", 400)
        else:
            return render_template("quoted.html", quote=quote)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    if request.method == "POST":
        if not request.form.get("username"):
            return apology("must provide a username", 400)
        elif not request.form.get("password"):
            return apology("must provide a password", 400)
        elif request.form.get("password") in most_common_passwords:
            return apology("password not allowed because it belongs to most common passwords (according to wikipedia 2019)", 400)
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("password and confirmation must match", 400)
        else:
            password_hash = generate_password_hash(request.form.get("password"))
            new_user = db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)", username=request.form.get("username"), hash=password_hash)
            if not new_user:
                return apology("username already exists", 400)

            session["user_id"] = new_user
            flash("Registered!")
            return redirect("/")

    else:
        return render_template("register.html")



@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        if not symbol:
            return apology("you have to select a symbol", 400)
        quote = lookup(symbol)
        if quote == None:
            return apology("symbol does not exist", 400)
        total_shares = db.execute("SELECT SUM(shares) as total_shares FROM transactions WHERE user_id = :user_id AND symbol = :symbol", user_id = session["user_id"], symbol = symbol)[0]["total_shares"]
        if not total_shares:
            return apology("you do not own any shares of this company", 400)
        shares = request.form.get("shares")
        if not shares:
            return apology("you need to specify a number of shares", 400)
        else:
            shares = int(shares)
            if shares < 1:
                return apology("you cannot buy less than 1 share", 400)
            elif shares > total_shares:
                return apology("you cannot sell more shares than you own", 400)
            else:
                total = quote["price"] * float(shares)
                db.execute("INSERT INTO transactions (user_id, symbol, shares, quote) VALUES (:user_id, :symbol, :shares, :quote)", user_id = session["user_id"], symbol = symbol, shares = - shares, quote = quote["price"])
                db.execute("UPDATE users SET cash = cash + :price WHERE id = :user_id", price = total, user_id = session["user_id"])
                flash("Sold!")
                return redirect("/")
    else:
        shares= []
        owned  = db.execute("SELECT symbol, SUM(shares) as total_shares FROM transactions WHERE user_id = :user_id GROUP BY symbol HAVING total_shares > 0", user_id = session["user_id"])
        for share in owned:
            row = {"symbol": share["symbol"],
                "shares": share["total_shares"]}
            shares.append(row)
        return render_template("sell.html", owned = shares)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
