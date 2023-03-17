from Constants import log


class Stack:

    def __init__(self):
        self.lst = []

    def is_empty(self) -> bool:
        return len(self.lst) == 0

    def pop(self):
        if not self.is_empty():
            ele = self.lst[0]
            self.lst = self.lst[1:]
            return ele
        else:
            log("In Class Stack, function pop -> No element to pop.", category='error')

    def peek(self):
        if not self.is_empty():
            return self.lst[0]
        else:
            log("In Class Stack, function peek -> No element to peek on.", category='error')

    def push(self, new_element):
        if self.is_empty():
            self.lst.append(new_element)
        else:
            self.lst = [new_element] + self.lst

    def get_size(self):
        return len(self.lst)
