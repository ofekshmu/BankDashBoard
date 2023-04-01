from Constants import Settings, Local


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
                log_st += f"{70*'-'}\n[ERROR]: {msg}{70*'-'}\n"
            case 'db':
                write = True
                log_st += f"[DataBase]: {msg}"
            case '':
                write = True
                log_st += f'{msg}'
            case 'warning':
                write = True
                log_st += f"<[WARNING]>: {msg}"
            case other:
                utils.log(msg="Key error in function 'temp'", category='error')

        if write:
            f = open("Log_file.txt", 'a', encoding="utf-8")
            f.write(log_st + "\n")
            f.close()
            print(log_st, end=e)

        if category == "error":
            raise ValueError("\nBreaking code...")
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
        lst = name.split()

        res = " ".join([x[::-1] if utils.has_hebrew(x) else x for x in lst][::-1])
        return res

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
                      earning,
                      monthly_balance: int,
                      end_month_balance: int,
                      gas_stats):
        import bs4
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
        div['class'] = 'container'
        table = soup.new_tag("table")
        table['class'] = 'list'
        div.append(table)

        soup.body.insert(5, div)

        for item in spendings:
            row = soup.new_tag("tr")
            row['class'] = 'num'
            for i in item:
                cell = soup.new_tag("td")
                cell.string = str(i)
                row.append(cell)
            table.append(row)

        # ----------
        div = soup.new_tag("div")
        title = soup.new_tag("h3")
        title.string = "Gas info"
        div.append(title)

        lst = gas_stats.__repr__().split("\n")[:-1]
        for stat in lst:
            p = soup.new_tag("p")
            p.string = stat
            div.append(p)

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
