#!./bin/python

import sys
import json
import time
import os
import stat

import signal
import socket
import serial
import io

from collections import Counter, defaultdict
from itertools import chain
from tabulate import tabulate

import urwid

from decoders import *

import locale
locale.setlocale(locale.LC_ALL, '')
code = locale.getpreferredencoding()

TOP = 20

KNOWN = ('201', '433', '4B0', '4F2', '4DA')


def memoize(f):
    memo = {}

    def helper(self, x):
        if x not in memo:
            memo[x] = f(self, x)
        return memo[x]
    helper.__name__ = f.__name__
    return helper


class dictlist(defaultdict):
    def __init__(self):
        super(dictlist, self).__init__(list)
        self.__all_same_cache = {}

    def all_same(self, key):
        if key in self.__all_same_cache:
            return self.__all_same_cache[key]
        ls = self[key]
        result = all(ls[i] == ls[i + 1] for i in range(len(ls) - 1))
        self.__all_same_cache[key] = result
        return result

    def unk_ranges(self, key):
        ls = self[key]
        ranges = [(255, 0) for a in ls[0].unknown]
        for o in ls:
            for i, d in enumerate(o.unknown):
                mn, mx = ranges[i]
                mn = min(mn, d)
                mx = max(mx, d)
                ranges[i] = (mn, mx)
        return tuple(ranges)

    def unk_deltas(self, key):
        r = self.unk_ranges(key)
        return tuple(b - a for (a, b) in r)

    def append(self, key, value):
        if key in self.__all_same_cache:
            del self.__all_same_cache[key]
        self[key].append(value)

class App(object):
    def __init__(self, argv):
        signal.signal(signal.SIGINT, self.sigint)
        self.file = argv[1]
        self.readonly = False
        if self.file.startswith('ip:'):
            ip = tuple(self.file.split(':')[1:])
            print (ip)
            self.fd = socket.create_connection(self.file.split(':')[1:])
            self.io = self.fd.makefile('rw')
        else:
            if stat.S_ISCHR(os.stat(self.file).st_mode):
                self.fd = serial.Serial(self.file, 115200, timeout=1)
                self.io = io.TextIOWrapper(io.BufferedRandom(self.fd))
            else:
                self.fd = io.FileIO(self.file, 'r')
                self.io = io.TextIOWrapper(io.BufferedReader(self.fd))
                self.readonly = True

        self.leftbox = urwid.ListBox(urwid.SimpleFocusListWalker([urwid.Text('')]))
        self.rightbox = urwid.ListBox(urwid.SimpleFocusListWalker([urwid.Text(''), urwid.Text('')]))
        self.column = urwid.Columns([self.leftbox, self.rightbox])
        self.header = urwid.AttrMap(urwid.Text('CAN Bus data stats'), 'header')

        self.status_icons = urwid.WidgetPlaceholder(urwid.Text(''))
        self.status_packets = urwid.WidgetPlaceholder(urwid.Text(''))

        self.footer = urwid.AttrMap(urwid.Columns([self.status_icons, self.status_packets]), 'footer')
        self.frame = urwid.PopUpTarget(urwid.Frame(self.column, header=self.header, footer=self.footer))

        self.statline = []
        self.c_packets = 0
        self.errors = 0
        self.packets = []
        self.packets_by_id = dictlist()
        self.packet_last_time = {}
        self.packet_avg_times = {}
        self.ids = Counter()
        self.classes = Counter()
        self.event_loop = urwid.AsyncioEventLoop()
        self.main_loop = urwid.MainLoop(
            self.frame,
            event_loop=self.event_loop,
            unhandled_input=self.handle_key)
        self.watch_file_handle = None
        self.toggle_watch()
        self.event_loop.alarm(0.25, self.update_display)

        if self.readonly:
            self.update_statline('RO')

    def run(self):
        self.main_loop.run()

    def sigint(self, signal, frame):
        raise urwid.ExitMainLoop()

    def toggle_watch(self):
        if self.watch_file_handle is None:
            self.watch_file_handle = self.event_loop.watch_file(self.fd, self.file_ready)
        else:
            self.event_loop.remove_watch_file(self.watch_file_handle)
            self.watch_file_handle = None

    def handle_key(self, key):
        if key in ('q', 'Q'):
            raise urwid.ExitMainLoop()
        if key in ('1', '2', '3') and not self.readonly:
            self.io.write('\x03\x01' + chr(int(key)) + '\x00\x00\x00\x00')
            self.update_statline(key)
        if key in ('c', 'C'):
            pass
        if key in ('p', 'P'):
            self.toggle_watch()

    def update_statline(self, stat):
        if stat in self.statline:
            self.statline.remove(stat)
        else:
            self.statline.append(stat)
        self.status_icons.original_widget = urwid.Text(self.statline)

    def set_status(self, index, text):
        self.footer.original_widget.contents[index] = (
            urwid.Text(text), ('weight', index + 1, False))

    def file_ready(self):
        o = None
        line = None
        try:
            line = self.io.readline()
            o = json.loads(line)

        except:
            self.errors += 1
        if o is not None and 'packet' in o:
            packet = Decoder.factory(**o['packet'])
            self.c_packets += 1
            self.packets.append(packet)
            self.packets_by_id.append(packet.id, packet)
            self.ids[packet.id] += 1
            self.classes[packet.__class__] += 1
            t = int(packet.timestamp or '0')
            if packet.id in self.packet_last_time:
                count = self.ids[packet.id]
                duration = t - self.packet_last_time[packet.id]
                self.packet_avg_times[packet.id] = ((self.packet_avg_times[packet.id] * (count - 1)) + duration) / count
                self.packet_last_time[packet.id] = t
            else:
                self.packet_avg_times[packet.id] = 0
                self.packet_last_time[packet.id] = t


        self.set_status(
            1,
            '{} errors in {} packets with {} ids'.format(self.errors, self.c_packets, len(self.packets_by_id)))

    def update_display(self):
        r_table = tabulate(
            ((
                self.packet_avg_times[id],
                count,
                self.packets_by_id[id][-1:][0]
            )
            for (id, count)
            in self.ids.most_common()),
            headers=['avg duration', 'count', 'last packet'],
            tablefmt="plain"
        )
        self.rightbox.body[0] = urwid.Text(r_table)
        l_table = tabulate(
            ((
                Decoder.lookup_class(id).__name__,
                id,
                count,
                self.packets_by_id.all_same(id),
                # '.' + (' '.join('{:3},{:3}'.format(a[0], a[1]) for a in self.packets_by_id.unk_ranges(id))),
                '\u00B7' + (' '.join('{:3}'.format(a) for a in Decoder.lookup_class(id).STATS.get_maxs()))
            )
            for (id, count)
            in self.ids.most_common()),
            headers=['repr', 'id', 'count', 'same', 'ranges'],
            tablefmt="plain"
        )
        self.leftbox.body[0] = urwid.Text(l_table)
        self.event_loop.alarm(0.1, self.update_display)


def main(argv):
    App(argv).run()

if __name__ == '__main__':
    main(sys.argv)
