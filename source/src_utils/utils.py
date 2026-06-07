from Constants import Settings, ReservedNames, Paths, CC_CHARGE_CATEGORY_NAME
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
                log_st += f"\n{100*'-'}\n[ERROR]: {msg}\n{100*'-'}\n"
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
            log_path = '/tmp/Log_file.txt' if os.getenv('DATABASE_URL') else 'Log_file.txt'
            try:
                f = open(log_path, 'a', encoding="utf-8")
                f.write(log_st + "\n")
                f.close()
            except OSError:
                pass
            print(log_st, end=e)

        if category == "error" and not os.getenv('DATABASE_URL'):
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
                      year,
                      spendings_df,
                      high_std_spendings,
                      earnings_df,
                      high_std_earnings,
                      monthly_balance: int,
                      cards_dict: dict,
                      data: dict,
                      accounts_data: dict,
                      cash_information_data: dict) -> None:
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
        span_tag.string = f"{calendar.month_name[month_num]} {year}"
        h1_tag.append(span_tag)
        new_div.append(h1_tag)

        # Find the head tag and append the new div under it
        head_tag = soup.head
        head_tag.insert(0, new_div)


        sub_titles_div = soup.new_tag('div')

        sub_titles_div.attrs['style'] = 'text-align: center;'

        soup.body.insert(2, sub_titles_div)

        # ----------
        div = soup.new_tag('div')
        div['class'] = 'container_img'

        img = soup.new_tag('img')
        img['src'] = Paths.CARD_DIST_PIE_GRAPH

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

        #concat cash spendings with spendings_df after filtering negative values
        
        df = cash_information_data['Monthly Cash Transactions']
        df = df[df['Amount'] < 0]
        spendings_df = pd.concat([spendings_df, df], ignore_index=True)


        for _, item in spendings_df.sort_values(by='Executed_Date', ascending=True).iterrows():

            row = soup.new_tag("div")
            row['class'] = 'num'

            executed_date = item['Execution_Date'] if not pd.isna(item['Execution_Date']) else item['Executed_Date']

            d = datetime.strptime(f"{executed_date}", "%Y-%m-%d %H:%M:%S").strftime('%A_%d')
            row['data-value'] = f"{item['ID']}"   # Amount

            if item['TableName'] == 'CardTransactions':
                value = cards_dict[item['CardID']]
            elif item['TableName'] == 'BankTransactions':
                value = cards_dict['Bank']
            else:
                value = cards_dict['Cash']
            
            # row['style'] = f"background-color: {value}"

            colored_box_div = soup.new_tag("div")
            colored_box_div['class'] = "color-box"
            colored_box_div['style'] = f"background-color: {value}"
            row.append(colored_box_div)


            # ---- replacing the name of the transaction with the description ----
            if item['TableName'] == 'BankTransactions' and item['Description'] is not None:
                st = f"{item['Description']}"
            else:
                st = f"{item['Name']}"
            # --------------------------------------------------------------------
            cell = soup.new_tag("h3")
            cell.string = st
            row.append(cell)

            cell = soup.new_tag("p")
            cell['class'] = 'date'
            
            if not pd.isnull(item['Amount']):
                price_lable_1 = f"{item['Amount']:,.2f}₪"
                price_lable_2 = ""
            elif item['Charge_Currency'] == item['Value_Currency'] or item['TableName'] == 'BankTransactions':
                price_lable_1 = f"{item['Final_Value']:,.2f}₪"
                price_lable_2 = ""
            else:
                price_lable_1 = f"{item['Final_Value']:,.2f}₪"
                price_lable_2 = f"({item['Charge_Value']:,}{item['Charge_Currency']})"
            
            # Create a <br> tag
            new_line = soup.new_tag('br')

            # Add text and <br> tag to the <p> tag
            cell.append(price_lable_1)
            cell.append(new_line)
            cell.append(price_lable_2)

            row.append(cell)

            cell = soup.new_tag("p")
            cell['class'] = 'cat'
            d = datetime.strptime(f"{executed_date}", "%Y-%m-%d %H:%M:%S").strftime('%A %d')
            cell.string = f"{item['Category']}"  # Category
            row.append(cell)

            cell = soup.new_tag("p")
            cell['class'] = 'element4'
            cell.string = f"{d}"
            row.append(cell)

            table.append(row)

        # ----------
        # ----------

        df = cash_information_data['Monthly Cash Transactions']
        df = df[df['Amount'] > 0]
        earnings_df = pd.concat([earnings_df, df], ignore_index=True)

        for _, item in earnings_df.sort_values(by='Executed_Date', ascending=True).iterrows():
            row = soup.new_tag("div")
            row['class'] = 'num'
            
            executed_date = item['Execution_Date'] if not pd.isna(item['Execution_Date']) else item['Executed_Date']
            d = datetime.strptime(f"{executed_date}", "%Y-%m-%d %H:%M:%S").strftime('%A_%d')

            row['data-value'] = f"{item['ID']}"  # Amount
            
            if item['TableName'] == 'CardTransactions':
                value = cards_dict[item['CardID']]
            elif item['TableName'] == 'BankTransactions':
                value = cards_dict['Bank']
            else:
                value = cards_dict['Cash']
            
            colored_box_div = soup.new_tag("div")
            colored_box_div['class'] = "color-box"
            colored_box_div['style'] = f"background-color: {value}"
            row.append(colored_box_div)
            
            # ---- replacing the name of the transaction with the description ----
            if item['TableName'] == 'BankTransactions' and item['Description'] is not None:
                st = f"{item['Description']}"
            else:
                st = f"{item['Name']}"
            # --------------------------------------------------------------------
            cell = soup.new_tag("h3")
            cell.string = st
            row.append(cell)

            cell = soup.new_tag("p")
            cell['class'] = 'date'


            if not pd.isnull(item['Amount']):
                price_lable_1 = f"{item['Amount']:,.2f}₪"
                price_lable_2 = ""
            elif item['Charge_Currency'] == item['Value_Currency'] or item['TableName'] == 'BankTransactions':
                price_lable_1 = f"{item['Final_Value']:,.2f}₪"
                price_lable_2 = ""
            else:
                price_lable_1 = f"{item['Final_Value']:,.2f}₪"
                price_lable_2 = f"({item['Charge_Value']:,}{item['Charge_Currency']})"


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
            
            cell = soup.new_tag("p")
            cell['class'] = 'element4'
            cell.string = f"{d}"
            row.append(cell)

            table2.append(row)

        # ----------

        div_tag = soup.new_tag('div')

        # ------------- Insertion of outliers under pie charts -------------
        # Add CSS styles for outliers with width matching pie chart
        style = soup.find('style')
        style.string += """
            .outliers-container {
                display: flex;
                justify-content: space-around;
                margin: 20px auto;
                width: 800px;  /* Match pie chart width */
                gap: 20px;
                padding: 0 20px;
            }
            .outlier-box {
                flex: 1;
                background: white;
                padding: 20px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            }
            .outlier-box h3 {
                color: #333;
                margin-bottom: 15px;
                font-size: 1.2em;
                text-align: center;
                border-bottom: 2px solid #eee;
                padding-bottom: 10px;
            }
            .outlier-list {
                list-style: none;
                padding: 0;
                margin: 0;
            }
            .outlier-item {
                display: flex;
                justify-content: space-between;
                padding: 8px 0;
                border-bottom: 1px solid #eee;
                transition: background-color 0.2s;
            }
            .outlier-item:hover {
                background-color: #f5f5f5;
            }
            .outlier-name {
                color: #555;
            }
            .outlier-value {
                color: #e74c3c;
                font-weight: bold;
            }
        """

        # Create outliers container
        outliers_container = soup.new_tag('div')
        outliers_container['class'] = 'outliers-container'

        # Spendings outliers box
        spendings_box = soup.new_tag('div')
        spendings_box['class'] = 'outlier-box'
        
        spendings_title = soup.new_tag('h3')
        spendings_title.string = 'Other Spending Categories'  # Changed title
        spendings_box.append(spendings_title)

        spendings_list = soup.new_tag('ul')
        spendings_list['class'] = 'outlier-list'
        
        for item in high_std_spendings:
            li = soup.new_tag('li')
            li['class'] = 'outlier-item'
            
            name_span = soup.new_tag('span')
            name_span['class'] = 'outlier-name'
            name_span.string = item[0]
            
            value_span = soup.new_tag('span')
            value_span['class'] = 'outlier-value'
            value_span.string = f"{item[1]:,.2f}₪"
            
            li.append(name_span)
            li.append(value_span)
            spendings_list.append(li)
        
        spendings_box.append(spendings_list)
        outliers_container.append(spendings_box)

        # Earnings outliers box
        earnings_box = soup.new_tag('div')
        earnings_box['class'] = 'outlier-box'
        
        earnings_title = soup.new_tag('h3')
        earnings_title.string = 'Other Earning Categories'  # Changed title
        earnings_box.append(earnings_title)

        earnings_list = soup.new_tag('ul')
        earnings_list['class'] = 'outlier-list'
        
        for item in high_std_earnings:
            li = soup.new_tag('li')
            li['class'] = 'outlier-item'
            
            name_span = soup.new_tag('span')
            name_span['class'] = 'outlier-name'
            name_span.string = item[0]
            
            value_span = soup.new_tag('span')
            value_span['class'] = 'outlier-value'
            value_span.string = f"{item[1]:,.2f}₪"
            
            li.append(name_span)
            li.append(value_span)
            earnings_list.append(li)
        
        earnings_box.append(earnings_list)
        outliers_container.append(earnings_box)

        # Insert the outliers container
        soup.body.insert(4, outliers_container)
        soup.body.insert(5, soup.new_tag('br'))
        # ------------------------------------------------------------------

        # Create financial metrics containers
        def create_financial_metric(soup, label, value, is_positive):
            """Helper function to create styled financial metrics"""
            container = soup.new_tag('div')
            container['class'] = 'metric-container'
            
            display = soup.new_tag('h1')
            display['class'] = "metric-display"
            
            label_span = soup.new_tag('span', attrs={'class': 'metric-label'})
            label_span.string = f'{label} '
            
            amount_span = soup.new_tag('span', attrs={'class': 'metric-amount'})
            amount_span['class'] = "metric-amount positive" if is_positive else "metric-amount negative"
            # Add minus sign for negative values
            amount_span.string = f'{value:,.2f}₪' if value >= 0 else f'-{abs(value):,.2f}₪'
            
            display.append(label_span)
            display.append(amount_span)
            container.append(display)
            return container

        # cash info metrics
        cash_spent = create_financial_metric(soup, 'Deposit/Spent Cash', cash_information_data['Monthly Spent Cash'], False)
        cash_earned = create_financial_metric(soup, 'Withdrawed/Earned Cash', cash_information_data['Monthly Earned Cash'], True)
        
        cmetrics_div = soup.new_tag('div')
        cmetrics_div['class'] = 'metrics-container'
        cmetrics_div.append(cash_spent)
        cmetrics_div.append(cash_earned)

        soup.body.append(cmetrics_div)

        # Create containers for each metric
        balance_container = create_financial_metric(soup, 'Balance', monthly_balance, monthly_balance >= 0)
        net_income_container = create_financial_metric(soup, 'Net Income', data["net income"], data["net income"] >= 0)
        overall_container = create_financial_metric(soup, 'Overall Net Income', data["overall net income"], data["overall net income"] >= 0)
        monthly_mean_container = create_financial_metric(soup, 'Monthly Mean', data["overall_net_mean"], data["overall_net_mean"] >= 0)

        # Add metrics at the right position (after pie charts)
        metrics_div = soup.new_tag('div')
        metrics_div['class'] = 'metrics-container'
        metrics_div.append(balance_container)
        metrics_div.append(net_income_container)
        metrics_div.append(overall_container)
        metrics_div.append(monthly_mean_container)

        # Insert after the pie charts but before the transactions lists
        soup.body.insert(7, metrics_div)

        # Add CSS styles to the head
        style = soup.new_tag('style')
        style.string = """
            .metric-container {
                text-align: center;
                margin: 20px 0;
                padding: 15px;
                background: linear-gradient(145deg, #f6f6f6, #ffffff);
                border-radius: 10px;
                box-shadow: 0 4px 15px rgba(0,0,0,0.1);
                transition: transform 0.2s;
            }
            .metric-container:hover {
                transform: translateY(-2px);
            }
            .metric-display {
                margin: 0;
                font-family: Arial, sans-serif;
            }
            .metric-label {
                color: #666;
                font-size: 0.7em;
                font-weight: normal;
            }
            .metric-amount {
                font-size: 0.9em;
                font-weight: bold;
                margin-left: 10px;
            }
            .metric-amount.positive {
                color: #4fba89;
            }
            .metric-amount.negative {
                color: #f66b85;
            }
            .metrics-container {
                display: flex;
                flex-direction: column;
                gap: 10px;
                align-items: center;
                margin: 20px auto;
                width: 800px;
            }
        """
        soup.head.append(style)

        # Replace old displays with new ones
        head_tag.append(balance_container)
        head_tag.append(net_income_container)
        head_tag.append(overall_container)

        # Add section for accounts balance plot at the end of the HTML content with margin
        accounts_balance_div = soup.new_tag('div')
        accounts_balance_div['class'] = 'container_img'
        accounts_balance_div['style'] = 'margin-top: 50px;'
        img_tag = soup.new_tag('img')
        img_tag['src'] = "../../Outputs/accounts_liner_plots.png"
        img_tag['class'] = "img-fluid"
        accounts_balance_div.append(img_tag)
        soup.body.append(accounts_balance_div)

        # Get most recent values for each account
        recent_accounts_data = {}
        total_balance = 0
        for account, values in accounts_data.items():
            if account != 'Total':  # Skip the total as we'll calculate it ourselves
                latest_date = max(date for date, _ in values)
                latest_value = next(value for date, value in values if date == latest_date)
                recent_accounts_data[account] = {
                    'date': latest_date,
                    'value': latest_value
                }
                total_balance += latest_value

        # Create accounts summary section
        accounts_summary_div = soup.new_tag('div')
        accounts_summary_div['class'] = 'accounts-summary'
        accounts_summary_div['style'] = 'margin-top: 50px; text-align: center;'

        # Create summary table
        table = soup.new_tag('table')
        table['style'] = '''
            margin: 0 auto;
            border-collapse: collapse;
            width: 80%;
            max-width: 800px;
            background: white;
            box-shadow: 0 1px 3px rgba(0,0,0,0.2);
            margin-bottom: 30px;
        '''

        # Add headers
        header = soup.new_tag('tr')
        for col in ['Account', 'Last Updated', 'Balance']:
            th = soup.new_tag('th')
            th.string = col
            th['style'] = 'padding: 12px; border-bottom: 2px solid #ddd; text-align: left;'
            header.append(th)
        table.append(header)

        # Add account rows
        for account, data in recent_accounts_data.items():
            row = soup.new_tag('tr')
            
            # Account name cell
            name_cell = soup.new_tag('td')
            name_cell.string = account
            name_cell['style'] = 'padding: 12px; border-bottom: 1px solid #eee;'
            row.append(name_cell)
            
            # Date cell
            date_cell = soup.new_tag('td')
            date_cell.string = data['date'].strftime('%Y-%m-%d')
            date_cell['style'] = 'padding: 12px; border-bottom: 1px solid #eee;'
            row.append(date_cell)
            
            # Balance cell
            balance_cell = soup.new_tag('td')
            balance_cell.string = f"{data['value']:,.2f}₪"
            balance_cell['style'] = 'padding: 12px; border-bottom: 1px solid #eee; text-align: right;'
            row.append(balance_cell)
            
            table.append(row)

        # Add total row
        total_row = soup.new_tag('tr')
        total_row['style'] = 'font-weight: bold; background-color: #f8f9fa;'
        
        total_label = soup.new_tag('td')
        total_label.string = 'Total'
        total_label['style'] = 'padding: 12px; border-top: 2px solid #ddd;'
        total_row.append(total_label)
        
        total_date = soup.new_tag('td')
        total_date.string = datetime.now().strftime('%Y-%m-%d')
        total_date['style'] = 'padding: 12px; border-top: 2px solid #ddd;'
        total_row.append(total_date)
        
        total_value = soup.new_tag('td')
        total_value.string = f"{total_balance:,.2f}₪"
        total_value['style'] = 'padding: 12px; border-top: 2px solid #ddd; text-align: right;'
        total_row.append(total_value)
        
        table.append(total_row)
        accounts_summary_div.append(table)

        # Add accounts summary section above the accounts plot
        accounts_plot_div = soup.find('div', class_='container_img', style='margin-top: 50px;')
        soup.body.insert(soup.body.contents.index(accounts_plot_div) + 1, accounts_summary_div)

        with open(r"source\html\output.html", "w", encoding='utf-8') as outf:
            outf.write(bs4.BeautifulSoup.prettify(soup))

    @staticmethod
    def template_menu(options: list[str], msg: str = "Choose one of the following:\n", exit: bool = False, sort: bool = False, col_space: int = 27, row_count: int = 6 ) -> int:
        """
        The function creates a template menu that is printed out for the user.
        Inputs are @options - a list of strings containing different options.
                   @msg - str with a menu message
                   @sort - for sorting the options alphabetically
                   @exit - for adding a "Return" option at the top of the list (output of value 0)
        return a numbers from 0 to len(options) - 1 representing the chosen option.
        if input does not match a valid option, the function asks for a valid one.
        """
        if sort:
            options = sorted(options)
        
        if exit:
            # append to the head of the list for comfort reason
            options.insert(0, "「Return」")

        utils.log(msg + '\n', 'system')
        utils.pretty_print([f"{str(i) + ' -> ':6s}{utils.heb_conversion(x)}" for i, x in enumerate(options, start=0)], const=row_count, col_space=col_space)

        while True:
            x = input()
            if not x.isnumeric():
                continue
            x = int(x)
            if x < 0 or x >= len(options):
                utils.log('Insert a valid index number!', 'system')
                continue
            return x
        
    @staticmethod
    def typer_template_menu(options: list[str], msg: str = "Choose one of the following:\n", sort: bool = False) -> Tuple[int, list[str]]:
        """
        The function creates a template menu that is printed out for the user.
        The user is requested to insert a substring or a valid option number.
        If the substring existis in one of the printed options, the list of options will reduce to fit the substring.
        Inputs are @options - a list of strings containing different options.
                   @msg - str with a menu message
        return a numbers from 0 to len(options) - 1 representing the chosen option.
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
        cat_lst = json.load(open(Paths.CATEGORY_JSON, encoding='utf-8'))
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
            json.dump(old_data + data, open(Paths.CATEGORY_JSON, "w", encoding='utf-8'))
        else:
            json.dump(data, open(Paths.CATEGORY_JSON, "w", encoding='utf-8'))

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
        utils.pretty_print([f"{str(i) + ' -> ':6s}{utils.heb_conversion(x)}" for i, x in enumerate(options, start=0)], const=8)

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
                    json.dump(utils.get_saved_categories() + [cat], open(Paths.CATEGORY_JSON, "w", encoding='utf-8'))
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

        The function will check nearby cells recursively until it finds the headers.
        Recursion will stop when the header is found or when the the offset is 5 cells away from the initial row/column.
        '''
        em = ExcelManager().set_active_sheet(Paths.INPUT_FOLDER + "\\" + file_name)
        
        col_max_offset = 2
        row_max_offset = 6
        
        col_range = \
            [i for i in range(header_col_index, header_col_index - col_max_offset, -1) if i >= 0] + \
            [i for i in range(header_col_index + 1, header_col_index + col_max_offset)] #range(max(0, header_col_index - col_max_offset), header_col_index + col_max_offset)  
        row_range = \
            [i for i in range(initial_row, initial_row - row_max_offset, -1) if i > 0] + \
            [i for i in range(initial_row + 1, initial_row + row_max_offset)]

        for i in row_range:
            for j in col_range:

                valid = True
                col = j
                row = i

                debug_list = [] # debug feature

                for name in headers:
                    value = em.read_cell(row, col)
                    
                    debug_list.append(value) # debug feature

                    if not value == name:
                        if col > j:
                            utils.log(f"Header Validation Failed halfway: {value} != {name}", "warning")
                        valid = False
                        break
                    col += 1
                if valid:
                    if row != initial_row:
                        utils.log(f"Headers were found at line {row}, Not in {initial_row} as specified.", "warning")
                    initial_row = row
                    return True
                utils.log(f"Header Validation Failed for {file_name} with format {format}\n extracted headers: {debug_list} ", "debug")
                continue
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

        utils.log(f"func date_ready: Invalid date format. Please use '-' or '/' as separators...\n got the value: {date} of type {type(date)}.", "error")
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
    def pretty_print(lst: list, const: int = 6, col_space: int = 27) -> None:
        """
        The function prints the given list in a rectangle shaped pattern.
        The elements are indexed from 0 to n - 1.
        The rectangle is set to have a maximun of @const elements per column.
        The col_space argument indicates the the space between each column.
        """
        n = len(lst)
        m = 1 + n // const
        for i in range(0, const):
            for j in range(0, m):
                index = i + const*j
                if index >= len(lst):
                    break
                print(f"{lst[index]:{col_space}s}", end="")
            print()


    @staticmethod
    def validate_constants() -> Union[str, bool]:
        """
        check if all the category values under USER_DEFINED_CATEGORIES exist in the categories.json file.
        """
        from Constants import GeneralPlot

        # Read the categories from the JSON file
        try:
            with open(Paths.CATEGORY_JSON, encoding='utf-8') as file:
                categories = json.load(file)
        except FileNotFoundError:
            return True  # file not present on this environment — skip validation
        # Check if all user-defined categories exist in the JSON file
        for category in GeneralPlot.USER_DEFINED_CATEGORIES:
            if category not in categories:
                return f"Category '{category}' not found in categories.json - Check (USER_DEFINED_CATEGORIES) in Constants.py"


        return True

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
        color_coded_df = pd.DataFrame(index=indexes, columns=columns)
        for _, row in file_df.iterrows():
            last_update = row["Last_update"]
            date = row["Date"]
            format_name = row["Format"]
            card_number = row["Card_Number"]
            col_name =  format_name + " | " + card_number
            df.at[date, col_name] = last_update
            
            test_df = utils.card_charge_validation(datetime.strptime(row["Date"], "%B, %Y"))
            status_series = test_df.loc[test_df['CardID'] == card_number, 'Status']

            if not status_series.empty:
                result = status_series.values[0]
            else:
                result = None  # or handle as needed
            
            color_coded_df.at[date, col_name] = result
        return df, color_coded_df

    @staticmethod
    def create_html_with_colored_dates(df: pd.DataFrame, 
                                       color_coded_df: pd.DataFrame,
                                       output_file_path: str='output.html'):
        """
        
        @param df: DataFrame with dates and values (columns are card names and rows are dates as seen in the html).
        @param color_coded_df: DataFrame with the same index and columns as df, but with color-coded status values.
        @param output_file_path: Path to save the generated HTML file.
        """
        from jinja2 import Template
        from Configurations.Formats import Formats
        from database import DataBase
        from Constants import BANK_CARD_NUMBER

        # 1. Get all untagged transaction names from the DB
        untagged_transactions, desc = DataBase().get_untagged(table="BankTransactions")

        # 2. Build a lookup for untagged-match cells (for both empty and not-verified date cells)
        from datetime import datetime

        untagged_match_cells = dict()  # (row_idx, col) -> (date, value, cell_type)
        for col in df.columns:  #columns are string combined of "Format Name | Card Number"
            if " | " in col:
                format_name, card_number = col.split(" | ")
                format_dict = Formats.FORMATS.get(format_name, {})
                card_names_dict = format_dict.get("Transaction Names", {})
                if card_number in card_names_dict:
                    possible_names = set(card_names_dict[card_number])
                    for idx in df.index:
                        value = df.at[idx, col]
                        status = color_coded_df.at[idx, col] if idx in color_coded_df.index and col in color_coded_df.columns else None
                        # Parse the month and year from the table row index (e.g. "November, 2023")
                        try:
                            row_month_year = datetime.strptime(str(idx), "%B, %Y")
                        except Exception:
                            continue
                        # Find a matching untagged transaction for this card/format/date
                        for row in untagged_transactions:
                            name = row[desc.index('Name')]
                            date_str = row[desc.index('Date')] if 'Date' in desc else None
                            val = row[desc.index('Out')] if 'Out' in desc else None
                            if name in possible_names and date_str:
                                try:
                                    trans_date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S").date()
                                except Exception:
                                    continue
                                # Match month and year
                                if trans_date.month - 1 == row_month_year.month and trans_date.year == row_month_year.year:
                                    # If cell is empty (missing file)
                                    if pd.isna(value) or value == "" or value is None:
                                        untagged_match_cells[(idx, col)] = (trans_date, val, name, "missing")
                                        # In case two of more cards fit the same transaction name, we want to show one for each avaliable card
                                        # So we remove the first match to allow another match with another fitting transaction name
                                        untagged_transactions.remove(row)
                                        break
                                    # If cell has a date and is Not Verified
                                    elif (
                                        isinstance(value, str)
                                        and len(value) == 10
                                        and '-' in value
                                        and (status == 'Not Verified')
                                    ):
                                        untagged_match_cells[(idx, col)] = (trans_date, val, name, "not_verified")
                                        break

                            name = row[desc.index('Name')]
                            date_str = row[desc.index('Date')] if 'Date' in desc else None
                            val = row[desc.index('Out')] if 'Out' in desc else None
                            if name in possible_names and date_str:
                                try:
                                    trans_date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S").date()
                                except Exception:
                                    continue
                                # Match month and year
                                if trans_date.month - 1 == row_month_year.month and trans_date.year == row_month_year.year:
                                    # If cell is empty (missing file)
                                    if pd.isna(value) or value == "" or value is None:
                                        untagged_match_cells[(idx, col)] = (trans_date, val, name, "missing")
                                        break
                                    # If cell has a date and is Not Verified
                                    elif (
                                        isinstance(value, str)
                                        and len(value) == 10
                                        and '-' in value
                                        and (status == 'Not Verified')
                                    ):
                                        untagged_match_cells[(idx, col)] = (trans_date, val, name, "not_verified")
                                        break
        
                elif BANK_CARD_NUMBER != card_number:   # Bank formats will not trigger the following warning
                    utils.log(f"Column '{col}' does not have a valid card number in the format dictionary, skipping...", "warning")
            else:
                utils.log(f"Column '{col}' does not contain ' | ' separator, skipping...", "warning")

        # 3. Legend text
        legend_text = {
            "green": "Green - file for the card and date was parsed and verified.",
            "yellow": "Yellow - file for the card was parsed but not verified or not applicable for verification.",
            "red": "Red - non-existent file for the relevant card and date.",
            "blue-missing": "Blue - untagged transaction(s) found for this card and date (missing file, shows date and value).",
            "blue-not-verified": "Light Blue - untagged transaction(s) found for this card and date (file not verified, shows date and value)."
        }

        # 4. HTML template (add .untagged-match-missing and .untagged-match-not-verified and legend)
        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                table {
                    border-collapse: collapse;
                    width: 100%;
                    overflow-x: auto;
                }
                th, td {
                    border: 1px solid black;
                    padding: 10px;
                    text-align: center;
                    font-size: 14px;
                }
                th {
                    background-color: #f2f2f2;
                    font-weight: bold;
                }
                tr:nth-child(even) {
                    background-color: #f9f9f9;
                }
                .verified {
                    background-color: #c2f0c2 !important; /* Green */
                }
                .not-verified {
                    background-color: #fff7b2 !important; /* Yellow */
                }
                .other-status {
                    background-color: #ffb3b3 !important; /* Red */
                }
                .untagged-match-missing {
                    background-color: #b3d1ff !important; /* Blue */
                    font-size: 12px;
                }
                .untagged-match-not-verified {
                    background-color: #d1eaff !important; /* Light Blue */
                    font-size: 12px;
                }
                .legend-container {
                    margin: 20px 0 30px 0;
                    padding: 10px 20px;
                    background: #f8f8f8;
                    border-radius: 8px;
                    width: fit-content;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
                }
                .legend-title {
                    font-weight: bold;
                    margin-bottom: 8px;
                }
                .legend-item {
                    display: flex;
                    align-items: center;
                    margin-bottom: 4px;
                    font-size: 14px;
                }
                .legend-color {
                    width: 18px;
                    height: 18px;
                    display: inline-block;
                    margin-right: 10px;
                    border: 1px solid #aaa;
                    border-radius: 3px;
                }
                .legend-green { background: #c2f0c2; }
                .legend-yellow { background: #fff7b2; }
                .legend-red { background: #ffb3b3; }
                .legend-blue-missing { background: #b3d1ff; }
                .legend-blue-not-verified { background: #d1eaff; }
            </style>
        </head>
        <body>
            <h1 style="text-align: Center"> File Organizer</h1>
            <div class="legend-container">
                <div class="legend-title">Legend:</div>
                <div class="legend-item"><span class="legend-color legend-green"></span>{{ legend.green }}</div>
                <div class="legend-item"><span class="legend-color legend-yellow"></span>{{ legend.yellow }}</div>
                <div class="legend-item"><span class="legend-color legend-red"></span>{{ legend.red }}</div>
                <div class="legend-item"><span class="legend-color legend-blue-missing"></span>{{ legend['blue-missing'] }}</div>
                <div class="legend-item"><span class="legend-color legend-blue-not-verified"></span>{{ legend['blue-not-verified'] }}</div>
            </div>
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
                            {% for col in columns %}
                                {% set value = row[col] %}
                                {% set status = color_coded_df.at[index, col] %}
                                {% set is_date = false %}
                                {% if value is string and value|length == 10 and '-' in value %}
                                    {% set is_date = true %}
                                {% endif %}
                                {% set cell_key = (index, col) %}
                                {% if cell_key in untagged_match_cells %}
                                    {% set match = untagged_match_cells[cell_key] %}
                                    {% if match[3] == "missing" %}
                                        <td class="untagged-match-missing">
                                            <div>
                                                <b>Missing file</b><br>
                                                <span style="color:#333;">
                                                    Name: {{ match[2] if match[2] else "?" }}<br>
                                                    Value: {{ match[1] if match[1] else "?" }}<br>
                                                    Transactions Date: {{ match[0] if match[0] else "?" }}<br>
                                                </span>
                                            </div>
                                        </td>
                                    {% elif match[3] == "not_verified" %}
                                        <td class="untagged-match-not-verified">
                                            <div>
                                                <b>Not Verified</b><br>
                                                <span style="color:#333;">
                                                    Name: {{ match[2] if match[2] else "?" }}<br>
                                                    Value: {{ match[1] if match[1] else "?" }}<br>
                                                    Transactions Date: {{ match[0] if match[0] else "?" }}<br>
                                                    File Update Date: {{ value if value else "?" }}<br>
                                                </span>
                                            </div>
                                        </td>
                                    {% endif %}
                                {% else %}
                                    <td class="{% if status == 'Verified' %}verified{% 
                                        elif status == 'Not Verified' or is_date %}not-verified{% 
                                        else %}other-status{% endif %}">
                                        {{ value }}
                                    </td>
                                {% endif %}
                            {% endfor %}
                        </tr>
                    {% endfor %}
                </tbody>
            </table>
        </body>
        </html>
        """

        # 5. Render template
        template = Template(html_template)
        rendered_html = template.render(
            data=df,
            columns=df.columns,
            pd=pd,
            color_coded_df=color_coded_df,
            legend=legend_text,
            untagged_match_cells=untagged_match_cells
        )

        with open(output_file_path, 'w', encoding='utf-8') as html_file:
            html_file.write(rendered_html)

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

        tag = soup.find('td', class_='Recent Monthly Average')
        if data['Recent Monthly Average'] < 0:
            tag.string = f"({abs(data['Recent Monthly Average']):,.2f}) ₪"
        else:
            tag.string = f"{data['Recent Monthly Average']:,.2f} ₪"

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

        for _, row in data["transactions"].sort_values(by='Date', ascending=False).iterrows():
            #date = datetime.strptime(row['Date/Executed_Date'], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
            #sub_tag.string = f"{row['Name']}\n{row['Final_Value']}\n{date}\n{row['Extra_Info']}"
            transaction_text = ""
            if row['Description'] is not None and row['Description'] != "":
                transaction_text += f"{row['Description']}"
            else:
                transaction_text += f"{row['Name']}"   
            
            lst_element = create_list_tag(transaction_text, row['Date'], row['Final_Value'])
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
        if os.path.exists(Paths.AUTO_TAGGER_JSON):
            with open(Paths.AUTO_TAGGER_JSON, 'r', encoding='utf-8') as f:
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


        with open(Paths.AUTO_TAGGER_JSON, 'w', encoding='utf-8') as f:
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
                DataBase().set_category(table_name=row['TableName'], id=row['ID'], category=res)
                logs += f"transaction {utils.heb_conversion(row['Name'])} ({row['TableName']}) ({row['ID']}) was tagged to {utils.heb_conversion(res)}\n"

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

        personal_conf_dict = json.load(open(Paths.PERSONAL_CONFIG, encoding='utf-8'))
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
        json.dump(personal_conf_dict, open(Paths.PERSONAL_CONFIG, "w", encoding='utf-8'))
        return True

    @staticmethod
    def change_an_existing_category_name():
        """
        The function allows the user to change an existing category name.
        The function will ask the user to choose a category name to replace, and then 
        to choose a new name for it
        """
        current_category_list = utils.get_saved_categories()
        index, sub_category_list = utils.typer_template_menu(current_category_list, msg = "Please choose a category name to replace:", sort = True)
        chosen_category_to_replace = sub_category_list[index]
        
        while True:
            index, sub_category_list = utils.typer_template_menu(options=current_category_list + ["「Choose a new category name」"], 
                                                        msg= "Pick a category from the existing list or choose to create a new one:",
                                                        sort=True,
                                                        )
            new_chosen_category = sub_category_list[index]
            if new_chosen_category == "「Choose a new category name」":
                new_chosen_category = utils.parse_str_from_user(message=f"Please insert a new name for category {(chosen_category_to_replace)}",)
            
            if chosen_category_to_replace == new_chosen_category:
                utils.log("You have chosen the same category name to replace, please choose a different one", 'system')
                continue
            
            if new_chosen_category in ["「Skip」", "「Back to menu」"]:
                utils.log("Choose a valid catregory name...", 'system')
                continue
            
            break
        
        from database import DataBase
        DataBase().replace_category(frm=chosen_category_to_replace, to=new_chosen_category)
        DataBase().commit_changes()
        new_category_lst = current_category_list.copy() 
        new_category_lst.remove(chosen_category_to_replace)
        new_category_lst.append(new_chosen_category)
        utils.update_categories_file(new_category_lst, append=False)
        utils.log(f"({chosen_category_to_replace}) has been replaced by ({new_chosen_category})")

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

    @staticmethod
    def accumulate_cash_Balance() -> int:
        """
        The function will sum all Cash transaction:
        1. transactions created by the user, queried in the Cash Transsaction table
        2. Withdrawlls specified in the Bank Transactions table
            (can be reognized by the Category name "withdrawal" in the Bank Transactions table)
        The function will return the total cash balance.
        """
        from database import DataBase
        from Constants import ReservedNames

        bank_withdrawals_df = DataBase().get_transactions_by_category(ReservedNames.WHITDRAWAL_CATEGORY)

        total_cash = 0

        if not bank_withdrawals_df.empty:
            total_cash += bank_withdrawals_df['Out/Transaction_value'].sum()
    
        cash_df = DataBase().get_Cash_Transactions()
      
        if not cash_df.empty:
            # utils.log(f"Cash Transactions found:\n{utils.df_to_markdown(cash_df)}", 'system')
            total_cash += cash_df['Amount'].sum()
            

        return total_cash
    
    @staticmethod
    def get_cash_transactions(datetime: datetime | None = None) -> pd.DataFrame:
        """
        The function will return all Cash transaction:
        1. transactions created by the user, queried in the Cash Transsaction table
        2. Withdrawlls specified in the Bank Transactions table
            (can be reognized by the Category name "withdrawal" in the Bank Transactions table)
        Given a datetime object which is not None, the function will filter the transactions to only include those from the specified month and year.
        The function will return a data frame with all queried columns
        """
        from database import DataBase
        from Constants import ReservedNames
        from src_utils.calculations import SimpleMath

        bank_withdrawals_df = DataBase().get_transactions_by_category(ReservedNames.WHITDRAWAL_CATEGORY)
        # Note: Only withdrawls are queried here, therefore, process_prices function is not needed.
        # Convert 'Date/Executed_Date' to datetime before filtering
        #utils.log(utils.df_to_markdown(bank_withdrawals_df), 'system')
        bank_withdrawals_df['Date/Executed_Date'] = pd.to_datetime(bank_withdrawals_df['Date/Executed_Date'], errors='coerce')
        bank_withdrawals_df = bank_withdrawals_df[
            (bank_withdrawals_df['Date/Executed_Date'].dt.month == datetime.month) &
            (bank_withdrawals_df['Date/Executed_Date'].dt.year == datetime.year)
        ]
        #utils.log(datetime.strftime("Filtering cash transactions for: %B, %Y"), 'system')
        bank_withdrawals_df = bank_withdrawals_df[['ID','Date/Executed_Date', 'Out/Transaction_value', 'Name', 'Category']]
        bank_withdrawals_df = bank_withdrawals_df.rename(columns={'Date/Executed_Date': 'Execution_Date',
                                                                  'Out/Transaction_value': 'Amount',})

        cash_df = DataBase().get_Cash_Transactions(datetime)
        #convet date column to datetime
        cash_df['Execution_Date'] = pd.to_datetime(cash_df['Execution_Date'], errors='coerce')

        cash_df = cash_df[['ID', 'Execution_Date', 'Amount', 'Name', 'Category']]

        combined_cash_df = pd.concat([cash_df, bank_withdrawals_df], ignore_index=True)
        combined_cash_df = combined_cash_df.sort_values(by='Execution_Date', ascending=False).reset_index(drop=True)

        # Convert 'Amount' column to numeric
        combined_cash_df['Amount'] = pd.to_numeric(combined_cash_df['Amount'], errors='coerce')

        return combined_cash_df

    @staticmethod
    def df_to_markdown(df: pd.DataFrame) -> str:
        """
        Converts a DataFrame to markdown format while properly handling Hebrew text.
        Applies heb_conversion to all string values to ensure correct RTL display.
        """
        # Create a copy to avoid modifying the original DataFrame
        df_display = df.copy()
        
        # Convert all object/string columns that may contain Hebrew
        for col in df_display.select_dtypes(include=['object']):
            df_display[col] = df_display[col].apply(lambda x: utils.heb_conversion(str(x)) if pd.notna(x) else x)
            
        # Convert column names that may contain Hebrew
        df_display.columns = [utils.heb_conversion(str(col)) for col in df_display.columns]
        
        return df_display.to_markdown()

    @staticmethod
    def generate_date(date_str: str, date_format: str) -> datetime:
        """
        Convert string date to datetime with validation for dates after 2020.
        
        Args:
            date_str: Date string to convert
            date_format: Expected format of date_str (e.g. "%d/%m/%Y")
            
        Returns:
            datetime object if valid
            
        Raises:
            Logs error and exits if date is invalid or before 2020
        """
        try:
            # Convert to datetime
            date = datetime.strptime(date_str, date_format)
            
            # Validate year
            if date.year < 2020:
                utils.log(f"Date {date_str} is before 2020. Only dates from 2020 onwards are allowed.", "error")
            
            return date
            
        except ValueError as e:
            utils.log(f"Invalid date format: {date_str}\nExpected format: {date_format}\nError: {str(e)}", "error")
        except Exception as e:
            utils.log(f"Error processing date: {date_str}\nError: {str(e)}", "error")


    @staticmethod
    def card_charge_validation(processed_df: pd.DataFrame, date: datetime) -> pd.DataFrame:
        """
        @prama processed_df: The function will receive the processed monthly transactions data frame.  
        @param date: monthly date inserted by the user, the date will be used to query the bank transactions in the following month.

        The function will try and validate all credit card charges present in the given month by comparing
        the total sum of all transaction executed withing a specific card with a bank transaction in the following month.
        match will be found when the price of the summed  transaction will be equal to a bank transaction in the following month
        and also the bank transaction main name will match the possible names specified by the user.

        The function will return a data frame with the following columns:
        - CardID: The card identifier
        - Status: Verified / Not Verified
        - Out/Transaction_value: The total sum of all transactions executed with the given card in the given month

        """
        # ----- New Code Here -------------------------------------
        from database import DataBase
        from Constants import Settings, Trans_Type

        wip_df = processed_df.copy()

        # Define the nan values for all bank transaction to a valid value: "Bank" for easier use
        wip_df['CardID'] = wip_df.apply(lambda row: 'Bank' if row['TableName'] == 'BankTransactions' else row['CardID'], axis=1)
        # Group by and drop irellevant columns
        wip_df = wip_df[['CardID', 'Final_Value']].groupby('CardID').sum().reset_index()
        wip_df['Status'] = False

        bank_df = DataBase().get_Bank_Transactions(utils.next_month(date).month,
                                                    utils.next_month(date).year)

        for _, row_card in wip_df.iterrows():
            # Skip the row that summes all bank transactions because validation is not required for it
            if row_card['CardID'] == 'Bank':
                continue
            for _, row_bank in bank_df.iterrows():
                card_charge_sum = abs(round(row_card['Final_Value'], 2))
                card_id = row_card['CardID']
                possible_bank_transaction_match =  round(row_bank['Out'], 2)
                if card_charge_sum == possible_bank_transaction_match:
                    wip_df.loc[wip_df['CardID'] == card_id, 'Status'] = True
                    if row_bank['Category'] == CC_CHARGE_CATEGORY_NAME:
                        break

                    if utils.template_menu(['No', 'Yes'], f"App found this transaction to be a credit card:\n\
                                        {row_bank}\n Do you Agree?"):
                        DataBase().set_category('BankTransactions', row_bank['ID'], CC_CHARGE_CATEGORY_NAME)
                        DataBase().commit_changes()
                        break
                    else:
                        utils.log('ignored...', 'system')
        
        if Settings.DEBUG:
            for index, row in wip_df.iterrows():
                if row['Status'] == 'Not Verified':
                    # Perform your action here
                    utils.log(f"information for card at index: {index},\n {wip_df[wip_df['CardID'] == row['CardID']].to_markdown()}", 'debug')
        
        return wip_df

        # format_name, card_number = col.split(" | ")
        # format_dict = Formats.FORMATS.get(format_name, {})
        # card_names_dict = format_dict.get("Transaction Names", {})
   

    @staticmethod
    def handle_withdrawals() -> Tuple[bool, str, pd.DataFrame]:
        """
        The function is responsible for handling withdrawals transactions present in both
        Bank Transactions and Card Transactions.
        The function will match transactions from both tables.
        Withdrawals transactions in Card Transactions are identified by a ReservedName "משיכת מזומנים"
        and the corresponding transaction in Bank Transactions is identified by the Card charge name, the same price, and charge month
        and will be tagged with the category "withdrawal".
        withdrawals are not calculated in the Analysis phase.
        
        The function will return a tuple with the following values:
        - bool: True is returned if no unpaired witdrawals were found, and False if withdrawals with no match were found.
        - str: A message indicating the result of the operation.
        - pd.DataFrame: 
        """
        from database import DataBase
        from Constants import ReservedNames
        from Configurations.Formats import Formats

        # Get all card transactions with the reserved name "משיכת מזומנים"
        card_withdrawals_df = DataBase().get_transactions_by_name(table_name="CardTransactions", name=ReservedNames.WITHDRAWAL)
        if card_withdrawals_df.empty:
            return True, "No Withdrawal transactions found", pd.DataFrame()
        
        #utils.log(f"{utils.df_to_markdown(card_withdrawals_df)}")

        # Remove transactions that have already been tagged as withdrawals
        card_withdrawals_df = card_withdrawals_df[card_withdrawals_df['Category'] != ReservedNames.WHITDRAWAL_CATEGORY]
        
        # Remove unnecessary columns
        card_withdrawals_df = card_withdrawals_df[['ID', 'CardID', 'Executed_Date', 'Transaction_Value']]

        total_matched_transactions_df = pd.DataFrame()

        for _, row in card_withdrawals_df.iterrows():
            # extract all the keys represting card numbers in the Transaction Names dictionary for each format dictionary
            possible_bank_transaction_names = [name for format_config in Formats.FORMATS.values() for card_id, names in format_config["Transaction Names"].items() for name in names if card_id == row['CardID']]
        
            # Get all bank transactions for the month of the first withdrawal
            transaction_date = datetime.strptime(row['Executed_Date'], "%Y-%m-%d %H:%M:%S")
            bank_transactions_df = DataBase().get_Bank_Transactions(transaction_date.month, transaction_date.year)

            #check if transaction matches in the bank_transactions_df
            matched_transactions_df = bank_transactions_df[
                (bank_transactions_df['Out'] == row['Transaction_Value']) &
                (bank_transactions_df['Name'].isin(possible_bank_transaction_names))
            ]
            
            #utils.log(f"{utils.df_to_markdown(matched_transactions_df)}")

            if matched_transactions_df.empty:
                return False, f"No matching transactions found for withdrawal ID: {row['ID']}, CardID: {row['CardID']}, Executed Date: {row['Executed_Date']}", pd.DataFrame()

            # if the size of the df is larger than 1, it means that there are multiple transactions that match the withdrawal.
            # Only the first one will be matched, and the rest will be ignored.
            # This case will happen when there were more than one withdrawal of the same amount in the same month.
            # The ignored transaction will be matched in the next iteration.
            if matched_transactions_df.shape[0] > 1:
                utils.log(f"Multiple matching transactions found for withdrawal ID: {row['ID']}, CardID: {row['CardID']}, Executed Date: {row['Executed_Date']}. This will trigger incorrect tagging for a case where there are more than one withdrawal per month.", 'warning')
                matched_transactions_df = matched_transactions_df.head(1)

            # this can probably be romoved
            if matched_transactions_df.empty:
                continue  # matching transactions were already matched before, skip to the next withdrawal

            # The set category function receives a ID of type int to set\
            else:
                # x is an integer holding the id of the first row in the df
                DataBase().set_category('CardTransactions', int(row['ID']), ReservedNames.WHITDRAWAL_CATEGORY)
                DataBase().set_category('BankTransactions', int(matched_transactions_df['ID'].iloc[0]), ReservedNames.WHITDRAWAL_CATEGORY)
                DataBase().set_description('CardTransactions', int(row['ID']),f"Matched with Bank Transaction ID: {matched_transactions_df['ID'].iloc[0]}")
                DataBase().set_description('BankTransactions', int(matched_transactions_df['ID'].iloc[0]), f"Matched with Card Transaction ID: {int(row['ID'])}")
                DataBase().commit_changes()
                total_matched_transactions_df = pd.concat([total_matched_transactions_df, matched_transactions_df], ignore_index=True)


        if total_matched_transactions_df.empty:
            return True, "Witdrawals Check Executed, None found", total_matched_transactions_df
        else:
            return True, "All withdrawals matched successfully", total_matched_transactions_df
        

    @staticmethod
    def exclude_transaction() -> None:
        """
        Lets the user choose a table and transaction ID to exclude.
        Sets category and description to 'EXCLUDE'.
        """
        tables = ['BankTransactions', 'CardTransactions']
        result_table = utils.template_menu(tables, 'Please choose a table to exclude a transaction from:')
        # choose a valid id and if not valid try again until user inserts -1
        result_id = input(f"Please insert the ID of the transaction you want to exclude from {tables[result_table]}: ")
        while not result_id.isdigit() or int(result_id) < 0:
            if result_id == '-1':
                return
            result_id = input("Invalid ID. Please insert a valid ID or -1 to exit: ")
        
        from database import DataBase
        from Constants import ReservedNames

        DataBase().set_category(tables[result_table], int(result_id), ReservedNames.EXCLUDED_CATEGORY)
        DataBase().commit_changes()
        utils.log(f"Transaction {result_id} from table {tables[result_table]} has been excluded.", 'system')


    @staticmethod
    def extract_payments_data(df: pd.DataFrame) -> pd.DataFrame:
        """
        extract the following data from the spending df recived:
        1. Transaction Name
        2. Current Payment
        3. Total transaction amount
        4. number of payments
        5. current payment number

        payments are identified by the data in the 'Extra_Info' column, which should contain the following string:
        'תשלום b  מתוך a'
        where a is the total number of payments and b is the current payment number.
        """
        import re

        records = []

        # Iterate through each row in the DataFrame
        for _, row in df.iterrows():
            extra_info = row['Extra_Info']
            if pd.isna(extra_info):
                continue
            # Use regex to find the payment information
            match = re.search(r'תשלום\s+(\d+)\s+מתוך\s+(\d+)', extra_info)
            if match:
                current_payment = int(match.group(1))
                total_payments = int(match.group(2))
                
                # Append the extracted data to the new DataFrame
                records.append({
                    'Transaction Name': row['Name'],
                    'Current Payment': abs(row['Final_Value']),
                    'Total Amount': row['Charge_Value'],
                    'Number of Payments': total_payments,
                    'Current Payment Number': current_payment})
            else:
                continue
        
        return pd.DataFrame(records)


    @staticmethod
    def parse_date_from_user(return_type: str = "str", day: bool = True) -> str | datetime:
        """
        Asks the user for a date and returns it as a string or datetime object.
        The date is returned in "%Y-%m-%d" format (string) or as a datetime object.
        Args:
            return_type (str): "str" for string output, "datetime" for datetime object.
            day (bool): If True, day is also parsed. If False, only month and year are parsed.
                day will be set as 1 for Arg day=False.
        Returns:
            str or datetime: The date in the requested format.
        """
        while True:
            try:
                if day:
                    date_input = input("Please enter a date (YYYY-MM-DD): ")
                    date_obj = datetime.strptime(date_input, "%Y-%m-%d")
                else:
                    date_input = input("Please enter a date (YYYY-MM): ")
                    date_obj = datetime.strptime(date_input, "%Y-%m")
                
                if return_type == "str":
                    return date_obj.strftime("%Y-%m-%d") if day else date_obj.strftime("%Y-%m")
                elif return_type == "datetime":
                    return date_obj
                else:
                    utils.log("Invalid return_type specified. Use 'str' or 'datetime'.", "error")
            except ValueError:
                utils.log("Invalid date format. Please try again.", "system")

    @staticmethod
    def delete_cash_transaction_by_id() -> bool:
        """
        The function will ask the user for an integer, representing a valid ID from
        the Cash Transactions table, and will delete the transaction with the given ID.
        The input will be asked until a valid input was received.
        the function will return True if the transaction was deleted successfully, and False otherwise.
        """
        from database import DataBase

        while True:
            user_input = input("Please enter the ID of the Cash Transaction to delete (or -1 to exit): ")
            if user_input == '-1':
                return False
            if not user_input.isdigit() or int(user_input) <= 0:
                utils.log("Invalid input. Please enter a positive integer ID or -1 to exit.",'system')
                continue
            
            transaction_id = int(user_input)
            if not DataBase().is_cash_transaction_exists(transaction_id):
                print(f"No Cash Transaction found with ID: {transaction_id}. Please try again.")
                continue
            
            # Confirm deletion
            confirm = utils.template_menu(['no', 'yes'], "Are you sure you want to delete the Cash Transaction with ID {transaction_id}? This action cannot be undone. (yes/no): ")

            if confirm == 1:  # User confirmed deletion
                DataBase().delete_cash_transaction(transaction_id)
                DataBase().commit_changes()
                utils.log(f"Cash Transaction with ID {transaction_id} has been deleted.", 'system')
                return True
            else:
                utils.log("Deletion cancelled. No changes made.", 'system')
                return False

    @staticmethod       
    def parse_str_from_user(message: str = "Please enter a non-empty string: ") -> str:
        """
        Asks the user for a non-empty string input.
        Returns the input string.
        """
        while True:
            user_input = input(message).strip()
            if user_input:
                return user_input
            else:
                utils.log("Input cannot be empty. Please try again.", "system")