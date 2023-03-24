from Constants import Settings


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
        if category == 'warning':
            utils.warning_halt()

    @staticmethod
    def name_he(name: str):
        try:
            i = name[::-1].index(' ')
            j = len(name) - i
            return name[:j][::-1] + " " + name[j:]
        except ValueError:
            return name

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
    def generate_html(monthly_balance: int):
        import bs4
        # load the file
        with open("source\html\Base_template.html") as inf:
            txt = inf.read()
        soup = bs4.BeautifulSoup(txt)

        sub_titles_div = soup.new_tag('div')

        balance_h2 = soup.new_tag('h2')
        balance_h2.string = f'Balance: {monthly_balance}'

        temp_h2 = soup.new_tag('h2')
        temp_h2.string = 'Temp: x'

        sub_titles_div.append(balance_h2)
        sub_titles_div.append(temp_h2)

        sub_titles_div.attrs['style'] = 'text-align: center;'

        soup.body.insert(0, sub_titles_div)
        
        with open("source\html\output.html", "w") as outf:
            outf.write(bs4.BeautifulSoup.prettify(soup))