from Constants import Settings, Local, Method
import json
import xlwings as xw
from os.path import join
from xlwings import Sheet
from typing import Union
from datetime import datetime
from database import DataBase


class utils:

    @staticmethod
    def log(msg: str, category: str = "", e: str = "\n"):

        log_st = ""
        write = False
        match category:
            case 'debug':
                if Settings.DEBUG:
                    write = True
                    log_st += f"[DEBUG]: {msg}"
            case 'system':
                if Settings.SYSTEM:
                    write = True
                    log_st += f"[SYSTEM]: {msg}"
            case 'error':
                write = True
                log_st += f"{100*'-'}\n[ERROR]: {msg}\n{100*'-'}\n"
            case 'db':
                write = True
                log_st += f"[DataBase]: {msg}"
            case '':
                write = True
                log_st += f'{msg}'
            case 'warning':
                write = True
                log_st += f"\n<[WARNING]>: {msg}\n"
            case other:
                utils.log(msg="Key error in function 'temp'", category='error')

        if write:
            f = open("Log_file.txt", 'a', encoding="utf-8")
            f.write(log_st + "\n")
            f.close()
            print(log_st, end=e)

        if category == "error":
            exit()
        # if category == 'warning':
        #     utils.warning_halt()

    @staticmethod
    def validate_formats():
        utils.log(f"Formats are not being validated...", "warning")

    @staticmethod
    def name_he(name: str):
        try:
            i = name[::-1].index(' ')
            j = len(name) - i
            return name[:j][::-1] + " " + name[j:]
        except ValueError:
            return name

    @staticmethod
    def heb_conversion(name: str) -> str:
        """
        Convert strings containing mixed characters (hebrew and english) to a string
        suited for printing.
        """
        def wrapper_hc(lst) -> str:
            if lst == []:
                return ""
            
            if utils.has_hebrew(lst[0]):
                return wrapper_hc(lst[1:]) + lst[0][::-1] + " "
            return lst[0] + " " + wrapper_hc(lst[1:])

        return wrapper_hc(name.split())

    @staticmethod
    def has_hebrew(string):
        """
        returns True if a string has any hebrew characters in it
        and False otherwise.
        """
        import re
        return bool(re.search(r'[\u0590-\u05FF]', string))

    @staticmethod
    def warning_halt():

        def is_valid(x: str) -> bool:
            if not x.isnumeric():
                return False
            x = int(x)
            if not isinstance(x, int):
                return False
            if x not in [1, 2]:
                return False
            return True

        print("------ [HALT] ------")
        st = "There might be a problem, what do you want to do?\n1 -> Continue\n2 -> Stop and debug"
        print(st)
        while True:
            x = input()
            if not is_valid(x):
                print("Bad input, Try again...")
                continue
            match int(x):
                case 1:
                    break  # Continue
                case 2:
                    exit()
                case _:
                    print("This should not happen"); input("stopped.")

    @staticmethod
    def generate_html(spendings,
                      earnings,
                      monthly_balance: int,
                      end_month_balance: int,
                      gas_stats):
        import bs4
        from datetime import datetime
        # load the file
        with open("source\html\Base_template.html") as inf:
            txt = inf.read()
        soup = bs4.BeautifulSoup(txt)

        sub_titles_div = soup.new_tag('div')

        balance_h2 = soup.new_tag('h2')
        balance_h2.string = f'Balance: {monthly_balance}'

        temp_h2 = soup.new_tag('h2')
        temp_h2.string = f"Balance at month's end: {end_month_balance}"

        sub_titles_div.append(balance_h2)
        sub_titles_div.append(temp_h2)

        sub_titles_div.attrs['style'] = 'text-align: center;'

        soup.body.insert(2, sub_titles_div)

        # ----------
        div = soup.new_tag('div')
        div['class'] = 'container_img'

        img = soup.new_tag('img')
        img['src'] = 'C:/Users/ofeks/OneDrive/Work/Projects/Personal/BankProject/Card_Distribution.png'

        div.append(img)
        soup.body.insert(5, div)
        # ----------
        div = soup.new_tag('div')
        div['class'] = 'container'
        table = soup.new_tag("div")
        table['class'] = 'list'
        div.append(table)
        table2 = soup.new_tag("div")
        table2['class'] = 'list'
        div.append(table2)

        soup.body.insert(6, div)

        for item in sorted(spendings, key=lambda x: x[-1]):
            row = soup.new_tag("div")
            row['class'] = 'num'
            row['data-value'] = f"{item[3]}₪"   # Amount

            st = f"{item[1]}"   # Name
            cell = soup.new_tag("h3")
            cell.string = st
            row.append(cell)

            cell = soup.new_tag("p")
            cell['class'] = 'date'
            d = datetime.strptime(f"{item[-1]}", "%Y-%m-%d %H:%M:%S").strftime('%A %d')
            cell.string = f"{d}"
            row.append(cell)

            cell = soup.new_tag("p")
            cell['class'] = 'cat'
            # d = datetime.strptime(f"{item[-1]}", "%Y-%m-%d %H:%M:%S").strftime('%A %d')
            cell.string = f"{item[4]}" # Category
            row.append(cell)
            
            table.append(row)

        # ----------
        # ----------
        for item in sorted(earnings, key=lambda x: x[-1]):
            row = soup.new_tag("div")
            row['class'] = 'num'
            row['data-value'] = f"{item[1]}₪"  # Amount

            st = f"{item[0]}"
            cell = soup.new_tag("h3")
            cell.string = st
            row.append(cell)

            cell = soup.new_tag("p")
            cell['class'] = 'date'
            d = datetime.strptime(f"{item[-1]}", "%Y-%m-%d %H:%M:%S").strftime('%A %d')
            cell.string = f"{d}"
            row.append(cell)

            cell = soup.new_tag("p")
            cell['class'] = 'cat'
            cell.string = f"{item[-2]}"
            row.append(cell)

            table2.append(row)

        # ----------
        div = soup.new_tag("div")
        div["class"] = 'gas-info'
        title = soup.new_tag("h3")
        title.string = "Gas info"
        div.append(title)

        table = soup.new_tag("table")

        # for key, value in gas_stats.items():
        #     tr = soup.new_tag("tr")
        #     td1 = soup.new_tag("td")
        #     td1.string = key + ":"
        #     td2 = soup.new_tag("td")
        #     td2.string = str(value)
        #     td2['style'] = 'padding-left: 15px;'
        #     tr.append(td1)
        #     tr.append(td2)
        #     table.append(tr)

        div.append(table)

        outer_div = soup.new_tag("div")
        outer_div['class'] = 'container_img'
        outer_div.append(div)

        img_tag = soup.new_tag("img")
        img_tag['src'] = Local.GAS_GRAPH
        outer_div.append(img_tag)

        soup.body.append(outer_div)

        div_tag = soup.new_tag('div')
        div_tag['class'] = 'container_img'

        img_tag = soup.new_tag("img")
        img_tag['src'] = Local.GAS_MONTHLY
        div_tag.append(img_tag)

        soup.body.append(div_tag)

        with open("source\html\output.html", "w", encoding='utf-8') as outf:
            outf.write(bs4.BeautifulSoup.prettify(soup))

    @staticmethod
    def template_menu(options: list[str], msg: str = "Choose one of the following:\n"):
        """
        
        """
        st = msg
        for idx, e in enumerate(options, start=0):
            st += f"\t{idx} -> {utils.heb_conversion(e)}\n"
        utils.log(st, 'system')

        while True:
            x = input()
            if not x.isnumeric():
                continue
            x = int(x)
            if x < 0 or x >= len(options):
                continue
            return x

    @staticmethod
    def handle_categories() -> str:
        """
        
        """
        #utils.log("Choose one of the existsing categories:")
        cat_lst = json.load(open(Local.CATE_JSON_PATH, encoding='utf-8'))
        options = cat_lst + ["Create a new category", "Skip"]
        res = utils.template_menu(options)
        if options[res] == "Create a new category":
            while True:
                cat = input("Insert a category name: ")
                utils.log("Are you sure?\n1-> Yes\n2-> No")
                x = input()
                if x == "1":
                    json.dump(cat_lst + [cat], open(Local.CATE_JSON_PATH, "w", encoding='utf-8'))
                    return cat
                else:
                    utils.log("Bad input, try again...", "system")
                    continue

        return options[res]

    @staticmethod
    def is_headers_valid(file_name: str, headers: list, initial_row: int) -> bool:
        '''
        The function validates the table headers in the file.
        The values of the headers and the initial row are given in the Constants.py.
        '''
        wb = xw.Book(join(Local.INPUT_FOLDER, file_name))
        sheet = wb.sheets[0]

        valid = True
        col = 0
        row = initial_row
        for name in headers:
            value = utils.cell(row, col, sheet)
            if not value == name:
                if col > 1:
                    utils.log(f"Header Validation Failed halfway: {value} != {name}", "warning")
                valid = False
                break
            col += 1
        if valid:
            if row != initial_row:
                utils.log(f"Headers were found at line {row}, Not in {initial_row} as specified.", "warning")
            initial_row = row
            return True
        utils.log(f"Header Validation Failed for {file_name}", "debug")
        return False

    @staticmethod
    def cell(row: int, col: int, sheet: Sheet) -> Union[str, None]:
        '''
        Returns the value of the cell with indexes [row, col]
        '''
        if row > 0 and col >= 0:
            return sheet[f'{chr(65 + col)}{row}'].value
        else:
            utils.log(f"Invalid indexes -> ({row}, {col})", "error")
            return ""

    @staticmethod
    def parse_Leumi_inner_cards(headers_count, table_skip, initial_row, initial_col, sheet, data, name):
        '''
        The parse function for InnerCreditFile updates the following fields:
        self.counter1: number of transactions in the first table
        self.counter2: number of transaction in the second table
        self.data: table1 and table2 data in a 2d array
        self.date: the date specified in the file
        '''
        COL_COUNT = len(headers_count)

        none_counter = 1 + table_skip  # Number of "None" fields in the file
        row_index = initial_row + 1    # The first data row

        table_row_counter = 0               # Counts the valid rows in each table (A file might have more than one table)
        total_counter = 0                   # The total valid Transations in the file
        initial_table_index = row_index     # The first row of data in a table

        curr_pos = utils.cell(row_index, initial_col, sheet)
        next_pos = utils.cell(row_index + 1, initial_col, sheet)

        def is_valid(value: Union[datetime, None, int, float, str]) -> bool:
            """
            The function returns False if the given values is invalid and True otherwise.
            valid values are one of the specified at the argument Typing.
            """
            if type(value) == datetime:
                return True
            if type(value) == int:
                return True
            if type(value) == float:
                return True
            if value is None:
                return False
            if value.isdigit():
                return True
            return False

        def check_digit(value: Union[datetime, None, int, str]) -> bool:
            """
            The function checks if the given value is a digit.
            It was made after figuring out the the read value can also be in datetime
            format which does not support the "isdigit()" function.
            """
            if type(value) == int:
                return True
            if type(value) == float:
                return True
            if type(value) == str:
                return value.isdigit()
            return False

        while none_counter > 0:
            # If the current row is invalid
            if not is_valid(curr_pos):
                none_counter -= 1
                # If the next row is valid ->
                # Than set the initial index of the next table
                if next_pos is not None and \
                   next_pos.isdigit():
                    initial_table_index = row_index + 1
            # If the current row is valid
            else:
                # Raise the counter for the current and total tables
                table_row_counter += 1
                total_counter += 1

                # Extract data (This might not be needed)
                row = sheet[row_index - 1: row_index, initial_col: COL_COUNT + initial_col].value
                data.append(row)

                # If the next row is invalid ->
                # Add the data about the current table to db
                # The second conditioning is for establishing between different cards in the table -
                # both current and next are number values but the card changes -> create a new table for it.
                if not is_valid(next_pos) or \
                   (check_digit(next_pos) and check_digit(curr_pos) and curr_pos != next_pos):
                    DataBase().insert_table_meta_data(name,
                                                      initial_table_index,
                                                      initial_col,
                                                      table_row_counter)
                    # Reset table info
                    table_row_counter = 0
                    initial_table_index = row_index + 1

            # iterate over to the next row
            row_index += 1
            curr_pos = next_pos
            next_pos = utils.cell(row_index + 1, initial_col, sheet)

        DataBase().insert_file(name,
                               "to implement",
                               "Auto Insertion",
                               "Not checked",
                               total_counter)

        return data
