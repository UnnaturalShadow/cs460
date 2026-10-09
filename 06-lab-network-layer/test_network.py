"""Portable packet tests; no Cougarnet installation or raw sockets needed.

Run with: python3 -m unittest -v test_network.py
The actual Cougarnet scenarios must still be run on the lab VM.
"""
import importlib
import json
import os
from pathlib import Path
import socket
import struct
import sys
import types
import unittest
from unittest.mock import patch


def mac_bytes(address):
    return bytes.fromhex(address.replace(':', ''))


class FakeBaseHost:
    def __init__(self):
        pass

    def physical_interfaces(self):
        return list(self.interfaces)

    def interface_info_single(self, intf):
        return {'address': self.interfaces[intf]['mac']}

    def ipv4_address_info_single(self, intf):
        return self.interfaces[intf]

    def ipv4_addresses(self, intf=None):
        names = [intf] if intf else self.interfaces
        return [self.interfaces[name]['address'] for name in names]

    def send_frame(self, frame, intf):
        self.network.queue.append((self, intf, frame))


def packet(dst, ttl=64, protocol=1):
    return struct.pack('!BBHHHBBH4s4s', 0x45, 0, 24, 0, 0,
                       ttl, protocol, 0, socket.inet_aton('10.0.0.2'),
                       socket.inet_aton(dst)) + b'test'


class Network:
    def __init__(self, filename, host_class):
        self.queue = []
        self.observations = []
        self.nodes = {}
        self.links = {}
        lines = Path(filename).read_text().splitlines()
        section = None
        configs = {}
        switches = set()
        interfaces = {}
        for line in lines:
            if not line or line.startswith('#'):
                continue
            if line in ('NODES', 'LINKS'):
                section = line
                continue
            if section == 'NODES':
                name, _, config = line.partition(' ')
                configs[name] = config
                interfaces[name] = {}
                if 'type=switch' in config:
                    switches.add(name)
            elif section == 'LINKS':
                ends = [end.split(',') for end in line.split()]
                a, b = ends[0][0], ends[1][0]
                for end, peer in zip(ends, (b, a)):
                    name = end[0]
                    if name in switches:
                        continue
                    address, length = end[1].split('/')
                    intf = f'{name}-{peer}'
                    interfaces[name][intf] = {
                        'address': address, 'prefixlen': int(length),
                        'mac': f'02:00:00:00:00:{sum(map(len, interfaces.values())) + 1:02x}'}
                    segment = peer if peer in switches else tuple(sorted((name, peer)))
                    self.links.setdefault(segment, []).append((name, intf))
        for name, config in configs.items():
            if name in switches:
                continue
            routes = []
            for field in config.split(','):
                if field.startswith('routes='):
                    for route in field[7:].split(';'):
                        prefix, peer, hop = route.split('|')
                        routes.append((prefix, f'{name}-{peer}', hop or None))
            cls = type('Node', (host_class,), {'interfaces': interfaces[name]})
            with patch.dict(os.environ, {'COUGARNET_ROUTES': json.dumps(routes)}):
                node = cls('type=router' in config)
            node.name, node.network = name, self
            node.received = []
            node.handle_tcp = lambda pkt, n=node: n.received.append(('tcp', pkt))
            node.handle_udp = lambda pkt, n=node: n.received.append(('udp', pkt))
            self.nodes[name] = node

    def drain(self):
        while self.queue:
            sender, intf, frame = self.queue.pop(0)
            segment = next(v for v in self.links.values() if (sender.name, intf) in v)
            for name, incoming in segment:
                if name == sender.name:
                    continue
                node = self.nodes[name]
                if frame[:6] not in (b'\xff' * 6, mac_bytes(node.interfaces[incoming]['mac'])):
                    continue
                if frame[12:14] == b'\x08\x00':
                    self.observations.append((name, frame[14:]))
                node._handle_frame(frame, incoming)


class NetworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base = types.ModuleType('cougarnet.sim.host')
        base.BaseHost = FakeBaseHost
        util = types.ModuleType('cougarnet.util')
        util.mac_str_to_binary = mac_bytes
        util.mac_binary_to_str = lambda data: ':'.join(f'{b:02x}' for b in data)
        util.ip_str_to_binary = socket.inet_aton
        util.ip_binary_to_str = socket.inet_ntoa
        cls.modules = patch.dict(sys.modules, {'cougarnet.sim.host': base, 'cougarnet.util': util})
        cls.modules.start()
        cls.Host = importlib.import_module('host').Host

    @classmethod
    def tearDownClass(cls):
        cls.modules.stop()

    def test_scenario1_arp_and_forwarding(self):
        net = Network('scenario1.cfg', self.Host)
        for source, dst, hop, expected in [
            ('a', '10.0.0.3', '10.0.0.3', ['b']),
            ('a', '10.0.0.3', '10.0.0.3', ['b']),
            ('b', '10.0.0.2', '10.0.0.2', ['a']),
            ('a', '10.0.1.2', '10.0.0.1', ['r1', 'c'])]:
            node = net.nodes[source]
            net.observations.clear()
            node.send_packet_on_int(packet(dst), next(iter(node.interfaces)), hop)
            net.drain()
            self.assertEqual([name for name, _ in net.observations], expected)
            self.assertEqual(node._pending_packets, [])
        self.assertIn('10.0.0.2', net.nodes['b']._arp_table)

    def test_scenario2_longest_prefix_and_ttl(self):
        net = Network('scenario2.cfg', self.Host)
        destinations = ['10.0.0.3', '10.20.0.25', '10.20.0.34', '10.20.1.20',
                        '10.20.3.1', '10.20.0.2', '10.20.0.11', '10.20.0.150',
                        '10.20.0.7', '10.20.0.75', '10.40.0.2', '10.40.0.2']
        expected = [['b']] + [['r1', n] for n in 'gfckjhdie'] + [['r1', 'r2', 'l'], ['r1']]
        for index, (dst, seen) in enumerate(zip(destinations, expected)):
            with self.subTest(destination=dst, index=index):
                net.observations.clear()
                net.nodes['a'].send_packet(packet(dst, 1 if index == 11 else 64))
                net.drain()
                self.assertEqual([name for name, _ in net.observations], seen)
                self.assertEqual([pkt[8] for _, pkt in net.observations],
                                 [1] if index == 11 else list(range(64, 64 - len(seen), -1)))

    def test_queue_dispatch_and_drops(self):
        net = Network('scenario1.cfg', self.Host)
        a = net.nodes['a']
        intf = next(iter(a.interfaces))
        a.send_packet_on_int(packet('10.0.0.3'), intf, '10.0.0.3')
        a.send_packet_on_int(packet('10.0.0.3', protocol=17), intf, '10.0.0.3')
        net.drain()
        self.assertEqual(len(net.observations), 2)
        self.assertEqual(net.nodes['b'].received[0][0], 'udp')
        a.handle_ip(packet('10.0.0.2', protocol=6), intf)
        self.assertEqual(a.received[0][0], 'tcp')
        a.send_packet(packet('192.0.2.1'))
        a.forward_packet(packet('10.0.0.3', ttl=0))
        a.not_my_packet(packet('10.0.0.3'), intf)
        a._handle_frame(b'\x00' * 14, intf)
        self.assertEqual(net.queue, [])


if __name__ == '__main__':
    unittest.main()
