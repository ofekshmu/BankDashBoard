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
                    print("This should not happen")
                    input("stopped.")

    @staticmethod
    def generate_html(month_num,
                      spendings_df,
                      earnings_df,
                      monthly_balance: int,
                      cards_dict: dict,
                      gas_stats):
        import bs4
        from datetime import datetime
        import calendar
        # load the file
        with open(r"source\html\Base_template.html") as inf:
            txt = inf.read()
        soup = bs4.BeautifulSoup(txt, features="html.parser")

        sub_titles_div = soup.new_tag('div')

        balance_h2 = soup.new_tag('h2')
        balance_h2.string = f'Balance: {monthly_balance:,}'

        h2_3 = soup.new_tag('h1')
        h2_3.string = f"{calendar.month_name[month_num]}"

        sub_titles_div.append(h2_3)
        sub_titles_div.append(balance_h2)

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

        for _, item in spendings_df.sort_values(by='Date/Executed_Date', ascending=True).iterrows():

            row = soup.new_tag("div")
            row['class'] = 'num'
            d = datetime.strptime(f"{item['Date/Executed_Date']}", "%Y-%m-%d %H:%M:%S").strftime('%A_%d')
            row['data-value'] = f"{d}"   # Amount

            if item['TableName'] == 'CardTransactions':
                value = cards_dict[item['Ref/CardID']]
            else:
                value = cards_dict['Bank']
            row['style'] = f"background-color: {value}"

            st = f"{item['Name']}"   # Name
            cell = soup.new_tag("h3")
            cell.string = st
            row.append(cell)

            cell = soup.new_tag("p")
            cell['class'] = 'date'
            cell.string = f"{item['Final_Value']:,}₪"
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
            row['style'] = f"background-color: {value}"
            
            st = f"{item['Name']}"
            cell = soup.new_tag("h3")
            cell.string = st
            row.append(cell)

            cell = soup.new_tag("p")
            cell['class'] = 'date'
            cell.string = f"{item['Final_Value']:,}₪"
            row.append(cell)

            cell = soup.new_tag("p")
            cell['class'] = 'cat'
            cell.string = f"{item['Category']}"
            row.append(cell)

            table2.append(row)

        # ----------
        div = soup.new_tag("div")
        div["class"] = 'gas-info'
        title = soup.new_tag("h3")
        title.string = "Gas info"
        div.append(title)

        table = soup.new_tag("table")

        for key, value in gas_stats.items():
            tr = soup.new_tag("tr")
            td1 = soup.new_tag("td")
            td1.string = key + ":"
            td2 = soup.new_tag("td")
            td2.string = str(value)
            td2['style'] = 'padding-left: 15px;'
            tr.append(td1)
            tr.append(td2)
            table.append(tr)

        div.append(table)

        outer_div = soup.new_tag("div")
        outer_div['class'] = 'container_img'
        outer_div.append(div)

        img_tag = soup.new_tag("img")
        img_tag['src'] = f"{Local.GAS_GRAPH}"
        outer_div.append(img_tag)

        soup.body.append(outer_div)

        div_tag = soup.new_tag('div')
        div_tag['class'] = 'container_img'

        img_tag = soup.new_tag("img")
        img_tag['src'] = f"{Local.GAS_MONTHLY}"
        div_tag.append(img_tag)

        soup.body.append(div_tag)

        with open(r"source\html\output.html", "w", encoding='utf-8') as outf:
            outf.write(bs4.BeautifulSoup.prettify(soup))

    @staticmethod
    def template_menu(options: list[str], msg: str = "Choose one of the following:\n", sort: bool = False):
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
    def handle_categories() -> Tuple[str, str]:
        """

        """
        # utils.log("Choose one of the existsing categories:")
        cat_lst = json.load(open(Local.CATE_JSON_PATH, encoding='utf-8'))
        cat_lst = sorted(cat_lst)
        options = cat_lst + ["Create a new category", "Skip"]
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
        if options[res] == "Create a new category":
            while True:
                cat = input("Insert a category name: ")
                utils.log("Are you sure?\n1-> Yes\n2-> No")
                x = input()
                if x == "1":
                    json.dump(cat_lst + [cat], open(Local.CATE_JSON_PATH, "w", encoding='utf-8'))
                    return cat, description
                else:
                    utils.log("Please Try again...", "system")
                    continue

        return options[res], description

    @staticmethod
    def is_headers_valid(file_name: str, headers: list, initial_row: int) -> bool:
        '''
        The function validates the table headers in the file.
        The values of the headers and the initial row are given in the Constants.py.
        '''
        em = ExcelManager().set_active_sheet(Local.INPUT_FOLDER + "\\" + file_name)

        valid = True
        col = 0
        row = initial_row
        for name in headers:
            value = em.read_cell(row, col)
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
            utils.log(f"Something happend.. -> {e}", "error")

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
            utils.log(f"In function re_extract, No match was found for\n \
                       rule: {rule}     |   string: {text}", "error")
            return "Code won't reach here"

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
        columns = file_df['Description'].unique().tolist()

        df = pd.DataFrame(index=indexes, columns=columns)
        for _, row in file_df.iterrows():
            last_update = row["Last_update"]
            date = row["Date"]
            format_name = row["Description"]
            df.at[date, format_name] = last_update
                
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
