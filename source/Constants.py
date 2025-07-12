########################################################################
#                             CONFIG FILE
#
#  Mind that on WINDOWS OS, all slashes are as follows: /
#
########################################################################

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
    
    PERSONAL_CONFIG =   'Personal Information/personal_config.json'     # Personal configuration file
    CATEGORY_JSON =     'Personal Information/categories.json'          # Categories JSON file (holds all different categories)
    AUTO_TAGGER_JSON =  'personal information/auto_tagger.json'         # Holds setting fro auto tagging different transactions

    #EXTENSION_1 = '.xls'    # Excel file extension                      # Extension type 1 for parsing
    #EXTENSION_2 = '.csv'    # CSV file extension                        # Extension type 2 for parsing      
    #EXTENSION_3 = ''                                                    # Add another extension option here if needed or leave as an empty string.

    #GENERAL_INFO_GRAPH =                "C:/Users/ofeks/Desktop/BankProject/Outputs/General_info.png"
    #GENERAL_INFO_USER_DEFINED_GRAPH =   "C:/Users/ofeks/Desktop/BankProject/Outputs/General_info_user_defined.png"
    CARD_DIST_PIE_GRAPH =               "C:/Users/ofeks/OneDrive/BankProject/Outputs/Card_Distribution.png"



class Local:

    # Validation
    CHARGE_DAY = 2

    Colors = [
        "#E6CCFF",  # Soft Lavender (darker and more saturated than original Lavender)
        "#D0FFD0",  # Pale Mint (a bit more green and slightly darker than Honeydew)
        "#FFD7BA",  # Light Apricot (warmer and more distinct than Linen)
        "#FFEDCC",  # Pale Peach (warmer than SeaShell)
        "#C8F7FF",  # Pale Sky Blue (darker and slightly more saturated than Light Cyan)
        "#FFD0D0",  # Light Coral (slightly darker than Misty Rose)
        "#F0E68C",  # Khaki (keeping the original Khaki for contrast)
        "#F5DCB7",  # Light Khaki (more yellowish than Beige)
        "#DAD0FF",  # Light Lavender (more distinct from the first lavender variant)
        "#FFDAB3"   # Soft Peach (more distinct and warmer than Moccasin)
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

    
    USER_PLOT = True
    USER_DEFINED_CATEGORIES = ["משכורת",
                               "רכב",
                               "מצרכים",
                               "אוכל בחוץ",
                               "שכירות",
                               "תחבורה ציבורית",
                               "הלוואה",
                               "בילויים",
                               "בריאות וכושר",
                               "חשבונות",
                               "חתונות",
                               "מתנות",
                               "מצרכים",
                               "השכלה ולימודים"]



class Personal:
    '''
    All constants in this class are taken from the personal_config.json
    which is only avaliable in the local repository.
    '''
    # BANK_ACC = json.load(open(Paths.PERSONAL_CONFIG, encoding='utf-8'))['bank_account']
    # BANK_ACC_VisaFile = json.load(open(Paths.PERSONAL_CONFIG, encoding='utf-8'))['bank_account_visa_file']


class GENERAL_PLOT:
    
    SHOW_CURRENT_MONTH = True
    