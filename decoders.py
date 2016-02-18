from itertools import chain
from stats import Stats


class Decoder(object):
    ID = None
    PRINT = False
    STATS = None
    COUNTER = None

    @classmethod
    def init_class(cls):
        if cls.STATS is None:
            cls.STATS = Stats()
            cls.COUNTER = 0
        return cls

    @classmethod
    def init_subclasses(cls):
        assert cls is Decoder, 'Can only be called on parent class'
        cls.__name__ = ''
        cls.CLSMAP = {c.ID: c.init_class() for c in cls.__subclasses__()}

    @classmethod
    def lookup_class(cls, id):
        Cls = cls.CLSMAP.get(id, False)
        if Cls is False:
            Cls = type('Generic', (Decoder, ), {})
            Cls.ID = id
            cls.CLSMAP[id] = Cls.init_class()
        return Cls

    @classmethod
    def factory(cls, id, **kwargs):
        Cls = cls.lookup_class(id)
        return Cls(id=id, **kwargs)

    def __init__(self, status, timestamp, payload, length, id, channel):
        self.status = status
        self.timestamp = timestamp
        self.payload = tuple(int(v or '0', 16) for v in payload)
        self.STATS.add_sample(self.timestamp, *self.payload)
        self.COUNTER += 1
        self.length = length
        self.id = id
        self.channel = channel
        self.unknown = tuple()
        self.__knownkeys = list(self.__dict__.keys()) + ['_Decoder__knownkeys']
        self.process()

    def __eq__(self, other):
        if self.id != other.id:
            return False
        if self.unknown and other.unknown:
            return self.unknown == other.unknown

    def __subrepr__(self):
        new_keys = set(self.__dict__.keys())
        return (
            '{}={}'.format(key, self.__dict__[key])
            for key in new_keys.difference(self.__knownkeys))

    def __repr__(self):
        sub = self.__subrepr__()
        if self.unknown:
            sub = chain(sub, ('unknown={}'.format(self.unknown), ))

        return '<{}-{} {}>'.format(
            self.__class__.__name__, self.__class__.ID, ' '.join(sub))

    def process(self):
        self.unknown = self.payload


class ABSWheels(Decoder):
    ID = '4B0'
    WHEELS = ('f_l', 'f_r', 'r_l', 'r_r')

    def __subrepr__(self):
        return ('{}={}'.format(w, self.__dict__[w]) for w in self.WHEELS)

    def process(self):
        for i, wheel in enumerate(self.WHEELS):
            i = i * 2
            v = (((self.payload[i] << 8) + self.payload[i+1]) - 10000) / 100.0
            self.__dict__[wheel] = v


class Doors(Decoder):
    ID = '433'
    DOORS = ('T', 'RR', 'RL', 'FR', 'FL')

    def __subrepr__(self):
        return ('doors={} {}'.format(self.doors, self.value),)

    def process(self):
        self.value = self.payload[0]
        self.doors = []
        for i, door in enumerate(self.DOORS):
            if self.value & (1 << (i + 3)):
                self.doors.append(door)
        self.unknown = self.payload[1:]


class Odometer(Decoder):
    ID = '4F2'

    def process(self):
        self.range = self.payload[0]
        self.km = (self.payload[1] << 8) + self.payload[2]
        self.unknown = self.payload


class EngineGas(Decoder):
    ID = '201'

    def process(self):
        self.rpm = (self.payload[0] << 8) + self.payload[1]
        self.speed = ((self.payload[4] << 8) + self.payload[5]) / 100
        self.accelerator = self.payload[6]
        UNK = (2, 3, 7)
        self.unknown = tuple(self.payload[i] for i in UNK)


class Compass(Decoder):
    ID = '2BA'
    # PRINT = True

    def process(self):
        self.heading = self.payload[4]
        self.unknown = self.payload


class Print(Decoder):
    ID = ''
    PRINT = True

    def __subrepr__(self):
        return ('id={}'.format(self.ID),)

Decoder.init_subclasses()
