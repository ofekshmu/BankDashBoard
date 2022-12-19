from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By

class MySelenium:
    def __init__(self):
        # Initialize the Selenium webdriver for Edge
        self.driver = webdriver.Chrome(ChromeDriverManager().install())

    def start(self, user_name: str, password: str):
        # Open www.google.com in the Edge browser
        self.driver.get("https://www.leumi.co.il/")
        self.driver.maximize_window()
        self.driver.find_element(By.XPATH, "//a[contains(text(), 'כניסה לחשבונך')]").click()
        self.driver.find_element(By.XPATH, "//input[@maxlength='7']").send_keys(user_name)
        self.driver.find_element(By.XPATH, "//input[@placeholder='סיסמה']").send_keys(password)
        while True:
            try:
                self.driver.find_element(By.XPATH, "//button[@type='submit' and @aria-disabled='false' and text()='כניסה לחשבון']").click()
                break
            except Exception:
                pass
        self.driver.find_element(By.XPATH, "//a[@role='menuitem' and @class='ng-tns-c122-0 ng-star-inserted' and @href='javascript:void(0)']").click()

        while True:
            try:
                self.driver.find_element(By.XPATH, "//a[@role='menuitem'][@class='ng-tns-c122-0']").click()
                break
            except Exception:
                pass

        self.driver.find_element(By.XPATH, "//button[@class='tw-text-primary excl2' and @title='יצוא לאקסל']").click()
        self.driver.find_element(By.XPATH, "//button[@class='ts-btn btn btn-primary' and contains(text(), 'המשך')]").click()

