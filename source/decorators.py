from enum import Enum


def error_handler(default_return=None):
    """
    A Python decorator that improves the reliability of functions by handling errors gracefully.
    It provides a controlled way to manage exceptions during execution,
    preventing abrupt program termination and promoting more predictable behavior.
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                print(f"An error occurred: {e}")
                return default_return

        return wrapper
    return decorator

def try_catch(function):
    '''
    This decorator add a try-except wrapper to the appointed function.
    If the function returns a None, True is returned instead. Upon returning None None
    value, the function will returned it.
    upon catching an error, The function will return False.
    '''
    def wrapper(*args):
        try:
            ans = function(*args)
            if ans is None:
                return True
            return ans
        except Exception as e:
            print(f'Function {function} Failed with error message:\
            \n{50*"-"}\n{e}\n{50*"-"}\n')
            return False

    return wrapper


class Status(Enum):
    exists = 1
    new = 2
    update = 3


class File(Enum):
    credit = 1
    montly = 2
    visa = 3
    INVALID = 4
    unknown = 5
