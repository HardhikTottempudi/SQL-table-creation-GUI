# 📦 SQL Table Creation GUI

An intuitive **Python GUI application** that simplifies MySQL table creation and data insertion through a user-friendly interface. Perfect for rapid database prototyping and learning SQL fundamentals.

## 🌟 Features

- **Visual Table Creation**: Create MySQL tables without writing SQL code
- **Dynamic Column Definition**: Add unlimited columns with custom names and data types
- **Flexible Data Types**: Support for VARCHAR, INT, and other MySQL data types
- **Batch Data Insertion**: Insert multiple rows of data through the GUI
- **Real-time Validation**: Input validation before database operations
- **User-Friendly Interface**: Built with Tkinter for cross-platform compatibility

## 🛠️ Tech Stack

- **Language**: Python 3.x
- **GUI Framework**: Tkinter
- **Database**: MySQL
- **Libraries**:
  - `mysql-connector-python` - Database connectivity
  - `tkinter` - GUI components

## 📋 Prerequisites

- Python 3.x installed
- MySQL Server installed and running
- Required Python packages:
  ```bash
  pip install mysql-connector-python
  ```

## 🚀 Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/HardhikTottempudi/SQL-table-creation-GUI.git
   cd SQL-table-creation-GUI
   ```

2. **Configure database connection**
   
   Open `sql_app.py` and update the connection settings:
   ```python
   db = mysql.connector.connect(
     host="localhost",
     user="root",
     password="YOUR_PASSWORD",      # Update this
     database="YOUR_DATABASE_NAME"  # Update this
   )
   ```

3. **Run the application**
   ```bash
   python sql_app.py
   ```

## 💡 How to Use

### Creating a Table

1. **Enter Table Name**: Provide a name for your new table
2. **Specify Columns**: Enter the number of columns needed
3. **Define Schema**: 
   - Enter each column name
   - Specify data type (e.g., `VARCHAR(50)`, `INT`, `DATE`)
4. **Add Rows**: Enter the number of rows to insert
5. **Input Data**: Fill in the data for each cell
6. **Execute**: Click the final button to create the table and insert data

### Example Workflow

```
Table Name: students
Columns: 3
  - Column 1: name, VARCHAR(50)
  - Column 2: age, INT
  - Column 3: grade, VARCHAR(2)
Rows: 2
  - Row 1: John Doe, 20, A
  - Row 2: Jane Smith, 22, B
```

## 📊 Supported Data Types

- `VARCHAR(n)` - Variable character strings
- `INT` - Integer numbers
- `FLOAT` / `DOUBLE` - Decimal numbers
- `DATE` - Date values
- `TEXT` - Large text fields
- And all standard MySQL data types

## 🎯 Key Features for Hiring Managers

- **Database Management**: Demonstrates understanding of SQL and relational databases
- **GUI Development**: Shows proficiency in creating intuitive user interfaces
- **Dynamic Programming**: Handles variable inputs and generates SQL dynamically
- **Data Validation**: Implements type checking and input sanitization
- **Problem-Solving**: Abstracts complex SQL operations into simple user actions

## 🔧 Technical Highlights

- **Dynamic SQL Generation**: Programmatically constructs CREATE TABLE and INSERT statements
- **Type Handling**: Automatic detection and conversion of data types
- **GUI State Management**: Manages complex multi-step user workflows
- **Error Prevention**: Input validation before database operations

## 🔮 Future Enhancements

- Add table modification (ALTER TABLE) functionality
- Support for primary keys and foreign keys
- Data import from CSV/Excel files
- Table preview before creation
- Export table structure as SQL script
- Support for constraints (NOT NULL, UNIQUE, etc.)
- Visual schema designer

## 📝 Troubleshooting

**Connection Errors**:
- Verify MySQL server is running
- Check credentials in the code
- Ensure the database exists

**Data Type Errors**:
- Use proper MySQL syntax for data types
- VARCHAR requires a length: `VARCHAR(50)`

**GUI Issues**:
- Ensure all required fields are filled
- Follow the workflow sequence: name → columns → rows → data

## 📚 Learning Outcomes

This project demonstrates:
- SQL table creation and data manipulation
- Python GUI development with Tkinter
- Database connectivity and operations
- User input handling and validation
- Dynamic code generation

## 📝 License

This project is open source and available for educational purposes.

## 👤 Author

**Hardhik Tottempudi**
- GitHub: [@HardhikTottempudi](https://github.com/HardhikTottempudi)
- Portfolio: [hardhiktottempudi.com](https://hardhiktottempudi.com/)

---

*This project showcases practical database management and GUI development skills for rapid prototyping.*
