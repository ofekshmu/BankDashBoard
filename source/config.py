import json


class local:
    '''
    Include all local enviroment related valriables
    '''
    XLSX_PATH = 'C:/Users/ofeks/OneDrive/Temporary/BankProject/Inputs'
    Personal_PATH = 'C:/Users/ofeks/OneDrive/Temporary/BankProject/personal information/personal_config.json'
    EXTENSION = '.xls'


class personal:
    '''
    All constants in this class are taken from the personal_config.json
    which is only avaliable in the local repository.
    '''
    BANK_ACC = json.load(open(local.Personal_PATH))['bank_account']


class Messaging:
    DEBUG = True
    SYSTEM = True
