# 📦 SQL Table Creation GUI

A **Python desktop app for MySQL, built for people who don't know SQL.** Connect through a form, create tables and enter data using plain-English forms, and answer questions across multiple tables — joins, filters, totals/averages — entirely with dropdowns and checkboxes. No SQL vocabulary is required anywhere in the core workflow. An optional "Advanced (SQL)" tab exists separately for anyone who *does* know SQL and wants to write it directly.

## 🌟 Features

- **Connection screen**: enter host/port/user/password/database at runtime — no credentials stored in source code
- **Live schema browser**: sidebar tree of tables and columns (with primary keys flagged), refreshes as you make changes
- **Visual table creation**: plain-English field types ("Whole number", "Text (short)", "Yes / No", "Date", …) instead of SQL type names, with checkboxes for "Unique ID", "Required", "No duplicates", "Auto-number"
- **Guided data entry**: pick a table, fill in a form generated from its real fields, stage several rows, then save them all at once
- **Ask Questions (visual query builder)**: pick a starting table, bring in related tables by matching columns (joins), tick the fields you want to see, apply a calculation (Count/Total/Average/Min/Max), filter rows with plain-English conditions ("contains", "is greater than", "is empty", …), sort by what you're showing, and limit the row count — all through dropdowns and checkboxes, never by typing SQL
- **Save as a Reusable View**: turn any built question into a named, saved view that then shows up as a regular table you can pick from in future questions — the no-SQL equivalent of a CTE, with zero SQL knowledge required
- **Results grid**: sortable columns, row counts, and one-click CSV export
- **Advanced (SQL) tab — optional**: a free-form SQL editor for CTEs, subqueries, unions, and multi-statement scripts, clearly marked as only for users who already know SQL; nothing in the rest of the app requires it

## 🛠️ Tech Stack

- **Language**: Python 3.x
- **GUI Framework**: Tkinter (`ttk` themed widgets)
- **Database**: MySQL
- **Libraries**: `mysql-connector-python`

## 📋 Prerequisites

- Python 3.x installed
- MySQL Server installed and running
- Install dependencies:
  ```bash
  pip install -r requirements.txt
  ```

## 🚀 Installation

```bash
git clone https://github.com/HardhikTottempudi/SQL-table-creation-GUI.git
cd SQL-table-creation-GUI
pip install -r requirements.txt
python sql_app.py
```

No source edits are needed — enter your connection details in the app's **1. Connect** tab.

## 💡 How to Use

### 1. Connect
Enter host / port / user / password / database and click **Connect**. The schema sidebar populates automatically.

### 2. Create a table
Name the table, add fields (name, plain-English type, and Unique ID/Required/No duplicates/Auto-number flags), then click **Create Table**. A read-only preview shows what will happen, but you never need to read or edit it.

### 3. Add data
Choose a table (its real fields are fetched from MySQL), fill in the values, click **+ Add This Row** for each row, then **Save All Rows**.

### 4. Ask questions (joins, filters, totals — no SQL)
Go to **4. Ask Questions**:
1. Pick a starting table.
2. Optionally bring in related tables — pick the table, how to match it (e.g. `customers.id` to `orders.customer_id`), and whether to keep only matches or all rows from one side.
3. Tick the fields to show; give any field a calculation (Total, Average, Count, …) to summarize it instead of listing every row.
4. Optionally add conditions ("Where `name` contains `a`", "Where `price` is greater than `100`"), sort by one of the fields you're showing, and cap the number of rows.
5. Click **Get Results**.

To reuse a question later (or build a follow-up question on top of it), click **Save as a Reusable View...** and give it a name — it then appears as a regular table everywhere in the app.

### 5. Advanced (SQL) — optional
Only needed if you already know SQL: free-form editor for `WITH` CTEs, subqueries, `UNION`, multi-statement scripts. Everything else in the app works without it.

## 🔒 Safety Notes

- Table/column/view names are validated against a strict identifier pattern and quoted with backticks before being used in generated SQL.
- All typed values (inserts and filter values) are sent as parameterized query arguments, never string-concatenated, so entered data can't break out into SQL.
- The optional Advanced (SQL) tab lets you run arbitrary SQL you write yourself — the same care you'd apply to any SQL client applies there.

## 📊 Supported Field Types (Create Table dropdown)

Text (short), Text (long), Whole number, Decimal number, Yes / No, Date, Date & Time — or "Other (advanced)..." to type any custom MySQL type directly.

## 🔮 Possible Future Enhancements

- Foreign key definition in the Create Table tab
- ALTER TABLE support
- CSV/Excel import into the Add Data tab
- Multiple sort keys in Ask Questions
- Multi-connection profiles

## 📝 License

This project is open source and available for educational purposes.

## 👤 Author

**Hardhik Tottempudi**
- GitHub: [@HardhikTottempudi](https://github.com/HardhikTottempudi)

---

*This project showcases practical database management and GUI development skills for rapid prototyping.*
