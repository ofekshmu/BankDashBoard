
class utils:

    @staticmethod
    def undo_last_change():
        pass

    @staticmethod
    def warning_halt():

        def is_valid(x: str) -> bool:
            if not x.isnumeric():
                return False
            x = int(x)
            if not isinstance(x, int):
                return False
            if x not in [1, 2]:
                return False
            return True

        print("------ [HALT] ------")
        st = "There might be a problem, what do yo u want to do?\n1 -> Continue\n2 -> Stop and debug"
        print(st)
        while True:
            x = input()
            if not is_valid(x):
                print("Bad input, Try again...")
                continue
            match x:
                case 1:
                    break  # Continue
                case 2:
                    input()
                    utils.undo_last_change()
                case _:
                    print("This should not happen"); input("stopped.")
