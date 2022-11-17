from AppManager import AppManager


def main():
    myApp = AppManager()
    myApp.load_data()
    myApp.plot_data()


if __name__ == "__main__":
    main()
