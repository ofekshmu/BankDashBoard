########################################################################
#                             CONFIG FILE
#
#  Mind that on WINDOWS OS, all slashes are as follows: /
#
########################################################################

import os as _os
from enum import Enum

BANK_CARD_NUMBER = "Not_Relevant"
CC_CHARGE_CATEGORY_NAME = "אשראי"
INVESTMENT_CATEGORY = "השקעה/חיסכון"
GOLDEN_COLOR_PALLETE = ["#FFF6E1", "#FFEBBC", "#FFDD8D", "#FFCB50", "#FFC02D"]

class Settings:
    DEBUG = False
    SYSTEM = True
    WARNING = True
    LAPTOP = False


class Method(Enum):
    FILE_NAME = 1
    CELL = 2
    HEADERS = 3
    NONE = 4

class Trans_Type(Enum):
    payment = "payments"
    flowing = "flowing"
    payback = "payback"
    withdrawl = "withdrawl"
    excluded = "excluded"
    default = "default"
    bank = "bank"

class Sortion(Enum):
    BY_NAME_SERIAL = 1
    BY_NAME_DATE = 2


class Paths:
    '''
    Include all local enviroment related valriables
    '''
    DB_NAME =           "ShmuelFamiliy"                                 # Different Data base name: "Yuviz_Data"

    INPUT_FOLDER =      'ShmuelFamiliy_Inputs'                          # Used For inserting new files for parsing
    VERIFIED_FOLDER =   f"Verified_{INPUT_FOLDER}"
    UPDATE_FOLDER =     "to_update"                                     # Used for the update process
    
    # Repo root = parent of the source/ dir this file lives in. The config
    # paths below are absolute so they resolve to the same file no matter which
    # directory the process was started from. Previously they were relative and
    # resolved against os.getcwd(); the web UI and the auto-tag pass could then
    # read/write different files (e.g. server launched from source/), which made
    # saved auto-tag rules appear to vanish. On Vercel these four are still
    # re-pointed to /tmp copies in WebApp.py.
    _CONFIG_ROOT =      _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))

    PERSONAL_CONFIG =   _os.path.join(_CONFIG_ROOT, 'personal information', 'personal_config.json')  # Personal configuration file
    CATEGORY_JSON =     _os.path.join(_CONFIG_ROOT, 'personal information', 'categories.json')       # Categories JSON file (holds all different categories)
    AUTO_TAGGER_JSON =  _os.path.join(_CONFIG_ROOT, 'personal information', 'auto_tagger.json')      # Holds setting for auto tagging different transactions
    Currency_JSON =     _os.path.join(_CONFIG_ROOT, 'personal information', 'currency.json')         # Holds used currencies in the cash table

    #HTML's Names/Paths:
    ORGANIZER_TABLE_NAME = "C:\\Users\\ofeks\\OneDrive\\Ofek\\BankProject\\source\\html\\Organizer_Table.html"

class ReservedNames:
    """
    Reserved names are used to identify specific files or categories that should not be processed or are reserved for special purposes.
    """
    WITHDRAWAL = "משיכת מזומנים"
    WHITDRAWAL_CATEGORY = "withdrawal"

    EXCLUDED_CATEGORY = "Excluded"
    FILLER_CATEGORY = "Filler"
    CASH_FILLER_CATEGORY = "cash_filler"

    CC_CHARGE_CATEGORY_NAME = "אשראי"

class Local:

    # Validation
    CHARGE_DAY = 2

    Colors = [
        "#26547C",  # Steel Blue
        "#EF476F",  # Coral Red
        "#FFD166",  # Golden Yellow
        "#06D6A0",  # Mint Green
        "#FCFCFC",  # Near White
        "#118AB2",  # Sky Blue
        "#FF9F1C",  # Amber
        "#9B5DE5",  # Soft Purple
        "#F15BB5",  # Hot Pink
        "#00BBF9",  # Cyan
    ]

    gentle_blue = ['#BFD7EA',
                    '#A5C6DB',
                    '#8BB5CC',
                    '#7194BD',
                    '#577DAE',
                    '#3D5C9F',
                    '#233D90'
                    ]

    gentle_orange = ['#FFF2CC',
                    '#FFE699',
                    '#FFD966',
                    '#FFC533',
                    '#FFB200',
                    '#FFA000',
                    '#FF8F00',
                    '#FF8000',
                    '#FF6B00'
                        ]
    
    
class GeneralPlot:
    SHOW_CURRENT_MONTH = True



class Personal:
    '''
    All constants in this class are taken from the personal_config.json
    which is only avaliable in the local repository.
    '''
    # BANK_ACC = json.load(open(Paths.PERSONAL_CONFIG, encoding='utf-8'))['bank_account']
    # BANK_ACC_VisaFile = json.load(open(Paths.PERSONAL_CONFIG, encoding='utf-8'))['bank_account_visa_file']


class GENERAL_PLOT:
    
    SHOW_CURRENT_MONTH = True
    