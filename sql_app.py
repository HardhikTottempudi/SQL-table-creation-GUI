"""SQL Table Creation GUI

A Tkinter desktop app for MySQL built for people who do NOT know SQL.
Connect through a form, browse a live schema tree, create tables and
enter data through plain-English forms, and answer questions across
multiple tables (joins, filters, totals) entirely with dropdowns and
checkboxes. A separate, clearly optional "Advanced (SQL)" tab exists
for anyone who does know SQL and wants to write it directly.
"""

import csv
import re
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

import mysql.connector
from mysql.connector import Error as MySQLError

IDENTIFIER_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

# Plain-English type names shown to the user, mapped to the real SQL type.
FRIENDLY_TYPES = {
    'Text (short)': 'VARCHAR(255)',
    'Text (long)': 'TEXT',
    'Whole number': 'INT',
    'Decimal number': 'DECIMAL(10,2)',
    'Yes / No': 'BOOLEAN',
    'Date': 'DATE',
    'Date & Time': 'DATETIME',
    'Other (advanced)...': None,
}
FRIENDLY_TYPE_LABELS = list(FRIENDLY_TYPES.keys())

# Plain-English join descriptions mapped to real SQL join keywords.
FRIENDLY_JOINS = {
    'Only matching rows in both': 'INNER JOIN',
    'All rows from the first table': 'LEFT JOIN',
    'All rows from the second table': 'RIGHT JOIN',
}
FRIENDLY_JOIN_LABELS = list(FRIENDLY_JOINS.keys())

# Plain-English filter operators mapped to how they're built into SQL.
FILTER_OPERATORS = [
    'is equal to', 'is not equal to', 'is greater than', 'is greater than or equal to',
    'is less than', 'is less than or equal to', 'contains', 'starts with', 'ends with',
    'is empty', 'is not empty',
]
OPERATORS_NEEDING_VALUE = {op for op in FILTER_OPERATORS if op not in ('is empty', 'is not empty')}

AND_OR = ['AND', 'OR']

AGG_FUNCS = {
    '(just show the value)': None,
    'Count': 'COUNT',
    'Total (Sum)': 'SUM',
    'Average': 'AVG',
    'Smallest (Min)': 'MIN',
    'Largest (Max)': 'MAX',
}
AGG_LABELS = list(AGG_FUNCS.keys())

FONT_UI = ('Segoe UI', 10)
FONT_UI_BOLD = ('Segoe UI', 10, 'bold')
FONT_MONO = ('Consolas', 10)

COLOR_BG = '#f4f6f9'
COLOR_PANEL = '#ffffff'
COLOR_ACCENT = '#2f6fed'
COLOR_ACCENT_DARK = '#2454bd'
COLOR_TEXT = '#1f2937'
COLOR_MUTED = '#6b7280'
COLOR_BORDER = '#d9dee6'
COLOR_OK = '#1a7f37'
COLOR_ERR = '#c0392b'


def split_sql_statements(sql_text):
    """Split a script into individual statements on ';', ignoring semicolons
    inside single/double/backtick-quoted sections. Empty statements dropped."""
    statements = []
    buf = []
    quote_char = None
    for ch in sql_text:
        if quote_char:
            buf.append(ch)
            if ch == quote_char:
                quote_char = None
            continue
        if ch in ("'", '"', '`'):
            quote_char = ch
            buf.append(ch)
            continue
        if ch == ';':
            stmt = ''.join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
            continue
        buf.append(ch)
    tail = ''.join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def quote_ident(name):
    """Validate and backtick-quote a MySQL identifier (table/column name)."""
    name = (name or '').strip()
    if not IDENTIFIER_RE.match(name):
        raise ValueError(f'Invalid identifier: "{name}". Use letters, digits, underscore, not starting with a digit.')
    return f'`{name}`'


def build_filter_fragment(col_ref, operator, value):
    """Turn a plain-English filter (column, operator, value) into a SQL
    fragment plus its parameter(s), for a parameterized WHERE clause."""
    if operator == 'is equal to':
        return f'{col_ref} = %s', [value]
    if operator == 'is not equal to':
        return f'{col_ref} != %s', [value]
    if operator == 'is greater than':
        return f'{col_ref} > %s', [value]
    if operator == 'is greater than or equal to':
        return f'{col_ref} >= %s', [value]
    if operator == 'is less than':
        return f'{col_ref} < %s', [value]
    if operator == 'is less than or equal to':
        return f'{col_ref} <= %s', [value]
    if operator == 'contains':
        return f'{col_ref} LIKE %s', [f'%{value}%']
    if operator == 'starts with':
        return f'{col_ref} LIKE %s', [f'{value}%']
    if operator == 'ends with':
        return f'{col_ref} LIKE %s', [f'%{value}']
    if operator == 'is empty':
        return f"({col_ref} IS NULL OR {col_ref} = '')", []
    if operator == 'is not empty':
        return f"({col_ref} IS NOT NULL AND {col_ref} != '')", []
    raise ValueError(f'Unknown filter operator: {operator}')


def literal_for_view(value):
    """Best-effort literal formatting for embedding a user-typed filter value
    directly into a CREATE VIEW statement (MySQL doesn't support placeholder
    parameters inside view definitions)."""
    try:
        float(value)
        return value
    except (TypeError, ValueError):
        pass
    escaped = str(value).replace('\\', '\\\\').replace("'", "\\'")
    return f"'{escaped}'"


class VerticalScrolledFrame(ttk.Frame):
    """A frame that scrolls vertically; put widgets inside `.body`."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0, background=COLOR_BG)
        vsb = ttk.Scrollbar(self, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side='left', fill='both', expand=True)
        vsb.pack(side='right', fill='y')

        self.body = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=self.body, anchor='nw')

        def on_body_configure(_event):
            canvas.configure(scrollregion=canvas.bbox('all'))

        def on_canvas_configure(event):
            canvas.itemconfigure(window, width=event.width)

        self.body.bind('<Configure>', on_body_configure)
        canvas.bind('<Configure>', on_canvas_configure)

        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')

        canvas.bind('<Enter>', lambda e: canvas.bind_all('<MouseWheel>', on_mousewheel))
        canvas.bind('<Leave>', lambda e: canvas.unbind_all('<MouseWheel>'))


class DBManager:
    """Owns the single live MySQL connection and exposes safe helpers."""

    def __init__(self):
        self.conn = None

    def connect(self, host, port, user, password, database):
        self.disconnect()
        self.conn = mysql.connector.connect(
            host=host, port=int(port or 3306), user=user,
            password=password, database=database or None,
        )
        return self.conn

    def disconnect(self):
        if self.conn is not None:
            try:
                self.conn.close()
            except MySQLError:
                pass
            self.conn = None

    def is_connected(self):
        return self.conn is not None and self.conn.is_connected()

    def _require_connection(self):
        if not self.is_connected():
            raise RuntimeError('Not connected to a database. Use the Connection tab first.')

    def execute(self, query, params=None):
        """Run one statement. Returns (columns, rows) for SELECT-like queries,
        or (None, affected_row_count) otherwise."""
        self._require_connection()
        cursor = self.conn.cursor()
        try:
            cursor.execute(query, params)
            if cursor.description:
                columns = [d[0] for d in cursor.description]
                rows = cursor.fetchall()
                return columns, rows
            self.conn.commit()
            return None, cursor.rowcount
        except MySQLError:
            self.conn.rollback()
            raise
        finally:
            cursor.close()

    def execute_script(self, sql_text):
        """Run possibly multiple ';'-separated statements. Returns a list of
        (statement, columns, rows_or_count) tuples."""
        self._require_connection()
        cursor = self.conn.cursor()
        results = []
        try:
            for stmt in split_sql_statements(sql_text):
                cursor.execute(stmt)
                if cursor.description:
                    results.append((stmt, [d[0] for d in cursor.description], cursor.fetchall()))
                else:
                    results.append((stmt, None, cursor.rowcount))
            self.conn.commit()
        except MySQLError:
            self.conn.rollback()
            raise
        finally:
            cursor.close()
        return results

    def executemany(self, query, seq_params):
        self._require_connection()
        cursor = self.conn.cursor()
        try:
            cursor.executemany(query, seq_params)
            self.conn.commit()
            return cursor.rowcount
        except MySQLError:
            self.conn.rollback()
            raise
        finally:
            cursor.close()

    def get_tables(self):
        if not self.is_connected():
            return []
        cols, rows = self.execute('SHOW TABLES')
        return [r[0] for r in rows]

    def get_columns(self, table):
        """Returns list of dicts: name, type, is_nullable, key, extra."""
        self._require_connection()
        cols, rows = self.execute(f'SHOW COLUMNS FROM {quote_ident(table)}')
        out = []
        for r in rows:
            out.append({
                'name': r[0], 'type': r[1], 'null': r[2],
                'key': r[3], 'default': r[4], 'extra': r[5],
            })
        return out


def style_app(root):
    style = ttk.Style(root)
    try:
        style.theme_use('clam')
    except tk.TclError:
        pass

    root.configure(bg=COLOR_BG)
    style.configure('.', font=FONT_UI, background=COLOR_BG, foreground=COLOR_TEXT)
    style.configure('TFrame', background=COLOR_BG)
    style.configure('Panel.TFrame', background=COLOR_PANEL)
    style.configure('TLabel', background=COLOR_BG, foreground=COLOR_TEXT, font=FONT_UI)
    style.configure('Panel.TLabel', background=COLOR_PANEL, foreground=COLOR_TEXT, font=FONT_UI)
    style.configure('Header.TLabel', background=COLOR_BG, foreground=COLOR_TEXT, font=('Segoe UI', 13, 'bold'))
    style.configure('Muted.TLabel', background=COLOR_BG, foreground=COLOR_MUTED, font=FONT_UI)
    style.configure('Muted.Panel.TLabel', background=COLOR_PANEL, foreground=COLOR_MUTED, font=FONT_UI)
    style.configure('Status.TLabel', background=COLOR_BG, font=FONT_UI)

    style.configure('TNotebook', background=COLOR_BG, borderwidth=0)
    style.configure('TNotebook.Tab', font=FONT_UI, padding=(14, 8))
    style.map('TNotebook.Tab', background=[('selected', COLOR_PANEL)], foreground=[('selected', COLOR_ACCENT_DARK)])

    style.configure('TButton', font=FONT_UI, padding=(10, 6))
    style.configure('Accent.TButton', font=FONT_UI_BOLD, padding=(12, 7),
                     background=COLOR_ACCENT, foreground='white')
    style.map('Accent.TButton', background=[('active', COLOR_ACCENT_DARK)])
    style.configure('Danger.TButton', font=FONT_UI, padding=(10, 6))

    style.configure('TEntry', padding=4)
    style.configure('TCombobox', padding=4)
    style.configure('Treeview', font=FONT_UI, rowheight=24, background='white',
                     fieldbackground='white', bordercolor=COLOR_BORDER)
    style.configure('Treeview.Heading', font=FONT_UI_BOLD)
    style.configure('TLabelframe', background=COLOR_BG, font=FONT_UI_BOLD)
    style.configure('TLabelframe.Label', background=COLOR_BG, font=FONT_UI_BOLD, foreground=COLOR_TEXT)
    style.configure('TCheckbutton', background=COLOR_BG, font=FONT_UI)
    style.configure('Panel.TCheckbutton', background=COLOR_PANEL, font=FONT_UI)
    return style


class ResultsView(ttk.Frame):
    """Reusable results grid with status line and CSV export."""

    def __init__(self, parent):
        super().__init__(parent)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        bar = ttk.Frame(self)
        bar.grid(row=0, column=0, sticky='ew', pady=(0, 4))
        self.status_var = tk.StringVar(value='No results yet.')
        ttk.Label(bar, textvariable=self.status_var, style='Muted.TLabel').pack(side='left')
        ttk.Button(bar, text='Export CSV', command=self.export_csv).pack(side='right')

        tree_frame = ttk.Frame(self)
        tree_frame.grid(row=1, column=0, sticky='nsew')
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(tree_frame, show='headings')
        vsb = ttk.Scrollbar(tree_frame, orient='vertical', command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')

        self._columns = []
        self._rows = []

    def clear(self):
        self.tree.delete(*self.tree.get_children())
        self.tree['columns'] = []
        self._columns, self._rows = [], []

    def show_message(self, message):
        self.clear()
        self.status_var.set(message)

    def display(self, columns, rows, status=None):
        self.clear()
        self._columns, self._rows = columns, rows
        self.tree['columns'] = columns
        for c in columns:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=max(90, min(220, 12 * len(c))), anchor='w')
        for row in rows:
            self.tree.insert('', 'end', values=['' if v is None else v for v in row])
        self.status_var.set(status or f'{len(rows)} row(s).')

    def display_affected(self, count, verb='affected'):
        self.clear()
        self.status_var.set(f'{count} row(s) {verb}.')

    def export_csv(self):
        if not self._columns:
            messagebox.showinfo('Export CSV', 'No results to export.')
            return
        path = filedialog.asksaveasfilename(defaultextension='.csv',
                                             filetypes=[('CSV files', '*.csv')])
        if not path:
            return
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(self._columns)
            writer.writerows(self._rows)
        messagebox.showinfo('Export CSV', f'Saved to {path}')


class SchemaPanel(ttk.Frame):
    """Left sidebar: live list of tables and columns for the active connection."""

    def __init__(self, parent, db, on_change=None):
        super().__init__(parent, style='Panel.TFrame')
        self.db = db
        self.on_change = on_change
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, style='Panel.TFrame')
        header.grid(row=0, column=0, sticky='ew', padx=8, pady=(8, 4))
        ttk.Label(header, text='Schema', style='Panel.TLabel', font=FONT_UI_BOLD).pack(side='left')
        ttk.Button(header, text='Refresh', command=self.refresh).pack(side='right')

        self.tree = ttk.Treeview(self, show='tree')
        self.tree.grid(row=1, column=0, sticky='nsew', padx=8, pady=(0, 8))
        vsb = ttk.Scrollbar(self, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.grid(row=1, column=1, sticky='ns', pady=(0, 8))

        self.tree.bind('<<TreeviewOpen>>', self._on_open)

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        if not self.db.is_connected():
            self.tree.insert('', 'end', text='(not connected)')
            return
        try:
            for table in self.db.get_tables():
                node = self.tree.insert('', 'end', text=table, values=('table',))
                self.tree.insert(node, 'end', text='loading...')
        except MySQLError as e:
            self.tree.insert('', 'end', text=f'Error: {e}')
        if self.on_change:
            self.on_change()

    def _on_open(self, _event):
        node = self.tree.focus()
        children = self.tree.get_children(node)
        if len(children) == 1 and self.tree.item(children[0], 'text') == 'loading...':
            self.tree.delete(children[0])
            table = self.tree.item(node, 'text')
            try:
                for col in self.db.get_columns(table):
                    label = f"{col['name']}  ({col['type']})"
                    if col['key'] == 'PRI':
                        label += '  [PK]'
                    self.tree.insert(node, 'end', text=label)
            except MySQLError as e:
                self.tree.insert(node, 'end', text=f'Error: {e}')


class ConnectionTab(ttk.Frame):
    def __init__(self, parent, db, on_connect=None):
        super().__init__(parent)
        self.db = db
        self.on_connect = on_connect

        card = ttk.Frame(self, style='Panel.TFrame', padding=20)
        card.pack(padx=20, pady=20, anchor='n', fill='x')

        ttk.Label(card, text='Connect to MySQL', style='Panel.TLabel', font=('Segoe UI', 14, 'bold')).grid(
            row=0, column=0, columnspan=2, sticky='w', pady=(0, 14))

        fields = [
            ('Host', 'host', 'localhost'),
            ('Port', 'port', '3306'),
            ('User', 'user', 'root'),
            ('Password', 'password', ''),
            ('Database', 'database', ''),
        ]
        self.vars = {}
        for i, (label, key, default) in enumerate(fields, start=1):
            ttk.Label(card, text=label + ':', style='Panel.TLabel').grid(row=i, column=0, sticky='w', pady=4)
            var = tk.StringVar(value=default)
            show = '*' if key == 'password' else ''
            entry = ttk.Entry(card, textvariable=var, width=32, show=show)
            entry.grid(row=i, column=1, sticky='w', pady=4, padx=(8, 0))
            self.vars[key] = var

        btn_row = ttk.Frame(card, style='Panel.TFrame')
        btn_row.grid(row=len(fields) + 1, column=0, columnspan=2, sticky='w', pady=(14, 0))
        self.connect_btn = ttk.Button(btn_row, text='Connect', style='Accent.TButton', command=self.connect)
        self.connect_btn.pack(side='left')
        self.disconnect_btn = ttk.Button(btn_row, text='Disconnect', command=self.disconnect)
        self.disconnect_btn.pack(side='left', padx=(8, 0))

        self.status_var = tk.StringVar(value='Not connected.')
        ttk.Label(card, textvariable=self.status_var, style='Muted.Panel.TLabel').grid(
            row=len(fields) + 2, column=0, columnspan=2, sticky='w', pady=(10, 0))

    def connect(self):
        v = {k: var.get() for k, var in self.vars.items()}
        if not v['host'] or not v['user']:
            messagebox.showwarning('Connect', 'Host and User are required.')
            return
        try:
            self.db.connect(v['host'], v['port'], v['user'], v['password'], v['database'])
        except MySQLError as e:
            self.status_var.set(f'Connection failed: {e}')
            messagebox.showerror('Connection failed', str(e))
            return
        self.status_var.set(f"Connected to {v['database'] or '(no default db)'} at {v['host']}:{v['port']} as {v['user']}.")
        if self.on_connect:
            self.on_connect()

    def disconnect(self):
        self.db.disconnect()
        self.status_var.set('Not connected.')
        if self.on_connect:
            self.on_connect()


class ColumnRow:
    """One editable column definition inside the Create Table tab.

    Column type is chosen from a plain-English list (e.g. "Whole number")
    rather than a raw SQL type, so no SQL vocabulary is required. Picking
    "Other (advanced)..." reveals a free-text box for anyone who does know
    the SQL type name they want.
    """

    def __init__(self, parent, index, remove_callback):
        self.frame = ttk.Frame(parent, style='Panel.TFrame')
        self.frame.grid(row=index, column=0, sticky='ew', pady=2)
        for c, w in enumerate([3, 3, 2, 1, 1, 1, 1, 0]):
            self.frame.columnconfigure(c, weight=w)

        self.name_var = tk.StringVar()
        self.type_var = tk.StringVar(value=FRIENDLY_TYPE_LABELS[0])
        self.custom_type_var = tk.StringVar()
        self.pk_var = tk.BooleanVar()
        self.notnull_var = tk.BooleanVar()
        self.unique_var = tk.BooleanVar()
        self.autoinc_var = tk.BooleanVar()

        ttk.Entry(self.frame, textvariable=self.name_var, width=16).grid(row=0, column=0, sticky='ew', padx=2)
        type_combo = ttk.Combobox(self.frame, textvariable=self.type_var, values=FRIENDLY_TYPE_LABELS,
                                   width=16, state='readonly')
        type_combo.grid(row=0, column=1, sticky='ew', padx=2)
        self.custom_type_entry = ttk.Entry(self.frame, textvariable=self.custom_type_var, width=12)
        self.custom_type_entry.grid(row=0, column=2, sticky='ew', padx=2)
        self.custom_type_entry.grid_remove()

        def on_type_change(_event=None):
            if self.type_var.get() == 'Other (advanced)...':
                self.custom_type_entry.grid()
            else:
                self.custom_type_entry.grid_remove()

        type_combo.bind('<<ComboboxSelected>>', on_type_change)

        ttk.Checkbutton(self.frame, text='Unique ID', variable=self.pk_var, style='Panel.TCheckbutton').grid(row=0, column=3)
        ttk.Checkbutton(self.frame, text='Required', variable=self.notnull_var, style='Panel.TCheckbutton').grid(row=0, column=4)
        ttk.Checkbutton(self.frame, text='No duplicates', variable=self.unique_var, style='Panel.TCheckbutton').grid(row=0, column=5)
        ttk.Checkbutton(self.frame, text='Auto-number', variable=self.autoinc_var, style='Panel.TCheckbutton').grid(row=0, column=6)
        ttk.Button(self.frame, text='✕', width=3, command=lambda: remove_callback(self)).grid(row=0, column=7, padx=(4, 0))

    def destroy(self):
        self.frame.destroy()

    def to_sql(self):
        name = self.name_var.get().strip()
        friendly = self.type_var.get().strip()
        if not name or not friendly:
            return None
        if friendly == 'Other (advanced)...':
            col_type = self.custom_type_var.get().strip()
            if not col_type:
                return None
        else:
            col_type = FRIENDLY_TYPES[friendly]
        parts = [quote_ident(name), col_type]
        if self.notnull_var.get() or self.pk_var.get():
            parts.append('NOT NULL')
        if self.autoinc_var.get():
            parts.append('AUTO_INCREMENT')
        if self.unique_var.get():
            parts.append('UNIQUE')
        return ' '.join(parts), self.pk_var.get(), name


class CreateTableTab(ttk.Frame):
    def __init__(self, parent, db, on_change=None):
        super().__init__(parent)
        self.db = db
        self.on_change = on_change
        self.rows = []

        ttk.Label(self, text="What do you want to call this table?", style='Header.TLabel').pack(
            anchor='w', padx=16, pady=(16, 4))
        top = ttk.Frame(self)
        top.pack(fill='x', padx=16, pady=(0, 8))
        ttk.Label(top, text='Table name:').pack(side='left')
        self.table_name_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.table_name_var, width=28).pack(side='left', padx=(8, 0))

        cols_card = ttk.Frame(self, style='Panel.TFrame', padding=12)
        cols_card.pack(fill='both', expand=False, padx=16, pady=8)

        header = ttk.Frame(cols_card, style='Panel.TFrame')
        header.pack(fill='x')
        ttk.Label(header, text='What information will it store?', style='Panel.TLabel', font=FONT_UI_BOLD).pack(side='left')
        ttk.Button(header, text='+ Add a field', command=self.add_row).pack(side='right')

        self.rows_container = ttk.Frame(cols_card, style='Panel.TFrame')
        self.rows_container.pack(fill='x', pady=(8, 0))

        btns = ttk.Frame(self)
        btns.pack(fill='x', padx=16, pady=8)
        ttk.Button(btns, text='Preview', command=self.preview).pack(side='left')
        ttk.Button(btns, text='Create Table', style='Accent.TButton', command=self.create_table).pack(side='left', padx=(8, 0))

        ttk.Label(self, text='What this will do (for reference — you never need to edit this):').pack(anchor='w', padx=16)
        self.sql_text = tk.Text(self, height=6, font=FONT_MONO, wrap='word', state='disabled', background='#f0f2f5')
        self.sql_text.pack(fill='x', padx=16, pady=(2, 16))

        self.add_row()
        self.add_row()

    def add_row(self):
        row = ColumnRow(self.rows_container, len(self.rows), self.remove_row)
        self.rows.append(row)

    def remove_row(self, row):
        row.destroy()
        self.rows.remove(row)
        for i, r in enumerate(self.rows):
            r.frame.grid(row=i, column=0, sticky='ew', pady=2)

    def build_sql(self):
        table = self.table_name_var.get().strip()
        if not table:
            raise ValueError('Enter a table name.')
        table_q = quote_ident(table)
        col_defs, pk_cols = [], []
        for row in self.rows:
            result = row.to_sql()
            if result is None:
                continue
            col_sql, is_pk, name = result
            col_defs.append(col_sql)
            if is_pk:
                pk_cols.append(quote_ident(name))
        if not col_defs:
            raise ValueError('Add at least one column with a name and type.')
        if pk_cols:
            col_defs.append(f"PRIMARY KEY ({', '.join(pk_cols)})")
        body = ',\n  '.join(col_defs)
        return f'CREATE TABLE IF NOT EXISTS {table_q} (\n  {body}\n)'

    def _set_preview(self, text):
        self.sql_text.configure(state='normal')
        self.sql_text.delete('1.0', 'end')
        self.sql_text.insert('1.0', text)
        self.sql_text.configure(state='disabled')

    def preview(self):
        try:
            sql = self.build_sql()
        except ValueError as e:
            messagebox.showwarning('Preview', str(e))
            return
        self._set_preview(sql + ';')

    def create_table(self):
        try:
            sql = self.build_sql()
        except ValueError as e:
            messagebox.showwarning('Create Table', str(e))
            return
        self._set_preview(sql + ';')
        try:
            self.db.execute(sql)
        except (MySQLError, RuntimeError) as e:
            messagebox.showerror('Create Table failed', str(e))
            return
        messagebox.showinfo('Create Table', f'Table created (or already existed).')
        if self.on_change:
            self.on_change()


class InsertDataTab(ttk.Frame):
    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self.columns_meta = []
        self.field_vars = {}
        self.batch = []

        ttk.Label(self, text='Which table are you adding data to?', style='Header.TLabel').pack(
            anchor='w', padx=16, pady=(16, 4))
        top = ttk.Frame(self)
        top.pack(fill='x', padx=16, pady=(0, 8))
        ttk.Label(top, text='Table:').pack(side='left')
        self.table_var = tk.StringVar()
        self.table_combo = ttk.Combobox(top, textvariable=self.table_var, width=25, state='readonly')
        self.table_combo.pack(side='left', padx=(8, 0))
        self.table_combo.bind('<<ComboboxSelected>>', lambda e: self.load_columns())
        ttk.Button(top, text='Refresh Tables', command=self.refresh_tables).pack(side='left', padx=(8, 0))

        form_card = ttk.Frame(self, style='Panel.TFrame', padding=12)
        form_card.pack(fill='x', padx=16, pady=8)
        ttk.Label(form_card, text='Fill in the details for one row', style='Panel.TLabel', font=FONT_UI_BOLD).pack(anchor='w')
        ttk.Label(form_card, text='Leave a field blank to leave it empty.', style='Muted.Panel.TLabel').pack(anchor='w')
        self.form_frame = ttk.Frame(form_card, style='Panel.TFrame')
        self.form_frame.pack(fill='x', pady=(8, 0))

        btns = ttk.Frame(self)
        btns.pack(fill='x', padx=16, pady=8)
        ttk.Button(btns, text='+ Add This Row', command=self.add_to_batch).pack(side='left')
        ttk.Button(btns, text='Save All Rows', style='Accent.TButton', command=self.insert_batch).pack(side='left', padx=(8, 0))
        ttk.Button(btns, text='Clear', command=self.clear_batch).pack(side='left', padx=(8, 0))

        ttk.Label(self, text='Rows ready to save:').pack(anchor='w', padx=16)
        batch_frame = ttk.Frame(self)
        batch_frame.pack(fill='both', expand=True, padx=16, pady=(2, 16))
        batch_frame.columnconfigure(0, weight=1)
        batch_frame.rowconfigure(0, weight=1)
        self.batch_tree = ttk.Treeview(batch_frame, show='headings', height=8)
        vsb = ttk.Scrollbar(batch_frame, orient='vertical', command=self.batch_tree.yview)
        self.batch_tree.configure(yscrollcommand=vsb.set)
        self.batch_tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')

    def refresh_tables(self):
        tables = self.db.get_tables() if self.db.is_connected() else []
        self.table_combo['values'] = tables
        if tables and self.table_var.get() not in tables:
            self.table_var.set(tables[0])
        if self.table_var.get():
            self.load_columns()

    def load_columns(self):
        for w in self.form_frame.winfo_children():
            w.destroy()
        self.field_vars = {}
        table = self.table_var.get()
        if not table or not self.db.is_connected():
            return
        try:
            self.columns_meta = self.db.get_columns(table)
        except MySQLError as e:
            messagebox.showerror('Load columns failed', str(e))
            return
        for i, col in enumerate(self.columns_meta):
            label = col['name']
            if col['extra'] == 'auto_increment':
                label += '  (auto)'
            ttk.Label(self.form_frame, text=f"{label}:", style='Panel.TLabel').grid(row=i, column=0, sticky='w', pady=2)
            var = tk.StringVar()
            ttk.Entry(self.form_frame, textvariable=var, width=30).grid(row=i, column=1, sticky='w', padx=(8, 0), pady=2)
            self.field_vars[col['name']] = var

        self.batch_tree['columns'] = [c['name'] for c in self.columns_meta]
        for c in self.columns_meta:
            self.batch_tree.heading(c['name'], text=c['name'])
            self.batch_tree.column(c['name'], width=100)
        self.clear_batch()

    def add_to_batch(self):
        if not self.columns_meta:
            messagebox.showwarning('Add Row', 'Select a table first.')
            return
        values = []
        for col in self.columns_meta:
            raw = self.field_vars[col['name']].get()
            values.append(None if raw == '' else raw)
        self.batch.append(values)
        self.batch_tree.insert('', 'end', values=['' if v is None else v for v in values])
        for var in self.field_vars.values():
            var.set('')

    def clear_batch(self):
        self.batch = []
        self.batch_tree.delete(*self.batch_tree.get_children())

    def insert_batch(self):
        table = self.table_var.get()
        if not table:
            messagebox.showwarning('Insert Batch', 'Select a table first.')
            return
        if not self.batch:
            messagebox.showwarning('Insert Batch', 'No rows in the batch. Add rows first.')
            return
        col_names = [c['name'] for c in self.columns_meta]
        cols_sql = ', '.join(quote_ident(c) for c in col_names)
        placeholders = ', '.join(['%s'] * len(col_names))
        sql = f'INSERT INTO {quote_ident(table)} ({cols_sql}) VALUES ({placeholders})'
        try:
            count = self.db.executemany(sql, self.batch)
        except (MySQLError, RuntimeError) as e:
            messagebox.showerror('Insert failed', str(e))
            return
        messagebox.showinfo('Insert Batch', f'Inserted {count} row(s).')
        self.clear_batch()


class JoinRow:
    """One "also bring in this table, matched on these columns" row.
    Everything is chosen from dropdowns populated from the live schema —
    no SQL syntax is typed."""

    def __init__(self, parent, index, remove_callback, on_change_callback):
        self.on_change_callback = on_change_callback
        self.frame = ttk.Frame(parent, style='Panel.TFrame')
        self.frame.grid(row=index, column=0, sticky='ew', pady=3)

        self.table_var = tk.StringVar()
        self.join_type_var = tk.StringVar(value=FRIENDLY_JOIN_LABELS[0])
        self.left_table_var = tk.StringVar()
        self.left_col_var = tk.StringVar()
        self.right_col_var = tk.StringVar()

        r0 = ttk.Frame(self.frame, style='Panel.TFrame')
        r0.pack(fill='x')
        ttk.Label(r0, text='Also bring in:', style='Panel.TLabel').pack(side='left')
        self.table_combo = ttk.Combobox(r0, textvariable=self.table_var, width=16, state='readonly')
        self.table_combo.pack(side='left', padx=(6, 12))
        ttk.Label(r0, text='Keep:', style='Panel.TLabel').pack(side='left')
        self.join_combo = ttk.Combobox(r0, textvariable=self.join_type_var, values=FRIENDLY_JOIN_LABELS,
                                        width=26, state='readonly')
        self.join_combo.pack(side='left', padx=(6, 12))
        ttk.Button(r0, text='✕ Remove', command=lambda: remove_callback(self)).pack(side='right')

        r1 = ttk.Frame(self.frame, style='Panel.TFrame')
        r1.pack(fill='x', pady=(4, 0))
        ttk.Label(r1, text='Match', style='Panel.TLabel').pack(side='left')
        self.left_table_combo = ttk.Combobox(r1, textvariable=self.left_table_var, width=14, state='readonly')
        self.left_table_combo.pack(side='left', padx=(6, 4))
        self.left_col_combo = ttk.Combobox(r1, textvariable=self.left_col_var, width=14, state='readonly')
        self.left_col_combo.pack(side='left', padx=(0, 8))
        ttk.Label(r1, text='to', style='Panel.TLabel').pack(side='left')
        ttk.Label(r1, text='(selected table above)', style='Muted.Panel.TLabel').pack(side='left', padx=(8, 4))
        self.right_col_combo = ttk.Combobox(r1, textvariable=self.right_col_var, width=14, state='readonly')
        self.right_col_combo.pack(side='left', padx=(4, 0))

        for combo in (self.table_combo, self.join_combo, self.left_table_combo,
                      self.left_col_combo, self.right_col_combo):
            combo.bind('<<ComboboxSelected>>', lambda e: self.on_change_callback())

    def destroy(self):
        self.frame.destroy()

    def is_complete(self):
        return bool(self.table_var.get() and self.left_table_var.get()
                    and self.left_col_var.get() and self.right_col_var.get())

    def to_sql(self):
        if not self.is_complete():
            return None
        join_kw = FRIENDLY_JOINS[self.join_type_var.get()]
        table = quote_ident(self.table_var.get())
        left = f'{quote_ident(self.left_table_var.get())}.{quote_ident(self.left_col_var.get())}'
        right = f'{table}.{quote_ident(self.right_col_var.get())}'
        return f'{join_kw} {table} ON {left} = {right}'


class FilterRow:
    """One "column [operator] value" filter row, joined to the next by AND/OR."""

    def __init__(self, parent, index, remove_callback, on_change_callback, is_first):
        self.on_change_callback = on_change_callback
        self.frame = ttk.Frame(parent, style='Panel.TFrame')
        self.frame.grid(row=index, column=0, sticky='ew', pady=2)

        self.combinator_var = tk.StringVar(value='AND')
        self.table_var = tk.StringVar()
        self.col_var = tk.StringVar()
        self.operator_var = tk.StringVar(value=FILTER_OPERATORS[0])
        self.value_var = tk.StringVar()

        if is_first:
            ttk.Label(self.frame, text='Where', style='Panel.TLabel', width=6).pack(side='left')
        else:
            ttk.Combobox(self.frame, textvariable=self.combinator_var, values=AND_OR, width=5,
                         state='readonly').pack(side='left')

        self.table_combo = ttk.Combobox(self.frame, textvariable=self.table_var, width=13, state='readonly')
        self.table_combo.pack(side='left', padx=(6, 2))
        self.col_combo = ttk.Combobox(self.frame, textvariable=self.col_var, width=13, state='readonly')
        self.col_combo.pack(side='left', padx=2)
        self.op_combo = ttk.Combobox(self.frame, textvariable=self.operator_var, values=FILTER_OPERATORS,
                                      width=18, state='readonly')
        self.op_combo.pack(side='left', padx=2)
        self.value_entry = ttk.Entry(self.frame, textvariable=self.value_var, width=16)
        self.value_entry.pack(side='left', padx=2)
        ttk.Button(self.frame, text='✕', width=3, command=lambda: remove_callback(self)).pack(side='left', padx=(4, 0))

        self.table_combo.bind('<<ComboboxSelected>>', lambda e: self.on_change_callback())
        self.op_combo.bind('<<ComboboxSelected>>', lambda e: self._sync_value_state())
        self._sync_value_state()

    def _sync_value_state(self):
        needs_value = self.operator_var.get() in OPERATORS_NEEDING_VALUE
        self.value_entry.configure(state='normal' if needs_value else 'disabled')

    def destroy(self):
        self.frame.destroy()

    def is_complete(self):
        if not (self.table_var.get() and self.col_var.get() and self.operator_var.get()):
            return False
        if self.operator_var.get() in OPERATORS_NEEDING_VALUE and self.value_var.get() == '':
            return False
        return True

    def to_sql(self):
        if not self.is_complete():
            return None
        col_ref = f'{quote_ident(self.table_var.get())}.{quote_ident(self.col_var.get())}'
        fragment, params = build_filter_fragment(col_ref, self.operator_var.get(), self.value_var.get())
        return fragment, params


class QueryBuilderTab(ttk.Frame):
    """Answer questions across one or more tables using dropdowns and
    checkboxes only — no SQL is typed. Internally this still generates and
    runs real SQL (joins, WHERE, GROUP BY, aggregates); the generated SQL is
    shown read-only for anyone curious, but never needs to be edited."""

    def __init__(self, parent, db, get_tables_cb):
        super().__init__(parent)
        self.db = db
        self.get_tables_cb = get_tables_cb
        self.join_rows = []
        self.filter_rows = []
        self.column_picks = {}          # (table, col) -> {'var': BooleanVar, 'agg_var': StringVar}
        self._columns_cache = {}        # table -> [column names]

        scroller = VerticalScrolledFrame(self)
        scroller.pack(fill='both', expand=True)
        body = scroller.body

        # Step 1: main table
        step1 = ttk.Frame(body, style='Panel.TFrame', padding=12)
        step1.pack(fill='x', padx=16, pady=(16, 8))
        ttk.Label(step1, text='Step 1 — Which table do you want to start from?', style='Panel.TLabel',
                  font=FONT_UI_BOLD).pack(anchor='w')
        row1 = ttk.Frame(step1, style='Panel.TFrame')
        row1.pack(fill='x', pady=(6, 0))
        self.from_var = tk.StringVar()
        self.from_combo = ttk.Combobox(row1, textvariable=self.from_var, width=24, state='readonly')
        self.from_combo.pack(side='left')
        self.from_combo.bind('<<ComboboxSelected>>', lambda e: self.refresh_all())
        ttk.Button(row1, text='Refresh tables', command=self.refresh_tables).pack(side='left', padx=(8, 0))

        # Step 2: joins
        step2 = ttk.Frame(body, style='Panel.TFrame', padding=12)
        step2.pack(fill='x', padx=16, pady=8)
        header2 = ttk.Frame(step2, style='Panel.TFrame')
        header2.pack(fill='x')
        ttk.Label(header2, text='Step 2 — Bring in related tables (optional)', style='Panel.TLabel',
                  font=FONT_UI_BOLD).pack(side='left')
        ttk.Button(header2, text='+ Add related table', command=self.add_join).pack(side='right')
        self.joins_container = ttk.Frame(step2, style='Panel.TFrame')
        self.joins_container.pack(fill='x', pady=(8, 0))

        # Step 3: columns to show
        step3 = ttk.Frame(body, style='Panel.TFrame', padding=12)
        step3.pack(fill='x', padx=16, pady=8)
        ttk.Label(step3, text='Step 3 — What do you want to show?', style='Panel.TLabel',
                  font=FONT_UI_BOLD).pack(anchor='w')
        ttk.Label(step3, text="Tick the fields you want. Pick a calculation (like Total) to summarize a field instead of listing every row.",
                  style='Muted.Panel.TLabel', wraplength=760, justify='left').pack(anchor='w', pady=(2, 6))
        self.columns_container = ttk.Frame(step3, style='Panel.TFrame')
        self.columns_container.pack(fill='x')

        # Step 4: filters
        step4 = ttk.Frame(body, style='Panel.TFrame', padding=12)
        step4.pack(fill='x', padx=16, pady=8)
        header4 = ttk.Frame(step4, style='Panel.TFrame')
        header4.pack(fill='x')
        ttk.Label(header4, text='Step 4 — Only show rows that match (optional)', style='Panel.TLabel',
                  font=FONT_UI_BOLD).pack(side='left')
        ttk.Button(header4, text='+ Add condition', command=self.add_filter).pack(side='right')
        self.filters_container = ttk.Frame(step4, style='Panel.TFrame')
        self.filters_container.pack(fill='x', pady=(8, 0))

        # Step 5: sort + limit
        step5 = ttk.Frame(body, style='Panel.TFrame', padding=12)
        step5.pack(fill='x', padx=16, pady=8)
        ttk.Label(step5, text='Step 5 — Sort and limit (optional)', style='Panel.TLabel', font=FONT_UI_BOLD).pack(anchor='w')
        ttk.Label(step5, text='Sorting is based on the fields you chose to show in Step 3.',
                  style='Muted.Panel.TLabel').pack(anchor='w', pady=(2, 4))
        row5 = ttk.Frame(step5, style='Panel.TFrame')
        row5.pack(fill='x')
        ttk.Label(row5, text='Sort by:', style='Panel.TLabel').pack(side='left')
        self.sort_col_var = tk.StringVar(value='')
        self.sort_col_combo = ttk.Combobox(row5, textvariable=self.sort_col_var, width=26, state='readonly')
        self.sort_col_combo.pack(side='left', padx=(6, 12))
        self.sort_dir_var = tk.StringVar(value='Ascending (A-Z, low-high)')
        ttk.Combobox(row5, textvariable=self.sort_dir_var,
                     values=['Ascending (A-Z, low-high)', 'Descending (Z-A, high-low)'],
                     width=24, state='readonly').pack(side='left', padx=(0, 16))
        ttk.Label(row5, text='Show only the first', style='Panel.TLabel').pack(side='left')
        self.limit_var = tk.StringVar()
        ttk.Entry(row5, textvariable=self.limit_var, width=6).pack(side='left', padx=(6, 4))
        ttk.Label(row5, text='rows', style='Panel.TLabel').pack(side='left')
        self._sort_options_map = {}

        # Actions
        btns = ttk.Frame(body)
        btns.pack(fill='x', padx=16, pady=8)
        ttk.Button(btns, text='Show me the SQL', command=self.preview).pack(side='left')
        ttk.Button(btns, text='Get Results', style='Accent.TButton', command=self.run).pack(side='left', padx=(8, 0))
        ttk.Button(btns, text='Save as a Reusable View...', command=self.save_as_view).pack(side='left', padx=(8, 0))

        ttk.Label(body, text='What this will do (for reference — you never need to edit this):').pack(anchor='w', padx=16)
        self.sql_text = tk.Text(body, height=6, font=FONT_MONO, wrap='word', state='disabled', background='#f0f2f5')
        self.sql_text.pack(fill='x', padx=16, pady=(2, 8))

        self.results = ResultsView(body)
        self.results.pack(fill='both', expand=True, padx=16, pady=(0, 16))

    # -- schema-driven state -------------------------------------------------

    def tables_in_play(self):
        tables = []
        if self.from_var.get():
            tables.append(self.from_var.get())
        for jr in self.join_rows:
            t = jr.table_var.get()
            if t and t not in tables:
                tables.append(t)
        return tables

    def columns_of(self, table):
        if table not in self._columns_cache:
            try:
                self._columns_cache[table] = [c['name'] for c in self.db.get_columns(table)]
            except (MySQLError, RuntimeError):
                self._columns_cache[table] = []
        return self._columns_cache[table]

    def refresh_tables(self):
        self._columns_cache = {}
        tables = self.get_tables_cb()
        self.from_combo['values'] = tables
        if tables and self.from_var.get() not in tables:
            self.from_var.set(tables[0])
        self.refresh_all()

    def refresh_all(self):
        """Re-derive every dropdown's available options from the current
        schema and current selections. Called after any structural change."""
        self._columns_cache = {}
        all_tables = self.get_tables_cb()
        in_play = self.tables_in_play()

        # Join rows: table choices exclude tables already used by an earlier
        # join row or the FROM table; ON-left choices are tables that appear
        # earlier in the FROM/JOIN sequence.
        preceding = [self.from_var.get()] if self.from_var.get() else []
        for jr in self.join_rows:
            available_new_tables = [t for t in all_tables if t not in in_play or t == jr.table_var.get()]
            jr.table_combo['values'] = available_new_tables
            jr.left_table_combo['values'] = preceding
            if jr.left_table_var.get() not in preceding and preceding:
                jr.left_table_var.set(preceding[0])
            left_cols = self.columns_of(jr.left_table_var.get()) if jr.left_table_var.get() else []
            jr.left_col_combo['values'] = left_cols
            right_cols = self.columns_of(jr.table_var.get()) if jr.table_var.get() else []
            jr.right_col_combo['values'] = right_cols
            if jr.table_var.get():
                preceding = preceding + [jr.table_var.get()]

        self._rebuild_column_picker(in_play)

        for fr in self.filter_rows:
            fr.table_combo['values'] = in_play
            if fr.table_var.get() not in in_play and in_play:
                fr.table_var.set(in_play[0])
            fr.col_combo['values'] = self.columns_of(fr.table_var.get()) if fr.table_var.get() else []

        self._refresh_sort_options()

    def _output_options(self):
        """Returns (select_parts, group_by_parts, has_aggregate, options)
        where options is [(friendly label, ORDER-BY-safe reference), ...]
        matching exactly what Step 3 will put in the SELECT list — so
        sorting never references a column that isn't in the output."""
        from_table = self.from_var.get().strip()
        picked = [(t, c, info) for (t, c), info in self.column_picks.items() if info['var'].get()]
        has_aggregate = any(AGG_FUNCS[info['agg_var'].get()] for _, _, info in picked)

        select_parts, group_by_parts, options = [], [], []
        if picked:
            for table, col, info in picked:
                col_ref = f'{quote_ident(table)}.{quote_ident(col)}'
                agg_label = info['agg_var'].get()
                agg_sql = AGG_FUNCS[agg_label]
                if agg_sql:
                    alias = quote_ident(f'{agg_label.split()[0].lower()}_{table}_{col}')
                    select_parts.append(f'{agg_sql}({col_ref}) AS {alias}')
                    options.append((f'{agg_label} of {col} ({table})', alias))
                else:
                    alias = quote_ident(f'{table}_{col}')
                    select_parts.append(f'{col_ref} AS {alias}')
                    if has_aggregate:
                        group_by_parts.append(col_ref)
                    options.append((f'{col} ({table})', alias))
        elif from_table:
            cols = self.columns_of(from_table)
            select_parts = [f'{quote_ident(from_table)}.{quote_ident(c)}' for c in cols] or ['*']
            options = [(c, f'{quote_ident(from_table)}.{quote_ident(c)}') for c in cols]

        return select_parts, group_by_parts, has_aggregate, options

    def _refresh_sort_options(self):
        _, _, _, options = self._output_options()
        self._sort_options_map = dict(options)
        labels = [''] + [label for label, _ in options]
        self.sort_col_combo['values'] = labels
        if self.sort_col_var.get() not in labels:
            self.sort_col_var.set('')

    def _rebuild_column_picker(self, tables):
        old_picks = self.column_picks
        for w in self.columns_container.winfo_children():
            w.destroy()
        self.column_picks = {}
        for table in tables:
            section = ttk.LabelFrame(self.columns_container, text=table)
            section.pack(fill='x', pady=4)
            cols = self.columns_of(table)
            for i, col in enumerate(cols):
                row = ttk.Frame(section, style='Panel.TFrame')
                row.grid(row=i, column=0, sticky='w', padx=6, pady=1)
                key = (table, col)
                prev = old_picks.get(key)
                var = prev['var'] if prev else tk.BooleanVar()
                agg_var = prev['agg_var'] if prev else tk.StringVar(value=AGG_LABELS[0])
                ttk.Checkbutton(row, text=col, variable=var, style='Panel.TCheckbutton',
                                command=self._refresh_sort_options).pack(side='left')
                agg_combo = ttk.Combobox(row, textvariable=agg_var, values=AGG_LABELS, width=20, state='readonly')
                agg_combo.pack(side='left', padx=(6, 0))
                agg_combo.bind('<<ComboboxSelected>>', lambda e: self._refresh_sort_options())
                self.column_picks[key] = {'var': var, 'agg_var': agg_var}

    # -- row management -------------------------------------------------

    def add_join(self):
        row = JoinRow(self.joins_container, len(self.join_rows), self.remove_join, self.refresh_all)
        self.join_rows.append(row)
        self.refresh_all()

    def remove_join(self, row):
        row.destroy()
        self.join_rows.remove(row)
        for i, r in enumerate(self.join_rows):
            r.frame.grid(row=i, column=0, sticky='ew', pady=3)
        self.refresh_all()

    def add_filter(self):
        row = FilterRow(self.filters_container, len(self.filter_rows), self.remove_filter,
                         self.refresh_all, is_first=len(self.filter_rows) == 0)
        self.filter_rows.append(row)
        self.refresh_all()

    def remove_filter(self, row):
        row.destroy()
        self.filter_rows.remove(row)
        for i, r in enumerate(self.filter_rows):
            r.frame.grid(row=i, column=0, sticky='ew', pady=2)
        self.refresh_all()

    # -- SQL generation -------------------------------------------------

    def build_sql(self):
        from_table = self.from_var.get().strip()
        if not from_table:
            raise ValueError('Pick a table in Step 1.')

        select_parts, group_by_parts, _has_aggregate, options = self._output_options()
        if not select_parts:
            select_parts = ['*']

        sql = f'SELECT {", ".join(select_parts)}\nFROM {quote_ident(from_table)}'
        for jr in self.join_rows:
            j = jr.to_sql()
            if j:
                sql += f'\n{j}'

        params = []
        where_parts = []
        for i, fr in enumerate(self.filter_rows):
            result = fr.to_sql()
            if result is None:
                continue
            fragment, frag_params = result
            prefix = '' if i == 0 or not where_parts else f'{fr.combinator_var.get()} '
            where_parts.append(prefix + fragment)
            params.extend(frag_params)
        if where_parts:
            sql += '\nWHERE ' + ' '.join(where_parts)

        if group_by_parts:
            sql += '\nGROUP BY ' + ', '.join(group_by_parts)

        if self.sort_col_var.get():
            sort_ref = dict(options).get(self.sort_col_var.get())
            if sort_ref:
                direction = 'DESC' if self.sort_dir_var.get().startswith('Descending') else 'ASC'
                sql += f'\nORDER BY {sort_ref} {direction}'

        if self.limit_var.get().strip():
            if not self.limit_var.get().strip().isdigit():
                raise ValueError('The "first N rows" box must be a plain number.')
            sql += f'\nLIMIT {int(self.limit_var.get().strip())}'

        return sql, params

    def _set_preview(self, text):
        self.sql_text.configure(state='normal')
        self.sql_text.delete('1.0', 'end')
        self.sql_text.insert('1.0', text)
        self.sql_text.configure(state='disabled')

    def preview(self):
        try:
            sql, params = self.build_sql()
        except ValueError as e:
            messagebox.showwarning('Show me the SQL', str(e))
            return
        note = f'\n\n-- Your typed values are filled in safely when you click "Get Results": {params}' if params else ''
        self._set_preview(sql + ';' + note)

    def run(self):
        try:
            sql, params = self.build_sql()
        except ValueError as e:
            messagebox.showwarning('Get Results', str(e))
            return
        self._set_preview(sql + ';')
        try:
            columns, rows = self.db.execute(sql, params or None)
        except (MySQLError, RuntimeError) as e:
            messagebox.showerror('Could not get results', str(e))
            return
        if columns is None:
            self.results.display_affected(rows)
        else:
            self.results.display(columns, rows)

    def save_as_view(self):
        """The no-SQL equivalent of a CTE: save the current question as a
        named, reusable view that shows up as a regular table you can pick
        from in future questions and joins."""
        try:
            sql, params = self.build_sql()
        except ValueError as e:
            messagebox.showwarning('Save as a Reusable View', str(e))
            return
        name = simpledialog.askstring('Save as a Reusable View',
                                       'Name this view (letters, numbers, underscore):', parent=self)
        if not name:
            return
        try:
            view_name = quote_ident(name)
        except ValueError as e:
            messagebox.showwarning('Save as a Reusable View', str(e))
            return
        literal_sql = sql
        for param in params:
            literal_sql = literal_sql.replace('%s', literal_for_view(param), 1)
        try:
            self.db.execute(f'CREATE OR REPLACE VIEW {view_name} AS {literal_sql}')
        except (MySQLError, RuntimeError) as e:
            messagebox.showerror('Save as a Reusable View', str(e))
            return
        messagebox.showinfo('Save as a Reusable View', f'Saved. "{name}" now appears alongside your tables.')
        self.refresh_tables()


class SqlEditorTab(ttk.Frame):
    """Optional, for users who already know SQL: a free-form editor for
    CTEs (WITH ... AS (...)), subqueries, unions, multi-statement scripts,
    DDL/DML — anything, run directly. Everyone else can ignore this tab
    entirely; the other tabs never require typing SQL."""

    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db

        notice = ttk.Frame(self, style='Panel.TFrame', padding=10)
        notice.pack(fill='x', padx=16, pady=(16, 0))
        ttk.Label(notice, text="Optional — only for users who already know SQL.",
                  style='Panel.TLabel', font=FONT_UI_BOLD).pack(anchor='w')
        ttk.Label(notice, text="Everything else in this app (Create Table, Add Data, Ask Questions) works without writing any SQL.",
                  style='Muted.Panel.TLabel').pack(anchor='w')

        btns = ttk.Frame(self)
        btns.pack(fill='x', padx=16, pady=(12, 8))
        ttk.Button(btns, text='Run', style='Accent.TButton', command=self.run).pack(side='left')
        ttk.Button(btns, text='Clear', command=self.clear_editor).pack(side='left', padx=(8, 0))
        ttk.Button(btns, text='Load .sql', command=self.load_file).pack(side='left', padx=(8, 0))
        ttk.Button(btns, text='Save .sql', command=self.save_file).pack(side='left', padx=(8, 0))
        ttk.Label(btns, text='  Tip: separate multiple statements with ;', style='Muted.TLabel').pack(side='left')

        self.editor = tk.Text(self, height=10, font=FONT_MONO, wrap='none', undo=True)
        self.editor.pack(fill='both', expand=False, padx=16, pady=(0, 8))
        self.editor.insert('1.0',
            'WITH high_value AS (\n'
            '  SELECT customer_id, SUM(amount) AS total\n'
            '  FROM orders\n'
            '  GROUP BY customer_id\n'
            '  HAVING SUM(amount) > 1000\n'
            ')\n'
            'SELECT c.name, h.total\n'
            'FROM customers c\n'
            'JOIN high_value h ON h.customer_id = c.id\n'
            'ORDER BY h.total DESC;'
        )

        self.results = ResultsView(self)
        self.results.pack(fill='both', expand=True, padx=16, pady=(0, 16))

    def clear_editor(self):
        self.editor.delete('1.0', 'end')

    def load_file(self):
        path = filedialog.askopenfilename(filetypes=[('SQL files', '*.sql'), ('All files', '*.*')])
        if not path:
            return
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        self.editor.delete('1.0', 'end')
        self.editor.insert('1.0', content)

    def save_file(self):
        path = filedialog.asksaveasfilename(defaultextension='.sql', filetypes=[('SQL files', '*.sql')])
        if not path:
            return
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.editor.get('1.0', 'end'))

    def run(self):
        sql = self.editor.get('1.0', 'end').strip()
        if not sql:
            return
        try:
            results = self.db.execute_script(sql)
        except (MySQLError, RuntimeError) as e:
            messagebox.showerror('Execution failed', str(e))
            return
        if not results:
            self.results.show_message('No statements executed.')
            return
        stmt, columns, data = results[-1]
        if columns is None:
            self.results.display_affected(data)
        else:
            self.results.display(columns, data)
        if len(results) > 1:
            self.results.status_var.set(self.results.status_var.get() + f'  ({len(results)} statements executed; showing last result)')


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('SQL Table Creation GUI')
        self.geometry('1180x760')
        self.minsize(980, 620)

        style_app(self)
        self.db = DBManager()

        self._build_menu()
        self._build_layout()

    def _build_menu(self):
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label='Exit', command=self.destroy)
        menubar.add_cascade(label='File', menu=file_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label='About', command=lambda: messagebox.showinfo(
            'About',
            'SQL Table Creation GUI\n\n'
            'Built for people who don\'t know SQL: connect, create tables,\n'
            'add data, and ask questions across tables (joins, filters,\n'
            'totals) using only dropdowns and checkboxes.\n\n'
            'An optional "Advanced (SQL)" tab is available for anyone\n'
            'who already knows SQL.'))
        menubar.add_cascade(label='Help', menu=help_menu)
        self.config(menu=menubar)

    def _build_layout(self):
        paned = ttk.Panedwindow(self, orient='horizontal')
        paned.pack(fill='both', expand=True)

        self.schema_panel = SchemaPanel(paned, self.db)
        paned.add(self.schema_panel, weight=1)

        right = ttk.Frame(paned)
        paned.add(right, weight=4)

        notebook = ttk.Notebook(right)
        notebook.pack(fill='both', expand=True)

        self.connection_tab = ConnectionTab(notebook, self.db, on_connect=self._on_connection_change)
        self.create_table_tab = CreateTableTab(notebook, self.db, on_change=self._on_schema_change)
        self.insert_tab = InsertDataTab(notebook, self.db)
        self.query_tab = QueryBuilderTab(notebook, self.db, get_tables_cb=self.db.get_tables)
        self.sql_tab = SqlEditorTab(notebook, self.db)

        notebook.add(self.connection_tab, text='1. Connect')
        notebook.add(self.create_table_tab, text='2. Create Table')
        notebook.add(self.insert_tab, text='3. Add Data')
        notebook.add(self.query_tab, text='4. Ask Questions')
        notebook.add(self.sql_tab, text='Advanced (SQL) — optional')

        self.status_var = tk.StringVar(value='Not connected.')
        status_bar = ttk.Frame(self)
        status_bar.pack(fill='x', side='bottom')
        ttk.Label(status_bar, textvariable=self.status_var, style='Status.TLabel', padding=(10, 4)).pack(side='left')

    def _on_connection_change(self):
        connected = self.db.is_connected()
        self.status_var.set('Connected' if connected else 'Not connected.')
        self.schema_panel.refresh()
        self.insert_tab.refresh_tables()
        self.query_tab.refresh_tables()

    def _on_schema_change(self):
        self.schema_panel.refresh()
        self.insert_tab.refresh_tables()
        self.query_tab.refresh_tables()

    def destroy(self):
        self.db.disconnect()
        super().destroy()


if __name__ == '__main__':
    app = App()
    app.mainloop()
