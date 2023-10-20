from collections import deque


class SpecialQueue:
    def __init__(self, max_length):
        self.max_length = max_length
        self.queue = deque()
        self.dict = {}

    def push(self, key, value):
        if len(self.queue) >= self.max_length:
            # If the queue is full, remove the oldest element
            removed_key = self.queue.popleft()
            del self.dict[removed_key]
        self.queue.append(key)
        self.dict[key] = value

    def pop(self):
        if not self.is_empty():
            removed_key = self.queue.popleft()
            value = self.dict.pop(removed_key)
            return (removed_key, value)
        else:
            raise ValueError()

    def is_empty(self):
        return len(self.queue) == 0
    
    def is_full(self):
        return len(self.queue) == self.max_length

    def top(self):
        if not self.is_empty():
            top_key = self.queue[0]
            return (top_key, self.dict[top_key])
        else:
            return None

    def access_by_key(self, key):
        if key in self.dict:
            return self.dict[key]
        else:
            raise ValueError()

    def is_present(self, key):
        if key in self.dict:
            # Move the key to the top of the queue
            self.queue.remove(key)
            self.queue.appendleft(key)
            return True
        else:
            return False

    def __str__(self):
        return str(self.dict)

