from flask import Flask, render_template, request, redirect, url_for
import yfinance as yf
import sqlite3

app = Flask(__name__)

# Initialize the database
def init_db():
    with sqlite3.connect('stocks.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT,
                note TEXT,
                group_id INTEGER,
                FOREIGN KEY (group_id) REFERENCES groups (id)
            )
        ''')
        conn.commit()

# Fetch stock data for a list of tickers
def fetch_stock_data(tickers):
    stocks_info = []
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            stocks_info.append({
                'ticker': ticker,
                'name': info.get('shortName', 'N/A'),
                'price': info.get('currentPrice', info.get('regularMarketPrice', 'N/A')),
                'volume': info.get('regularMarketVolume', 'N/A'),
            })
        except Exception as e:
            print(f"Error fetching data for {ticker}: {e}")
            stocks_info.append({
                'ticker': ticker,
                'name': 'Error',
                'price': 'N/A',
                'volume': 'N/A',
            })
    return stocks_info

@app.route('/')
def index():
    return redirect(url_for('group', group_name='Default'))

@app.route('/group/<group_name>')
def group(group_name):
    warning_message = request.args.get('warning')  # Retrieve the warning from the query string

    with sqlite3.connect('stocks.db') as conn:
        cursor = conn.cursor()

        # Fetch all group names
        cursor.execute('SELECT name FROM groups')
        groups = [row[0] for row in cursor.fetchall()]

        # Fetch stocks for the selected group
        cursor.execute('''
            SELECT stocks.id, stocks.ticker, stocks.note, stocks.added_price
            FROM stocks
            JOIN groups ON stocks.group_id = groups.id
            WHERE groups.name = ?
        ''', (group_name,))
        stocks = cursor.fetchall()

        # Fetch stock data for the group's tickers
        tickers = [stock[1] for stock in stocks]
        stock_data = fetch_stock_data(tickers)

        # Combine stock data with notes, added price, and calculate percentage change
        for stock in stock_data:
            for db_stock in stocks:
                if db_stock[1] == stock['ticker']:
                    stock['id'] = db_stock[0]
                    stock['note'] = db_stock[2]
                    stock['added_price'] = db_stock[3]

                    # Calculate percentage change
                    if stock['price'] != 'N/A' and db_stock[3] is not None:
                        stock['percent_change'] = ((stock['price'] - db_stock[3]) / db_stock[3]) * 100
                    else:
                        stock['percent_change'] = 'N/A'

                    # Fetch other groups where this stock exists
                    cursor.execute('''
                        SELECT groups.name
                        FROM stocks
                        JOIN groups ON stocks.group_id = groups.id
                        WHERE stocks.ticker = ? AND groups.name != ?
                    ''', (stock['ticker'], group_name))
                    stock['other_groups'] = [row[0] for row in cursor.fetchall()]

    return render_template(
        'group.html',
        groups=groups,
        stocks=stock_data,
        selected_group=group_name,
        warning_message=warning_message
    )

@app.route('/add_stock', methods=['POST'])
def add_stock():
    ticker = request.form['ticker'].strip().upper()
    note = request.form['note'].strip()
    group_name = request.form['group_name'].strip()

    with sqlite3.connect('stocks.db') as conn:
        cursor = conn.cursor()

        # Fetch current stock price using Yahoo Finance
        try:
            stock = yf.Ticker(ticker)
            added_price = stock.info.get('currentPrice', stock.info.get('regularMarketPrice', None))
        except Exception as e:
            print(f"Error fetching price for {ticker}: {e}")
            added_price = None  # Handle cases where price isn't available

        # Check if the stock is already in another group
        cursor.execute('''
            SELECT groups.name 
            FROM stocks
            JOIN groups ON stocks.group_id = groups.id
            WHERE stocks.ticker = ?
        ''', (ticker,))
        existing_groups = cursor.fetchall()

        # Prepare warning message if stock exists in other groups
        warning_message = None
        if existing_groups:
            other_groups = [group[0] for group in existing_groups if group[0] != group_name]
            if other_groups:
                warning_message = f"Stock '{ticker}' is already present in the following group(s): {', '.join(other_groups)}"

        # Get the group_id for the selected group
        cursor.execute('SELECT id FROM groups WHERE name = ?', (group_name,))
        group_id = cursor.fetchone()
        if not group_id:
            return redirect(url_for('group', group_name='Default'))  # Safety fallback
        group_id = group_id[0]

        # Insert the stock into the database with the current price
        try:
            cursor.execute(
                'INSERT INTO stocks (ticker, note, group_id, added_price) VALUES (?, ?, ?, ?)',
                (ticker, note, group_id, added_price)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            pass  # Ignore duplicates in the same group

    # Redirect back to the group page and display the warning message
    return redirect(url_for('group', group_name=group_name) + (f"?warning={warning_message}" if warning_message else ""))

@app.route('/add_group', methods=['POST'])
def add_group():
    group_name = request.form['group_name'].strip()
    if not group_name:
        return redirect(url_for('index'))
    with sqlite3.connect('stocks.db') as conn:
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO groups (name) VALUES (?)', (group_name,))
            conn.commit()
        except sqlite3.IntegrityError:
            pass
    return redirect(url_for('group', group_name=group_name))

@app.route('/edit_note/<int:stock_id>', methods=['POST'])
def edit_note(stock_id):
    new_note = request.form['note']
    with sqlite3.connect('stocks.db') as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE stocks SET note = ? WHERE id = ?', (new_note, stock_id))
        conn.commit()
        result = cursor.execute('''
            SELECT groups.name FROM stocks
            JOIN groups ON stocks.group_id = groups.id
            WHERE stocks.id = ?
        ''', (stock_id,)).fetchone()
    group_name = result[0] if result else 'Default'
    return redirect(url_for('group', group_name=group_name))

@app.route('/delete_group/<group_name>', methods=['POST'])
def delete_group(group_name):
    with sqlite3.connect('stocks.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM stocks
            WHERE group_id = (SELECT id FROM groups WHERE name = ?)
        ''', (group_name,))
        cursor.execute('DELETE FROM groups WHERE name = ?', (group_name,))
        conn.commit()

    return redirect(url_for('index'))

@app.route('/edit_group/<group_name>', methods=['POST'])
def edit_group(group_name):
    new_group_name = request.form['new_group_name'].strip()
    if not new_group_name or new_group_name == group_name:
        return redirect(url_for('group', group_name=group_name))
    with sqlite3.connect('stocks.db') as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE groups SET name = ? WHERE name = ?', (new_group_name, group_name))
        conn.commit()
    return redirect(url_for('group', group_name=new_group_name))

@app.route('/delete_stock/<int:stock_id>', methods=['POST'])
def delete_stock(stock_id):
    with sqlite3.connect('stocks.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT groups.name
            FROM stocks
            JOIN groups ON stocks.group_id = groups.id
            WHERE stocks.id = ?
        ''', (stock_id,))
        result = cursor.fetchone()
        group_name = result[0] if result else 'Default'
        cursor.execute('DELETE FROM stocks WHERE id = ?', (stock_id,))
        conn.commit()
    return redirect(url_for('group', group_name=group_name))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)

