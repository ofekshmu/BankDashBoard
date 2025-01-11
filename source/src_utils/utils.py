from Constants import Settings, Local
import json
from typing import Union
from datetime import datetime
import shutil
import os
import send2trash
from typing import Tuple
import pandas as pd
from tqdm import tqdm
from src_utils.ExcelReader import ExcelManager


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
                utils.log(msg=f"Key error in log function: got '{category}'", category='error')

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
            return wrapper_hc(lst[1:]) + " " +lst[0]


        if not utils.has_hebrew(name):
            return name

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
                    print("This should not happen")
                    input("stopped.")

    @staticmethod
    def generate_html(month_num,
                      spendings_df,
                      high_std_spendings,
                      earnings_df,
                      high_std_earnings,
                      monthly_balance: int,
                      cards_dict: dict,
                      data: dict):
        import bs4
        from datetime import datetime
        import calendar
        # load the file
        with open(r"source\html\Base_template.html") as inf:
            txt = inf.read()
        soup = bs4.BeautifulSoup(txt, features="html.parser")

        # Create the new div element
        new_div = soup.new_tag("div")
        new_div['class'] = "two alt-two"
        h1_tag = soup.new_tag("h1")
        h1_tag.string = "DashBoard"
        span_tag = soup.new_tag("span")
        span_tag.string = f"{calendar.month_name[month_num]}"
        h1_tag.append(span_tag)
        new_div.append(h1_tag)

        # Find the head tag and append the new div under it
        head_tag = soup.head
        head_tag.insert(0, new_div)


        sub_titles_div = soup.new_tag('div')

        balance_h2 = soup.new_tag('h1')
        balance_h2['class'] = "two alt-balance"
        balance_h2.string = f'Balance {monthly_balance:,.2f}₪'
        
        net_income = soup.new_tag('h1')
        net_income['class'] = "two alt-balance"
        net_income.string = f'Net Income: {data["net income"]:,.2f}₪'
        
        overall_net_income = soup.new_tag('h1')
        overall_net_income['class'] = "two alt-balance"
        overall_net_income.string = f'Overall Net Income: {data["overall net income"]:,.2f}₪'
        
        if data["net income"] >= 0:
            net_income['style'] = "color: #588157"
            overall_net_income['style'] = "color: #588157"
        else:
            overall_net_income['style'] = "color: #c1121f"

        head_tag.append(balance_h2)
        head_tag.append(net_income)
        head_tag.append(overall_net_income)

        sub_titles_div.attrs['style'] = 'text-align: center;'

        soup.body.insert(2, sub_titles_div)

        # ----------
        div = soup.new_tag('div')
        div['class'] = 'container_img'

        img = soup.new_tag('img')
        img['src'] = Local.CARD_DIST_PIE

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

        # if not cards_df.empty:
        #     div_element = soup.new_tag('div')
        #     card_status_table = bs4.BeautifulSoup(cards_df.to_html(index=False), 'html.parser')

        #     # Find all table cells in the DataFrame HTML
        #     cells = card_status_table.find_all('td')

        #     # Add conditional classes to cells based on their values
        #     for cell in cells:
        #         if cell.text.strip() == 'Verified':
        #             cell['class'] = 'Verified'
        #         elif cell.text.strip() == 'Not Verified':
        #             cell['class'] = 'Not verified'

        #     div_element.append(card_status_table)

        #     soup.body.insert(6, div_element)

        for _, item in spendings_df.sort_values(by='Date/Executed_Date', ascending=True).iterrows():

            row = soup.new_tag("div")
            row['class'] = 'num'
            d = datetime.strptime(f"{item['Date/Executed_Date']}", "%Y-%m-%d %H:%M:%S").strftime('%A_%d')
            row['data-value'] = f"{d}"   # Amount

            if item['TableName'] == 'CardTransactions':
                value = cards_dict[item['Ref/CardID']]
            else:
                value = cards_dict['Bank']
            
            # row['style'] = f"background-color: {value}"

            colored_box_div = soup.new_tag("div")
            colored_box_div['class'] = "color-box"
            colored_box_div['style'] = f"background-color: {value}"
            row.append(colored_box_div)


            # ---- replacing the name of the transaction with the description ----
            if item['TableName'] == 'BankTransactions' and item['Description/Charge_Currency'] is not None:
                st = f"{item['Description/Charge_Currency']}"
            else:
                st = f"{item['Name']}"
            # --------------------------------------------------------------------
            cell = soup.new_tag("h3")
            cell.string = st
            row.append(cell)

            cell = soup.new_tag("p")
            cell['class'] = 'date'
            
            if item['Description/Charge_Currency'] == item['Reserved/Value_Currency'] or item['TableName'] == 'BankTransactions':
                price_lable_1 = f"{item['Final_Value']:,}₪"
                price_lable_2 = ""
            else:
                price_lable_1 = f"{item['Final_Value']:,}₪"
                price_lable_2 = f"({item['Income/Charge_Value']:,}{item['Description/Charge_Currency']})"
            
            # Create a <br> tag
            new_line = soup.new_tag('br')

            # Add text and <br> tag to the <p> tag
            cell.append(price_lable_1)
            cell.append(new_line)
            cell.append(price_lable_2)

            row.append(cell)

            cell = soup.new_tag("p")
            cell['class'] = 'cat'
            d = datetime.strptime(f"{item['Date/Executed_Date']}", "%Y-%m-%d %H:%M:%S").strftime('%A %d')
            cell.string = f"{item['Category']}"  # Category
            row.append(cell)

            table.append(row)

        # ----------
        # ----------
        for _, item in earnings_df.sort_values(by='Date/Executed_Date', ascending=True).iterrows():
            row = soup.new_tag("div")
            row['class'] = 'num'
            d = datetime.strptime(f"{item['Date/Executed_Date']}", "%Y-%m-%d %H:%M:%S").strftime('%A_%d')
            row['data-value'] = f"{d}"  # Amount
            
            if item['TableName'] == 'CardTransactions':
                value = cards_dict[item['Ref/CardID']]
            else:
                value = cards_dict['Bank']
            # row['style'] = f"background-color: {value}"
            
            colored_box_div = soup.new_tag("div")
            colored_box_div['class'] = "color-box"
            colored_box_div['style'] = f"background-color: {value}"
            row.append(colored_box_div)
            
            # ---- replacing the name of the transaction with the description ----
            if item['TableName'] == 'BankTransactions' and item['Description/Charge_Currency'] is not None:
                st = f"{item['Description/Charge_Currency']}"
            else:
                st = f"{item['Name']}"
            # --------------------------------------------------------------------
            cell = soup.new_tag("h3")
            cell.string = st
            row.append(cell)

            cell = soup.new_tag("p")
            cell['class'] = 'date'

            if item['Description/Charge_Currency'] == item['Reserved/Value_Currency'] or item['TableName'] == 'BankTransactions':
                price_lable_1 = f"{item['Final_Value']:,}₪"
                price_lable_2 = ""
            else:
                price_lable_1 = f"{item['Final_Value']:,}₪"
                price_lable_2 = f"({item['Income/Charge_Value']:,}{item['Description/Charge_Currency']})"


            # Create a <br> tag
            new_line = soup.new_tag('br')

            # Add text and <br> tag to the <p> tag
            cell.append(price_lable_1)
            cell.append(new_line)
            cell.append(price_lable_2)

            #cell.string = price_lable
            row.append(cell)

            cell = soup.new_tag("p")
            cell['class'] = 'cat'
            cell.string = f"{item['Category']}"
            row.append(cell)

            table2.append(row)

        # ----------

        div_tag = soup.new_tag('div')

        # ------------- Insertion of outliers under pie charts -------------
        
        transaction_outlier_div = soup.new_tag('div')
        transaction_outlier_div['class'] = 'outer-div'
        
        spendings_outliers = soup.new_tag('div')
        spendings_outliers['class'] = 'inner-div'
        
        # Append each item as list elements (li) inside the ul
        for item in high_std_spendings:
            li = soup.new_tag('li')
            li.string = f"{item[0]} - {item[1]}₪"
            spendings_outliers.append(li)
            
        transaction_outlier_div.append(spendings_outliers)

        earnings_outliers = soup.new_tag('div')
        earnings_outliers['class'] = 'inner-div'

        # Append each item as list elements (li) inside the ul
        for item in high_std_earnings:
            li = soup.new_tag('li')
            li.string = f"{item[0]} - {item[1]}₪"
            earnings_outliers.append(li)
            
        transaction_outlier_div.append(earnings_outliers)
        
        soup.body.insert(5, transaction_outlier_div)
        soup.body.insert(6, soup.new_tag('br'))
        # ------------------------------------------------------------------
        overall_net_income_mean = soup.new_tag('h1')
        overall_net_income_mean['class'] = "two alt-balance"
        overall_net_income_mean.string = f'Overall Net Income Monthly Mean: {data["overall_net_mean"]:,.2f}₪'
        soup.body.insert(12, overall_net_income_mean)

        soup.body.append(div_tag)

        with open(r"source\html\output.html", "w", encoding='utf-8') as outf:
            outf.write(bs4.BeautifulSoup.prettify(soup))

    @staticmethod
    def template_menu(options: list[str], msg: str = "Choose one of the following:\n", sort: bool = False) -> int:
        """
        The function creates a template menu that is printed out for the user.
        Inputs are @options - a list of strings containing different options.
                   @msg - str with a menu message
        return a numbers from 0 to len(options) - 1 representing the chosen option.
        if input does not match a valid option, the function asks for a valid one.
        """
        if sort:
            options = sorted(options)

        utils.log(msg + '\n', 'system')
        utils.pretty_print([f"{str(i) + ' -> ':6s}{utils.heb_conversion(x)}" for i, x in enumerate(options, start=0)])

        while True:
            x = input()
            if not x.isnumeric():
                continue
            x = int(x)
            if x < 0 or x >= len(options):
                continue
            return x
        
    @staticmethod
    def typer_template_menu(options: list[str], msg: str = "Choose one of the following:\n", sort: bool = False) -> Tuple[int, list[str]]:
        """
        The function creates a template menu that is printed out for the user.
        Inputs are @options - a list of strings containing different options.
                   @msg - str with a menu message
        return a numbers from 0 to len(options) - 1 representing the chosen option.
        if input does not match a valid option, the function asks for a valid one.
        """
        def get_substrings(lst: list[str], substring: str) -> list:
            substrings_lst = []

            for st in lst:
                if substring in st:
                    substrings_lst.append(st)
            
            return substrings_lst

        if sort:
            options = sorted(options)

        utils.log(msg + '\n', 'system')

        while True:
            utils.pretty_print([f"{str(i) + ' -> ':6s}{utils.heb_conversion(x)}" for i, x in enumerate(options, start=0)])
            x = input()
            if x.isnumeric(): 
                x = int(x)
                if x < 0 or x >= len(options):
                    continue
                return x, options
            else:   # x is text
                sub_options = get_substrings(options, x)
                if len(sub_options) == 0:
                    continue
                utils.pretty_print([f"{str(i) + ' -> ':6s}{utils.heb_conversion(x)}" for i, x in enumerate(sub_options, start=0)])
                x = input()
                if not x.isnumeric():
                    continue
                x = int(x)
                if x < 0 or x >= len(sub_options):
                    continue
                return x, sub_options

    @staticmethod
    def get_saved_categories(add_options: bool = False, sort: bool = True) -> list[str]:
        """
        returns the categories stored on the local config json
        in the path specified in CATE_JSON_PATH.
        The following options: ["「Create a new category」", "「Skip」", "「Back to menu」"]
        can be added to the list using the function argument @add_options.
        """
        cat_lst = json.load(open(Local.CATE_JSON_PATH, encoding='utf-8'))
        if sort:
            cat_lst = sorted(cat_lst)
        if add_options:
            cat_lst += ["「Create a new category」", "「Skip」", "「Back to menu」"]
        return cat_lst

    @staticmethod
    def update_categories_file(data: list, append: bool = True) -> None:
        """
        The function will write/append new category data to the category json file.
        """
        if append:
            old_data = utils.get_saved_categories(sort=False)
            json.dump(old_data + data, open(Local.CATE_JSON_PATH, "w", encoding='utf-8'))
        else:
            json.dump(data, open(Local.CATE_JSON_PATH, "w", encoding='utf-8'))

    @staticmethod
    def handle_categories() -> Tuple[str, str]:
        """
        The function returns a category name and its description as entered by the user.
        The categories are read from a json file and displayed with 3 adittional options.
        """
        # utils.log("Choose one of the existsing categories:")
        options = utils.get_saved_categories(add_options=True)
        # ----------- Input category and description -------------
        st = "Please insert your selection and description in the following format:\n*Number* - *Description*" + '\n'
        utils.log(st, 'system')
        utils.pretty_print([f"{str(i) + ' -> ':6s}{utils.heb_conversion(x)}" for i, x in enumerate(options, start=0)])

        number = -1
        description = ""
        while True:
            x = input()
            parts = x.split('-', 1)

            if not len(parts) in [1, 2]:
                utils.log("Bad format... try again.", 'system')
                continue

            if len(parts) >= 1:
                number_str = parts[0]
                number_str = number_str.strip()

                if not number_str.isdigit():
                    utils.log("first clause is not a number, try again...", "system")
                    continue

                number = int(number_str)

                if number < 0 or number >= len(options):
                    utils.log("Bad number, try again...", "system")
                    continue

            if len(parts) == 2:
                description = parts[1].strip()
            break

        res = number
        # ----------------------------------------------------------
        if options[res] == "「Create a new category」":
            while True:
                cat = input("Insert a category name: ")
                if cat in utils.get_saved_categories():
                    utils.log("This category name already exists...", "system")
                    continue
                utils.log("Are you sure?\n1-> Yes\n2-> No")
                x = input()
                if x == "1":
                    json.dump(utils.get_saved_categories() + [cat], open(Local.CATE_JSON_PATH, "w", encoding='utf-8'))
                    return cat, description
                else:
                    utils.log("Please Try again...", "system")
                    continue

        return options[res], description

    @staticmethod
    def is_headers_valid(format: str, file_name: str, headers: list, initial_row: int, header_col_index: int) -> bool:
        '''
        The function validates the table headers in the file.
        The values of the headers and the initial row are given in the Constants.py.
        '''
        em = ExcelManager().set_active_sheet(Local.INPUT_FOLDER + "\\" + file_name)

        valid = True
        col = header_col_index
        row = initial_row

        debug_list = [] # debug feature

        for name in headers:
            value = em.read_cell(row, col)
            
            debug_list.append(value) # debug feature

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
        utils.log(f"Header Validation Failed for {file_name} with format {debug_list}\n extracted headers: ", "debug")
        return False

    @staticmethod
    def date_ready(date: str) -> datetime:
        """
        Converts a date string into a datetime object. The string has to be in one
        of the following formats: "%d-%m-%Y", "%d/%m/%Y", "%d/%m/%y"
        """
        formats = ["%d-%m-%Y", "%d/%m/%Y", "%d/%m/%y"]

        for fmt in formats:
            try:
                return datetime.strptime(date, fmt)
            except TypeError as e:
                utils.log(f"Got a Type error: date is of type {type(date)}, Should be str.", "error")
            except Exception as e:
                continue

        utils.log(f"Invalid date format. Please use '-' or '/' as separators...\n got the value: {date} of type {type(date)}.", "error")
        # following date will never be returned. placed for linter.
        return datetime(1, 1, 1)

    @staticmethod
    def amount_ready(value) -> int:
        if value == ' ':
            return 0
        return value

    @staticmethod
    def move_file_to_directory(file_path, destination_directory, create_dst: bool = True):
        try:
            # Check if the file exists
            if not os.path.isfile(file_path):
                utils.log(f"The specified file does not exist -> {file_path}", "error")

            # Get the base name of the file (the file name without the directory path)
            file_name = os.path.basename(file_path)

            if create_dst and not os.path.exists(destination_directory):
                utils.log(f"New directory made: {destination_directory}", "system")
                os.makedirs(destination_directory)

            ExcelManager().close_and_kill_excel()
            # Join the destination directory path with the file name to get the new file path
            new_file_path = os.path.join(destination_directory, file_name)

            # Move the file to the destination directory
            shutil.move(file_path, new_file_path)

            utils.log(f"File moved successfully to {new_file_path}", "system")
        except Exception as e:
            utils.log(f"Something happend.. Could not move the file -> {e}", "warning")

    @staticmethod
    def move_to_recycle_bin(file_path):
        try:
            send2trash.send2trash(file_path)
            utils.log(f"File '{file_path}' sent to recycle bin.", 'system')
        except Exception as e:
            utils.log(f"Failed to send '{file_path}' to recycle bin: {e}", 'system')

    @staticmethod
    def reg_extract(rule: str, text: str) -> str:
        """
        The function returns the first match from the text according to the given rule.
        """
        import re

        matches = re.findall(rule, text)

        if matches:
            return matches[0]
        else:
            utils.log(f"In function reg_extract, No match was found for\n \
                       rule: {rule}     |   string: {text}", "error")
            return "Code won't reach here"

    @staticmethod
    def next_month(date: datetime) -> datetime:
        """
        receives a month - a number between 1 - 12 describing 
        returns the next month/year 
        """
        from dateutil.relativedelta import relativedelta

        # Get the next month by adding a relativedelta of 1 month
        return date + relativedelta(months=1)
    
    @staticmethod
    def previous_month(date: datetime) -> datetime:
        """
        receives a month - a number between 1 - 12 describing 
        returns the next month/year 
        """
        from dateutil.relativedelta import relativedelta

        # Get the next month by adding a relativedelta of 1 month
        return date - relativedelta(months=1)


    @staticmethod
    def subtract_month(month: int, year: int) -> Tuple[str, str]:
        """
        Function returns the date, one month before the given one (not including the day)
        The format is: MM, YYYY
        """

        if month == 1:
            month = 12
            year -= 1
        elif 1 < month <= 12:
            month -= 1
        else:
            utils.log("Month must be between 1 and 12, inclusive.", 'error')

        str_month = str(month)
        if len(str_month) == 1:
            str_month = '0' + str_month

        return str_month, str(year)

    @staticmethod
    def next_day(date: datetime) -> datetime:
        from datetime import datetime, timedelta

        # Assuming your datetime object is stored in the variable `current_datetime`
        current_datetime = datetime.now()  # Replace this with your datetime object

        # Get the next day by adding a timedelta of 1 day
        return current_datetime + timedelta(days=1)


    @staticmethod
    def remove_leumi(df: pd.DataFrame) -> pd.DataFrame:
        return df[(df['Name'] != 'לאומי ויזה') & (df['Category'] != 'IGNORE')]

    @staticmethod
    def pretty_print(lst: list, const: int = 6) -> None:
        """
        The function prints the given list in a rectangle shaped pattern.
        The elements are indexed from 0 to n - 1.
        The rectangle is set to have a maximun of @const elements per column.
        """
        n = len(lst)
        m = 1 + n // const
        for i in range(0, const):
            for j in range(0, m):
                index = i + const*j
                if index >= len(lst):
                    break
                print(f"{lst[i + const*j]:27s}", end="")
            print()

    @staticmethod
    def validate_formats() -> Union[str, bool]:
        """
        The function Checks the validity of the formats filled in by the user
        According to the rules. (The rules are not yet documented).
        If an error accures, a string is returned, otherwise, True is returned.
        """
        from Configurations.Formats import Formats, Identification_Method, Context_class, Sortion_Method
        formats = Formats.FORMATS
        utils.log(f'Total number of formats: {len(formats)}', 'debug')

        # Check that all keys are present in present formats
        card_keys = ['Format Name',
                    'Context',
                    'Identification method',
                    'Identification data',
                    'Sortion method',
                    'Sortion key',
                    'Card number cell',
                    'Card string format',
                    'Adittional data field',
                    'TimeStamp',
                    'TimeStamp Format', 
                    'TimeStamp location',
                    'Headers',
                    'Double tables',
                    'Secondary Headers',
                    'Header row index',
                    'Header col index',
                    'Independent']
        bank_keys = ['Format Name',
                    'Context',
                    'Identification method',
                    'Identification data',
                    'Sortion method',
                    'Sortion key',
                    'Adittional data field',
                    'Headers',
                    'Double tables',
                    'Secondary Headers',
                    'Header row index',
                    'Header col index',
                    'Independent']
        
        for format_name, format_data in tqdm(formats.items(), desc=f"{'Validating formats: Overall info':42s}", unit="formats"):
            dict_i_keys = list(format_data.keys())
            if format_data['Context'] == Context_class.Card:
                keys_to_test = card_keys
            else:
                keys_to_test = bank_keys
            for key in keys_to_test:
                if key not in dict_i_keys:
                    return f"The key ({key}) is missing from format ({format_name})"

        def check_multiple(key: str, secondary_key) -> list:
            lst = []
            for format_name_i, format_data_i in formats.items():
                for format_name_j, format_data_j in formats.items():
                    if format_name_i == format_name_j:
                        continue
                    if format_data_i[key] == format_data_j[key]:
                        lst.append((format_name_i, format_name_j))
            
            res = []
            for tup in lst:
                format_1 = tup[0]
                format_2 = tup[1]
                if formats[format_1][secondary_key] == Identification_Method.HEADERS or \
                    formats[format_2][secondary_key] == Identification_Method.HEADERS:
                    res.append(tup)
            
            return res

        for format_key, format_data in tqdm(formats.items(), desc=f"{'Validating formats: Overall info':42s}", unit="formats"):
            if format_key != format_data['Format Name']:
                return f"Format name missmatch for {format_key}"

            if not isinstance(format_data['Context'], Context_class):
                return f"Context Enum was not used for {format_key}"

            if not isinstance(format_data['Identification method'], Identification_Method):
                return f"Identification_Method Enum was not used for {format_key}"

            if format_data['Identification method'] == Identification_Method.NONE:
                return 'Identification_Method should not be Identification_Method.NONE'

            data = format_data['Identification data']
            match format_data['Identification method']:
                case Identification_Method.FILE_NAME:
                    if not isinstance(data, str):
                        return f'Identification data should be a string when using "Identification_Method.FILE_NAME" in format {format_key}'
                case Identification_Method.CELL:
                    if not isinstance(data, tuple):
                        return f'Identification data should be a tuple indicating row, col when using "Identification_Method.CELL" in format {format_key}'
                case Identification_Method.HEADERS:
                    if data is not None:
                        return f'Identification data should be None when using "Identification_Method.Headers" in format {format_key}'
                    if len(format_data['Headers']) == 0:
                        return f'Headers were not specified'
                    # if format_key in header_duplicates:
                    #     return f'The "Header Identification" field for {format_key} Cannot be set to "HEADERS". Because there is another format with identical headers.'
                case _:
                    return f'Internal ERROR, should not happen.'
                
            sortion_key = format_data['Sortion key']
            match format_data['Sortion method']:
                case Sortion_Method.BY_NAME_SERIAL:
                    if sortion_key is not None:
                        return f'Bad sortion key for format {format_key}'
                case Sortion_Method.BY_NAME_DATE:
                    if sortion_key is not None:
                        return f'Bad sortion key for format {format_key}'
                case _:
                    return f'Please indicate a sortion method for {format_key}'

            add_data = format_data['Adittional data field']

            if add_data is Tuple:
                if add_data[0] < 1:
                    return f'Bad row value {add_data[0]} in format {format_key}, please use values greater than 0.'
                if add_data[1] < 0:
                    return f'Bad col value {add_data[1]} in format {format_key}, please use positive values.'
            if add_data is not None and not isinstance(add_data, tuple):
                return f"Bad input type {type(add_data)} at 'adittional data field' in format {format_key}."
            
            if not isinstance(format_data['Headers'], list):
                return f'Bad header format {type(format_data["Headers"])} in format {format_key}.'
            if len(format_data['Headers']) < 1:
                return f'Headers list is too short for format {format_key}.'
            
            if type(format_data['Double tables']) != bool:
                return f'Bad format for key "Double tables", in {format_key}. Should be of type bool.'
            
            if format_data['Double tables']:
                if type(format_data['Secondary Headers']) != list:
                    return f'Bad Secondary Headers format {type(format_data["Secondary Headers"])} in format {format_key}.'
                if len(format_data['Secondary Headers']) < 1:
                    return f'Secondary Headers list is too short for format {format_key}.'
            else:
                if format_data['Secondary Headers'] != []:
                    return f'"Secondary Headers" should be [] (empty list) for "Double tables" == True in format {format_key}.'
                
            if type(format_data['Independent']) != bool:
                f'Bad format for key "Independent" {format_data["Independent"]}, in format {format_key}.'
        
        for format_name_i, data_i in tqdm(formats.items(), desc=f"{'Validating formats: identification method':42s}", unit="formats"):
            for format_name_j, data_j in formats.items():
                if format_name_i != format_name_j:
                    if tuple(data_i['Headers']) == tuple(data_j['Headers']) and \
                        data_i['Identification method'] == data_j['Identification method'] and \
                        data_i['Identification data'] == data_j['Identification data']:
                        return f"「{format_name_i}」 and 「{format_name_j}」has identical identification system\n\
\t  Make sure that the the following keys: 'Identification method', 'Identification data', 'Headers' are unique\
\t  Between formats."

        tuple_lst = check_multiple("Headers", "Identification method")
        st = ""
        for tup in tuple_lst:
            st += f"[LOGIC ERROR]: The following formats: {tup[0]} and {tup[1]} Have the same 'Headers',\n\
Therefore, they cannot be identified by them. \
Please Make sure that none of the following formats have their 'Identifications Method' set to 'IdentificationsMethod.Header'.\n"
        
        if tuple_lst != []:
            return st

        return True
    
    @staticmethod
    def read_present_table():
        
        from database import DataBase
        from dateutil.relativedelta import relativedelta

        file_df = DataBase().get_file_table()

        # Sort from earliest to latest
        file_df.sort_values(by='Date', inplace=True)

        # The following line, converts the column, from string value dates, to date object of the following format: example: "November, 2023"
        # Because the date represent the Charge date of the transactions, one month is taken back to represent the month
        # the trasnactions were taken in.
        file_df['Date'] = file_df['Date'].apply(lambda x: (datetime.strptime(x, "%Y-%m-%d %H:%M:%S" )  - relativedelta(months=1)).strftime("%B, %Y"))
        
        indexes = file_df['Date'].unique().tolist()
        # columns = file_df['Format'].unique().tolist()
        columns = (file_df['Format'].astype(str) + " | " + file_df['Card_Number']).unique().tolist()

        df = pd.DataFrame(index=indexes, columns=columns)
        for _, row in file_df.iterrows():
            last_update = row["Last_update"]
            date = row["Date"]
            format_name = row["Format"]
            card_number = row["Card_Number"]
            col_name =  format_name + " | " + card_number
            df.at[date, col_name] = last_update
                
        return df


    @staticmethod
    def create_html_with_colored_dates(df, output_file_path='output.html'):
        # Define a Jinja2 template for the HTML

        from jinja2 import Template
        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                table {
                    border-collapse: collapse;
                    width: 100%;
                    overflow-x: auto; /* Enable horizontal scrolling for small screens */
                }

                th, td {
                    border: 1px solid black;
                    padding: 10px;
                    text-align: center; /* Adjust text alignment */
                    font-size: 14px; /* Adjust font size */
                }

                th {
                    background-color: #f2f2f2; /* Header background color */
                    font-weight: bold; /* Bold header text */
                }

                tr:nth-child(even) {
                    background-color: #f9f9f9; /* Alternate row background color */
                }

                .date {
                    background-color: #c2f0c2; /* Light green for date cells */
                }

                .plain {
                    background-color: #ffb3b3; /* Light red for plain cells */
                }
            </style>
        </head>
        <body>
            <h1 style="text-align: Center"> File Organizer</h1>
            <table>
                <thead>
                    <tr>
                        <th></th>
                        {% for col in columns %}
                            <th>{{ col }}</th>
                        {% endfor %}
                    </tr>
                </thead>
                <tbody>
                    {% for index, row in data.iterrows() %}
                        <tr>
                            <td>{{ index }}</td>
                            {% for value in row %}
                                <td {% if pd.isna(value) %}class="plain" {% else %}class="date"{% endif %}>
                                    {{ value }}
                                </td>
                            {% endfor %}
                        </tr>
                    {% endfor %}
                </tbody>
            </table>
        </body>
        </html>
        """
        # Apply the template to create the HTML
        template = Template(html_template)
        rendered_html = template.render(data=df, columns=df.columns, pd=pd)

        # Save the HTML to a file
        with open(output_file_path, 'w') as html_file:
            html_file.write(rendered_html)

        # Open the HTML file in a web browser
        import webbrowser
        webbrowser.open(output_file_path)

    @staticmethod
    def seperate_high_std(df: pd.DataFrame, numerical_col_name: str) -> Tuple[pd.DataFrame, list]:
        """
        The function receives 
        1. A data frame (pd.DataFrame)
        2. A name (str) representing the column name of the relevant numerical value (probably price values)
        The function will return a sub section of the data frame, along with a list.
        The data frame will include only transactions that have lower prices than the total std of the transactions.
        The transactions that were removed, will be appended to the returned list in the following format:
        [(category_0, total_sum_0), (category_1, total_sum_1), ... , (category_n, total_sum_n)]
        """
        std = df[numerical_col_name].std()
        mean = df[numerical_col_name].mean()
        total = df[numerical_col_name].sum()

        lower_treshold = total*0.02
        #lower_treshold = lower_treshold if lower_treshold > 0 else 0.05*mean 

        high_treshold = df[numerical_col_name].max()  + 10

        conditions = (df[numerical_col_name] < high_treshold) & (df[numerical_col_name] > lower_treshold)
        sub_df = df[conditions]
        counter_sub_df = df[~conditions]

        counter_list = [(utils.heb_conversion(category), row[numerical_col_name]) for category, row in counter_sub_df.iterrows()]
        # create a list -> trans_name, numerical_col_name
        return sub_df, counter_list
    
    @staticmethod
    def create_html_name_analysis(data: dict) -> None:
        import bs4

        # load the file
        with open(r"source/html/Category_template.html") as inf:
            txt = inf.read()
        soup = bs4.BeautifulSoup(txt, features="html.parser")

        # Find the h2 tag with class 'subtitle'
        subtitle_tag = soup.find('h2', class_='subtitle')
        subtitle_tag.string = data['subtitle']

        subtitle_tag = soup.find('h3', class_='category-title')
        subtitle_tag.string = data['Category/business name']

        tag = soup.find('td', class_='Monthly Average')
        if data['Monthly Average'] < 0 :
            tag.string = f"({abs(data['Monthly Average']):,.2f}) ₪"
        else:
            tag.string = f"{data['Monthly Average']:,.2f} ₪"

        tag = soup.find('td', class_='Monthly Active Average')
        if data['Monthly Active Average'] < 0:
            tag.string = f"({abs(data['Monthly Active Average']):,.2f}) ₪"
        else:
            tag.string = f"{data['Monthly Active Average']:,.2f} ₪"

        tag = soup.find('td', class_="Monthly Active Standard Deviation")
        tag.string = f"{data['Monthly Active Standard Deviation']:,.2f} ₪"

        tag = soup.find('td', class_="Yearly Average")
        if data['Yearly Average'] < 0:
            tag.string = f"({abs(data['Yearly Average']):,.2f}) ₪"
        else:
            tag.string = f"{data['Yearly Average']:,.2f} ₪"

        tag = soup.find('td', class_="Total Spendings")
        tag.string = f"({data['Total Spendings']:,.2f}) ₪"

        tag = soup.find('td', class_="Total Income")
        tag.string = f"{data['Total Income']:,.2f} ₪"

        tag = soup.find('img', alt="Yearly Use")
        tag['src'] = f"{data['Yearly use plot path']}"


        tag = soup.find('p', class_="Highest Transaction: Value & Date")
        tag.string = "The highest transaction value was: " + data["Highest Transaction value"] + "₪ , Executed on " + data["Highest Transaction date"] +" ₪"

        # Add associated cate/business:
        tag = soup.find('p', class_="Associated")
        
        for ele in data["Association list"]:
            sub_tag = soup.new_tag('li')
            sub_tag.string = f"{ele}"
            tag.append(sub_tag)

        tag = soup.find('img', alt="Additional Image")
        tag['src'] = f"{data['count pie plot path']}"

        # Add transactions data to html list:
        list_tag = soup.find('main', class_="leaderboard__profiles")

        from datetime import datetime

        def create_list_tag(name: str, date, value):
            main_tag = soup.new_tag('article')
            main_tag['class'] = 'leaderboard__profile'
            
            # img_tag = soup.new_tag('img')
            # img_tag['src'] = ""
            # img_tag['alt'] = "-name here-"
            # img_tag['class'] = 'leaderboard__picture'
            # main_tag.append(img_tag)
            
            name_tag = soup.new_tag('span')
            name_tag['class'] = 'leaderboard__name'
            name_tag.string = datetime.strptime(date, "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
            main_tag.append(name_tag)

            name_tag = soup.new_tag('span')
            name_tag['class'] = 'leaderboard__name'
            name_tag.string = f"{name}"
            main_tag.append(name_tag)     

            value_tag = soup.new_tag('span')
            if value < 0:
                value_tag['class'] = 'leaderboard__value_neg'
            else:
                value_tag['class'] = 'leaderboard__value'
            value_tag.string = f"{abs(value)} ₪"
            main_tag.append(value_tag)

            return main_tag

        for _, row in data["transactions"].sort_values(by='Date/Executed_Date').iterrows():
            #date = datetime.strptime(row['Date/Executed_Date'], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
            #sub_tag.string = f"{row['Name']}\n{row['Final_Value']}\n{date}\n{row['Extra_Info']}"
            lst_element = create_list_tag(row['Name'], row['Date/Executed_Date'], row['Final_Value'])
            list_tag.append(lst_element)

        with open(r"source\html\Category_output.html", "w", encoding='utf-8') as outf:
            outf.write(bs4.BeautifulSoup.prettify(soup))

    @staticmethod
    def auto_tagger(name: str, category: str = None) -> str:
        """
        The function is responsible for editing the json config file depending on the inputs.
        The function receives:
        a Bussines name, and a category name.
        In case category was not inserted, or specified as None, json file will be updated with
        name: None
        In case both were given, and not None, the pair will be appended or changed depending on
        the current status of the keys on the dictionary.

        """
        if os.path.exists(Local.AUTO_TAGGER_PATH):
            with open(Local.AUTO_TAGGER_PATH, 'r', encoding='utf-8') as f:
                at_dict = json.load(f)

        else:
            at_dict = {}

        if category is None:
            if name not in at_dict:
                at_dict[name] = None
        else:
            if name in at_dict:
                match at_dict[name]:
                    case None:
                        at_dict[name] = category
                    case "No Match":
                        msg =f"The name {name} is already matched with a 'No Match' string. \
                            but you are trying to change it to {category}, do you aprrove?"
                        if utils.template_menu(['no', 'yes'], msg):
                            at_dict[name] = category
                    case _:
                        msg =f"The name {name} is already matched with the category \
                            {utils.heb_conversion(dict_at[name])} but you are trying \
                            to change it to {category}, do you aprrove?"
                        if utils.template_menu(['no', 'yes'], msg):
                            at_dict[name] = category
            else:
                at_dict[name] = category


        with open(Local.AUTO_TAGGER_PATH, 'w', encoding='utf-8') as f:
            json.dump(at_dict, f, ensure_ascii=False)
        #utils.log(f"The following key:value pair has been updated in auto_tagger.json to -> {utils.heb_conversion(name)} : {category}",'system')

        return at_dict[name]

    @staticmethod
    def tagger_refresh() -> None:
        """
        The function uses the json config file, in order to try and auto tag transactions
        with no category tagging.
        """
        from database import DataBase

        dirty_bit = False
        logs = "\n\n ----- The following transactions have been tagged: -----\n\n"
        lst, desc = DataBase().get_untagged()
        untagged_transactions_df = pd.DataFrame(lst, columns=desc)
        for _, row in untagged_transactions_df.iterrows():
            res = utils.auto_tagger(row['Name'])
            if res == 'No Match':
                continue
            if res is not None:
                dirty_bit = True
                DataBase().set_category(table=row['TableName'], id=row['ID'], category=res)
                logs += f"transaction {utils.heb_conversion(row['Name'])} ({row['TableName']}) ({row['ID']}) was tagged to {res}\n"

        if dirty_bit:
            utils.log(logs, 'system')
            DataBase().commit_changes()
        else:
            utils.log('No transactions were Auto tagged...', 'system')

    @staticmethod
    def match_BeinLeumi_headers(table: list[list]) -> list[list]:
        """

        """
        from Configurations.Formats import Formats
        if not Formats.FORMATS["BeinLeumi-Bank"]["Headers"] == \
                ['תאריך',
                'סוג פעולה',
                'תיאור',
                'אסמכתא',
                'זכות',
                'חובה',
                'תאריך ערך',
                'יתרה']:
            raise ValueError("Headers Changed!")
        if not Formats.FORMATS["BeinLeumi-Bank-Date-Range"]["Headers"] == \
                ['יתרה',
                'תאריך ערך',  #1
                'זכות',       #2
                'חובה',       #3
                'תאור',       #4
                'אסמכתא',     #5
                'סוג פעולה',  #6
                'תאריך']:
            raise ValueError("Headers Changed!")
        new_column_order = [7, 6, 4, 5, 2, 3, 1, 0]
        reordered_data = [[row[i] for i in new_column_order] for row in table]
        return reordered_data

    @staticmethod
    def validate_BankTransactions() -> bool:
        """
        
        """
        from datetime import datetime
        from database import DataBase

        def is_valid_balance(value):
            return isinstance(value, (int, float))

        personal_conf_dict = json.load(open(Local.PERSONAL_CONFIG, encoding='utf-8'))
        date_str = personal_conf_dict['bank_transactions_last_valid_date']
        last_valid_date = datetime.strptime(date_str, "%Y-%m-%d")
        df = DataBase().query_Bank_Transactions_for_validation(last_valid_date)
        df = df.sort_values(by=['Date', 'ID'], ascending=[True, False])
        #print(df.to_markdown())
        balance = "Initial Value"
        for _, row in df.iterrows():
            if balance == "Initial Value":
                if is_valid_balance(row['Balance']):
                    balance = row['Balance']
            else:
                balance += row['Income'] - row['Out']
                if is_valid_balance(row['Balance']):
                    if abs(balance - row['Balance']) > 0.001:
                        utils.log(f"Bank Transaction Validation FAILED!\nDetails:\n\
                                    tried comparing a calculated balance of {balance}\n\
                                    with the given balance of {row['Balance']}\n\
                                    given transaction is associated with ID: {row['ID']}\n\
                                    Transaction date is {row['Date']}", "error")
                    else:
                        last_valid_date = row['Date']
                        print(type(last_valid_date))

        if isinstance(last_valid_date, datetime):
            last_valid_date = last_valid_date.strftime("%Y-%m-%d")
        else:
            # Convert the string to a datetime object
            date_object = datetime.strptime(last_valid_date, "%Y-%m-%d %H:%M:%S")

            # Define the format for the string without the timestamp
            date_format_without_timestamp = "%Y-%m-%d"

            # Convert the datetime object back to a string without the timestamp
            last_valid_date = date_object.strftime(date_format_without_timestamp)
            
        personal_conf_dict['bank_transactions_last_valid_date'] = last_valid_date
        json.dump(personal_conf_dict, open(Local.PERSONAL_CONFIG, "w", encoding='utf-8'))
        return True

    @staticmethod
    def change_an_existing_category_name():
        """
        """
        cat_lst = utils.get_saved_categories()
        index, cat_lst = utils.typer_template_menu(cat_lst, msg = "Please choose a category name to replace:", sort = True)
        chosen_cat_to_replace = cat_lst[index]
        utils.log(f"You chose {chosen_cat_to_replace}...")
        
        while True:
            new_chosen_cat, _ = utils.handle_categories()
            if chosen_cat_to_replace == new_chosen_cat:
                continue
            if new_chosen_cat in ["「Skip」", "「Back to menu」"]:
                continue
            break
        
        from database import DataBase
        DataBase().replace_category(frm=chosen_cat_to_replace, to=new_chosen_cat)
        DataBase().commit_changes()
        new_category_lst = utils.get_saved_categories()
        new_category_lst.remove(chosen_cat_to_replace)
        utils.update_categories_file(new_category_lst, append=False)
        utils.log(f"({chosen_cat_to_replace}) has been removed from the category list")

    @staticmethod
    def delete_a_transaction() -> None:
        """
        The function asks the user for card transactions ids to delete from the data base.
        The user can pick multiple ids to delete. Note that after the function is executed,
        there will be no documentation of the deleted transaction.
        """
        utils.log("Please insert the id's of the transactions you want to delete, and -1 to stop", 'system')
        id_lst = []
        while True:
            x = input()
            if x == '-1':
                break
            if not x.isdigit() or int(x) < -1 or int(x) == 0:
                utils.log("Please insert a valid input number...", 'system')
                continue

            id_lst.append(x)

        from database import DataBase
        DataBase().delete_transactions(id_lst)
        DataBase().commit_changes()

        # if utils.template_menu(["Delete from Bank Transactions", \
        #                         "Delete from Card Transactions"], \
        #                        "Where do you want to delete the trasnaction from?")
    
        #     DataBase().delete_transactions()
        # else:
        #     DataBase().delete_transactions()
        # DataBase().commit_changes()