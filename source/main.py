from AppManager import AppManager
from Constants import log
from datetime import datetime


def main():
    log(msg=f"{30*'#'} " + datetime.now().strftime("%m/%d/%Y, %H:%M:%S") + f" {30*'#'}", category="system")
    myApp = AppManager()
    myApp.load_data()
    myApp.plot_data()


if __name__ == "__main__":
    main()
