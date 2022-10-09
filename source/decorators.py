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
