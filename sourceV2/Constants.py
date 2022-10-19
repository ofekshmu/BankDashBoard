class Settings:
    DEBUG = True
    SYSTEM = True
    WARNING = True
    LAPTOP = True


def log(msg: str, category: str):
    match category:
        case 'debug':
            if Settings.DEBUG:
                print(f'->>>>>> [DEBUG]: {msg}\n{"-"*30}\n')
        case 'system':
            if Settings.SYSTEM:
                print(f'-> [SYSTEM]: {msg}')
        case 'warning':
            print(f"\n\t\tX[WARNING]X\n{25*'-'}\n: {msg}\n")
        case other:
            raise ValueError('Insert either system/debug')


class local:
    '''
    Include all local enviroment related valriables
    '''
    if Settings.LAPTOP:
        XLSX_PATH = 'C:/Users/Ofek Shmuel/OneDrive/Temporary/BankProject/Inputs'
        Personal_PATH = 'C:/Users/Ofek Shmuel/OneDrive/Temporary/BankProject/personal information/personal_config.json'
    else:
        XLSX_PATH = 'C:/Users/ofeks/OneDrive/Temporary/BankProject/Inputs'
        Personal_PATH = 'C:/Users/ofeks/OneDrive/Temporary/BankProject/personal information/personal_config.json'
    EXTENSION = '.xls'
