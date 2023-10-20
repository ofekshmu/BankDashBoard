from AppManager import AppManager
from src_utils.utils import utils
from datetime import datetime


def main():
    utils.log(msg=f"\n{40*'#'} " + datetime.now().strftime("%m/%d/%Y, %H:%M:%S") + f" {40*'#'}")
    myApp = AppManager()
    myApp.menu()


if __name__ == "__main__":
    main()
