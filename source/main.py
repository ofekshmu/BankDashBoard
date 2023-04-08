from AppManager import AppManager
from src_utils.utils import utils
from datetime import datetime
from src_utils.utils import utils
from front.Graphics import Graphics


def main():
    utils.log(msg=f"\n{40*'#'} " + datetime.now().strftime("%m/%d/%Y, %H:%M:%S") + f" {40*'#'}")
    myApp = AppManager()
    myApp.menu()
    myApp.validate()
    myApp.analysis()


if __name__ == "__main__":
    main()
