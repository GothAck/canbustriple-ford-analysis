from collections import deque
from scipy.stats import mode


def add_plural_method(cls, name, method):
    new_name = name[:-2] + 's'

    def new_method(self):
        return (method(self, n) for n in range(self.count))
    new_method.__name__ = new_name
    setattr(cls, new_name, new_method)


def add_plural_methods(cls):
    for name in dir(cls):
        method = getattr(cls, name)
        if callable(method) and name.endswith('_n'):
            add_plural_method(cls, name, method)
    return cls


@add_plural_methods
class Stats(object):
    def __init__(self, count=8, runtime=50):
        self.count = count
        self.runtime = runtime
        self.deques = tuple(
            deque([], maxlen=runtime)
            for _ in range(count))

    def add_sample(self, ts, *samples):
        if len(samples) == self.count:
            for i, sample in enumerate(samples):
                self.deques[i].append(sample)

    def get_sum_n(self, n):
        return sum(self.deques[n])

    def get_avg_n(self, n):
        return self.get_sum_n(n) / len(self.deques[n])

    def get_max_n(self, n):
        return max(self.deques[n])

    def get_min_n(self, n):
        return min(self.deques[n])

    def get_mode_n(self, n):
        return mode(self.deques[n])
