from flask import Flask, render_template, request, redirect, url_for
import yfinance as yf
import sqlite3

app = Flask(__name__)

# Initialize the database
def init_db():
    with sqlite3.connect('stocks.db') as conn:
        cursor = conn.cursor()
        # Create table for groups
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
        ''')
        # Create table for stocks
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT UNIQUE,
                note TEXT,
                group_id INTEGER,
                FOREIGN KEY (group_id) REFERENCES groups (id)
            )
        ''')
        conn.commit()

# Fetch stock data for a list of tickers
def fetch_stock_data(tickers):
    """
    Fetch stock data for a list of tickers.
    Returns a list of dictionaries containing stock details.
    """
    stocks_info = []
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            stocks_info.append({
                'ticker': ticker,
                'name': info.get('shortName', 'N/A'),
                'price': info.get('currentPrice', 'N/A'),
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

# Home route: Redirect to the Default group
@app.route('/')
def index():
    return redirect(url_for('group', group_name='Default'))

# Route to display stocks for a specific group
@app.route('/group/<group_name>')
def group(group_name):
    with sqlite3.connect('stocks.db') as conn:
        cursor = conn.cursor()

        # Fetch all group names
        cursor.execute('SELECT name FROM groups')
        groups = [row[0] for row in cursor.fetchall()]

        # Fetch stocks for the selected group
        cursor.execute('''
            SELECT stocks.id, stocks.ticker, stocks.note
            FROM stocks
            JOIN groups ON stocks.group_id = groups.id
            WHERE groups.name = ?
        ''', (group_name,))
        stocks = cursor.fetchall()

    # Fetch stock data for the group's tickers
    tickers = [stock[1] for stock in stocks]
    stock_data = fetch_stock_data(tickers)

    # Combine stock data with notes
    for stock in stock_data:
        for db_stock in stocks:
            if db_stock[1] == stock['ticker']:
                stock['id'] = db_stock[0]
                stock['note'] = db_stock[2]

    return render_template('group.html', groups=groups, stocks=stock_data, selected_group=group_name)

# Route to add a new stock to a group
@app.route('/add_stock', methods=['POST'])
def add_stock():
    ticker = request.form['ticker'].strip().upper()
    note = request.form['note'].strip()
    group_name = request.form['group_name'].strip()

    with sqlite3.connect('stocks.db') as conn:
        cursor = conn.cursor()

        # Get the group_id for the selected group
        cursor.execute('SELECT id FROM groups WHERE name = ?', (group_name,))
        group_id = cursor.fetchone()
        if not group_id:
            return redirect(url_for('group', group_name='Default'))  # Safety fallback

        group_id = group_id[0]

        try:
            # Insert the stock into the stocks table
            cursor.execute(
                'INSERT INTO stocks (ticker, note, group_id) VALUES (?, ?, ?)',
                (ticker, note, group_id)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            pass  # Ignore duplicate tickers

    return redirect(url_for('group', group_name=group_name))

# Route to edit a stock's note
@app.route('/edit_note/<int:stock_id>', methods=['POST'])
def edit_note(stock_id):
    new_note = request.form['note'].strip()
    group_name = request.form['group_name']

    with sqlite3.connect('stocks.db') as conn:
        cursor = conn.cursor()
        # Update the note for the stock
        cursor.execute('UPDATE stocks SET note = ? WHERE id = ?', (new_note, stock_id))
        conn.commit()

    return redirect(url_for('group', group_name=group_name))

# Route to create a new group
@app.route('/add_group', methods=['POST'])
def add_group():
    group_name = request.form['group_name'].strip()
    
    # Avoid creating empty or duplicate groups
    if not group_name:
        return redirect(url_for('index'))

    with sqlite3.connect('stocks.db') as conn:
        cursor = conn.cursor()
        try:
            # Insert the group into the groups table
            cursor.execute('INSERT INTO groups (name) VALUES (?)', (group_name,))
            conn.commit()
        except sqlite3.IntegrityError:
            pass  # Ignore duplicate groups

    return redirect(url_for('group', group_name=group_name))

# Route to delete a stock
@app.route('/delete_stock/<int:stock_id>', methods=['POST'])
def delete_stock(stock_id):
    with sqlite3.connect('stocks.db') as conn:
        cursor = conn.cursor()
        # Get the group name of the stock before deleting
        cursor.execute('''
            SELECT groups.name
            FROM stocks
            JOIN groups ON stocks.group_id = groups.id
            WHERE stocks.id = ?
        ''', (stock_id,))
        result = cursor.fetchone()
        group_name = result[0] if result else 'Default'

        # Delete the stock
        cursor.execute('DELETE FROM stocks WHERE id = ?', (stock_id,))
        conn.commit()

    return redirect(url_for('group', group_name=group_name))

# Route to delete a group
@app.route('/delete_group/<group_name>', methods=['POST'])
def delete_group(group_name):
    with sqlite3.connect('stocks.db') as conn:
        cursor = conn.cursor()
        # Delete all stocks in the group
        cursor.execute('''
            DELETE FROM stocks
            WHERE group_id = (SELECT id FROM groups WHERE name = ?)
        ''', (group_name,))
        # Delete the group itself
        cursor.execute('DELETE FROM groups WHERE name = ?', (group_name,))
        conn.commit()

    return redirect(url_for('index'))

# Route to edit a group's name
@app.route('/edit_group/<group_name>', methods=['POST'])
def edit_group(group_name):
    new_group_name = request.form['new_group_name'].strip()

    # Avoid empty group names or duplicates
    if not new_group_name or new_group_name == group_name:
        return redirect(url_for('group', group_name=group_name))

    with sqlite3.connect('stocks.db') as conn:
        cursor = conn.cursor()
        # Update the group name
        cursor.execute('UPDATE groups SET name = ? WHERE name = ?', (new_group_name, group_name))
        conn.commit()

    return redirect(url_for('group', group_name=new_group_name))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)

