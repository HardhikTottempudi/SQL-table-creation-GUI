
#import mysql connector
import mysql.connector


db = mysql.connector.connect(
  host="localhost",
  user="root",
  password="password for dbms",
  database="Your database name"
)

#SET UP
cu = db.cursor()


# import tkinter module
from tkinter import *
from tkinter.ttk import *
from tkinter import messagebox



Tk().geometry('700x500')


tab_names = Entry()
tab_names.grid(row=0,column=1)
tab_nameL = Label(text='Enter table name:')
tab_nameL.grid(row=0,column=0)
e1 = Entry()
e1.grid(row=1,column=1)
no_of_columnL = Label(text='Enter Number of column:')
no_of_columnL.grid(row=1,column=0)
e2 = Entry()
e2.grid(row=2,column=1)
no_of_rowL = Label(text='Enter Number of rows: ')
no_of_rowL.grid(row=2,column=0)
column_titles = []
column_type = []
column_values = []
temp_column_Val = []

def print_p(t,x,y):
    print_label = Label(text=t)
    print_label.place(x=x,y=y)

def print_g(t,r,c):
    l_grid = Label(text=t)
    l_grid.grid(row=r,column=c)

def label_l(text,x,y):
    l = Label(text=text)
    l.place(x=x, y=y)

def entry_e(name,x,y):
    name = Entry()
    name.place(x=x,y=y)

def create_e(e_n,x,y):
    e_n = Entry()
    e_n.place(x=x,y=y)
    temp_column_Val.append(e_n)

def show():
    print(column_values)
    print(column_titles)
    print(column_type)


def get_details():
    no_of_row = e2.get()
    no_of_columns = e1.get()
    no_of_column = int(no_of_columns)

    # Collecting column names and their corresponding type
    for title in range(no_of_column):
        print_p('Enter column title: ',0,125)
        col_til_val = Entry()
        col_til_val.place(x=170,y=125)
        print_p('Enter corresponding titles type:',0,150)
        type_e = Entry()
        type_e.place(x=170,y=150)


        def bla():
            column_titles.append(col_til_val.get())
            column_type.append(type_e.get())
            col_til_val.delete(0, END)
            col_til_val.insert(0, "")
            type_e.delete(0, END)
            type_e.insert(0, "")
            if len(column_titles) == no_of_column:
                messagebox.showinfo("showinfo", "ENTER DETAILS IN NEXT SECTION")
                print_p('Thank you for entering', 0, 190)
                def finish(h):
                    no_of_rows = e2.get()
                    no_of_row = int(no_of_rows)
                    no_of_columns = e1.get()
                    no_of_column = int(no_of_columns)

                    for i in range(1, no_of_row + 1):
                        for j in range(1, no_of_column + 1):
                            label_l('Enter ' + str(i) + ' row', 0, h)
                            create_e('xyz', 175, h)
                            h += 25

                            def bob():
                                for i in range(no_of_row * no_of_column):
                                    column_values.append(temp_column_Val[i].get())

                            ins_but = Button(text='Insert data',command=bob)
                            ins_but.place(x=400,y=290)

                #but = Button(text='press', command=lambda: click(300))
                #but.place(x=400, y=0)

                #x=Button(text='print',command=show)
                #x.place(x=400,y=285)

                finish_but = Button(text='ENTER ROW DETAILS',command=lambda: finish(250))
                finish_but.place(x=400, y=230)



        # Collecting Column titles and type
        but = Button(text='end sec',command=bla)
        but.place(x=400,y=200)





#Button for collecting details (column names,no of rows,no of column)
START_BUTTON = Button(text='START',width=10,command=get_details)
START_BUTTON.place(x=400,y=100)


#If type is integer than converting from input to int
for i in range(len(column_type)):
    if column_type[i] == 'int':
        column_values[i] = int(column_values[i])



def sql():
    tab_name = tab_names.get()
    no_of_columns = e1.get()
    no_of_rows = e2.get()
    no_of_column = int(no_of_columns)
    no_of_row = int(no_of_rows)
    create_tab = 'create table if not exists '+tab_name+' ( '

    for i in range(len(column_titles)):
        if column_titles[i] not in create_tab:
            create_tab += column_titles[i] + ' '
            create_tab += column_type[i] + ' ' + ','

    tab_f = list(create_tab)
    tab_f.pop()
    tab_f = ''.join(tab_f)
    tab_f += ')'
    cu.execute(tab_f)
    db.commit()

    # inserting values
    var = ['varchar']

    for ij in range(1, 51):
        var.append('varchar(' + str(ij) + ')')
    st_var = list(var)
    st_var = st_var.pop()
    st_var = ''.join(var)

    ins = 'insert into ' + tab_name + ' values'
    sym = ''
    for i in range(len(column_titles)):
        if column_type[i] in var:
            sym += '"%s",'
        else:
            sym += '%s,'
    sym1 = list(sym)
    sym1.pop()
    sym1 = ''.join(sym1)

    final_ins = ins+'('+sym1+')'
    print(final_ins)

    row_details = []
    s = 0
    e = 0
    for i in range(no_of_row):
        row_details.append(tuple(column_values[s:no_of_column + e]))  #####converting into tuple for example : [('12b', 99), (100, 'a')]
        s += no_of_column
        e += no_of_column

    n_l = []
    for i in range(no_of_row):
        n_l.append(final_ins %row_details[i])
        #cu.execute(final_ins %row_details[i])
        #db.commit()

    for ijk in n_l:
        cu.execute(ijk)
    db.commit()
sql_but = Button(text='create table',command=sql)
sql_but.place(x=400,y=350)


mainloop()
