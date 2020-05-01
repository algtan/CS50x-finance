import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

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


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    """HINT: Display a table with all of the current user's stocks, the number of shares of each, the current price of each stock, and the total value of each holding."""
    """HINT: Display the user's current cash balance."""

    # Query database for stocks in the user's portfolio
    port_rows = db.execute("SELECT * FROM portfolio WHERE user_id = :user_id ORDER BY symbol", user_id=session["user_id"])

    # Query database for user's current cash
    user_rows = db.execute("SELECT * FROM users WHERE id = :id", id=session["user_id"])

    # Calculate how much cash the user has
    cash = user_rows[0]["cash"]
    # Convert the cash amount into USD format
    cash_usd = usd(cash)

    # Initialize value to keep track of the total amount held in stocks
    stock_total = 0

    # Add stock price information to port_rows
    for port_row in port_rows:
        # Lookup current stock prices for user's portfolio
        stock = lookup(port_row["symbol"])
        # Add stock price to port_rows
        port_row["stock_price"] = usd(stock["price"])
        # Calculate the amount of money held in those stocks
        stock_amount = stock["price"] * port_row["shares"]
        # Add stock amount into port_rows
        port_row["amount"] = usd(stock_amount)
        # Add amount to user's total portfolio
        stock_total += stock_amount

    # Calculate the user's total portfolio in cash and stocks
    total = usd(cash + stock_total)

    return render_template("index.html", cash_usd=cash_usd, port_rows=port_rows, total=total)


@app.route("/add_cash", methods=["GET", "POST"])
@login_required
def add_cash():
    """Add additional cash to user's account"""

    if request.method == "POST":

        # Check how much cash the user has
        user_rows = db.execute("SELECT * FROM users WHERE id = :id",
                               id=session["user_id"])

        # Store the amount the user wants to add
        add_amount = float(request.form.get("add"))

        # Update the users table to reflect the amount of cash the user now has
        db.execute("UPDATE users SET cash=:cash WHERE id=:id", id=session["user_id"], cash=user_rows[0]["cash"] + add_amount)

        flash("Additional Cash Added to Your Account!")
        return redirect("/")

    else:
        return render_template("buy.html")


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    """HINT: When requested via GET, should display form to buy a stock."""
    """HINT: When form is submitted via POST, purchase the stock so long as the user can afford it."""

    if request.method == "POST":

        # Ensure a stock symbol was submitted
        if not request.form.get("symbol"):
            return apology("missing symbol", 400)

        elif not request.form.get("shares"):
            return apology("missing shares", 400)

        # store the number of shares the user would like to purchase
        num_shares = int(request.form.get("shares"))

        # Lookup symbol
        stock = lookup(request.form.get("symbol"))

        # Ensure stock symbol is valid
        if stock == None:
            return apology("invalid symbol", 400)

        # Check how much cash the user has
        user_rows = db.execute("SELECT * FROM users WHERE id = :id",
                               id=session["user_id"])

        cash = user_rows[0]["cash"]

        # Check if the user has enough cash to purchase the amount of shares for that particular stock
        if cash < stock["price"] * num_shares:
            return apology("can't afford", 400)

        # Insert the transaction into the transactions table
        db.execute("INSERT INTO transactions (user_id, symbol, trans_qty, trans_indiv_price, timestamp) VALUES (:user_id, :symbol, :trans_qty, :trans_indiv_price, :timestamp)",
                   user_id=session["user_id"], symbol=stock["symbol"], trans_qty=num_shares, trans_indiv_price=stock["price"], timestamp=datetime.now())

        # Calculate remaining cash
        remaining = cash - stock["price"]*num_shares

        # Update the users table to reflect the amount of cash the user now has
        db.execute("UPDATE users SET cash=:cash WHERE id=:id", id=session["user_id"], cash=remaining)

        # Update the portfolio table to reflect the user's portfolio

        # Query database if the user already owns the stock
        port_rows = db.execute("SELECT * FROM portfolio WHERE user_id = :user_id AND symbol = :symbol",
                               user_id=session["user_id"], symbol=stock["symbol"])

        # If the user doesn't already own that stock, create a new row
        if len(port_rows) == 0:
            db.execute("INSERT INTO portfolio (user_id, symbol, name, shares) VALUES (:user_id, :symbol, :name, :shares)",
                       user_id=session["user_id"], symbol=stock["symbol"], name=stock["name"], shares=num_shares)

        # If the user already owns the stock, update the existing row
        else:
            # Query database for count of existing shares
            count = port_rows[0]["shares"]
            db.execute("UPDATE portfolio SET shares=:shares", shares=count+num_shares)

        flash("Bought!")
        return redirect("/")

    else:
        return render_template("buy.html")

@app.route("/change_pw", methods=["GET", "POST"])
@login_required
def change_pw():
    """Change User's Password"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Get current user's information from users table
        rows = db.execute("SELECT * FROM users WHERE id=:id", id=session["user_id"])

        # Ensure current password was submitted
        if not request.form.get("current_pw"):
            return apology("must provide your current password", 403)

        # Ensure current password matches hash
        elif not check_password_hash(rows[0]["hash"], request.form.get("current_pw")):
            return apology("invalid password", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        elif request.form.get("password_again") != request.form.get("password"):
            return apology("passwords don't match", 400)

        # Update the user's password hash
        db.execute("UPDATE users SET hash=:hash WHERE id=:id", id=session["user_id"], hash=generate_password_hash(request.form.get("password")))

        # Redirect user to home page
        flash("Password Successfully Changed!")
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("password.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    """HINT: Display a table with a history of all transaction's, listing row by row every buy and every sell."""

     # Gather user's transactions
    trans_rows = db.execute("SELECT * FROM transactions WHERE user_id=:user_id ORDER BY timestamp DESC", user_id=session["user_id"])

    return render_template("history.html", trans_rows=trans_rows)


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

    """HINT: When requested via GET, should display form to request a stock quote."""
    """HINT: When form is submitted via POST, lookup the stock symbol by calling the lookup function, and display the results."""

    if request.method == "POST":

        # Ensure a stock symbol was submitted
        if not request.form.get("symbol"):
            return apology("missing symbol", 400)

        # Lookup symbol
        stock = lookup(request.form.get("symbol"))

        # Ensure stock symbol is valid
        if stock == None:
            return apology("invalid symbol", 400)

        return render_template("quoted.html", name=stock["name"], price=usd(stock["price"]), symbol=stock["symbol"])

    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    """HINT: When requested via GET, should display registration form"""
    """HINT: When form is submitted via POST, insert the new user into users table"""
    """HINT: Be sure to check for invalid inputs, and to hash the user's password"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        elif request.form.get("password_again") != request.form.get("password"):
            return apology("passwords don't match", 400)

        # Query database for username to see if it already exists
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # If username exists, tell the user that it is unavailable
        if len(rows) != 0:
            return apology("username is not available", 422)

        # Insert the username and password hash into the users table if the username is available
        db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)",
                   username=request.form.get("username"), hash=generate_password_hash(request.form.get("password")))

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    """HINT: When requested via GET, should display form to sell a stock."""
    """HINT: When form is submitted via POST, sell the specified number of shares of stock, and update the user's cash."""

    if request.method == "POST":
        # Check if the user entered a valid stock
        if not request.form.get("symbol"):
            return apology("missing symbol", 400)

        # Check if the user has entered a valid number
        elif not request.form.get("shares"):
            return apology("missing shares", 400)

        # Lookup symbol for the latest stock information
        stock = lookup(request.form.get("symbol"))

        # Store the number of shares the user would like to sell
        num_shares = int(request.form.get("shares"))

        # Check how many shares the user has of that particular stock
        port_rows = db.execute("SELECT * FROM portfolio WHERE user_id = :user_id AND symbol = :symbol",
                               user_id=session["user_id"], symbol=stock["symbol"])

        # Store the number of shares the user owns into a variable called count
        count = port_rows[0]["shares"]

        # If the user does not have enough shares, return an apology
        if count < num_shares:
            return apology("too many shares", 400)

        # Insert the transaction into the transactions table
        db.execute("INSERT INTO transactions (user_id, symbol, trans_qty, trans_indiv_price, timestamp) VALUES (:user_id, :symbol, :trans_qty, :trans_indiv_price, :timestamp)",
                   user_id=session["user_id"], symbol=stock["symbol"], trans_qty=-1*num_shares, trans_indiv_price=stock["price"], timestamp=datetime.now())

        # Calculate the new number of shares the user owns
        shares = count - num_shares

        # Update the portfolio table
        db.execute("UPDATE portfolio SET shares=:shares WHERE symbol=:symbol", shares=shares, symbol=stock["symbol"])

        # Delete the row if the number of shares now held is zero (0)
        if shares == 0:
            db.execute("DELETE FROM portfolio WHERE user_id=:user_id & shares=0", user_id=session["user_id"])

        # Check how much cash the user has
        user_rows = db.execute("SELECT * FROM users WHERE id = :id",
                               id=session["user_id"])

        cash = user_rows[0]["cash"]

        # Calculate the amount the user now has in cash
        new_cash = cash + stock["price"] * num_shares

        # Update the users table
        db.execute("UPDATE users SET cash=:cash WHERE id=:id", id=session["user_id"], cash=new_cash)

        flash("Sold!")
        return redirect("/")

    else:
        # Query database to see what stocks the user owns
        rows = db.execute("SELECT * FROM portfolio WHERE user_id = :user_id ORDER BY symbol",
                               user_id=session["user_id"])

        return render_template("sell.html", rows=rows)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
