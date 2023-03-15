from AppManager import AppManager
from Constants import log
from datetime import datetime


def main():
    log(msg=f"\n{40*'#'} " + datetime.now().strftime("%m/%d/%Y, %H:%M:%S") + f" {40*'#'}")
    myApp = AppManager()
    myApp.load_data()
    myApp.plot_data()


if __name__ == "__main__":
    main()
