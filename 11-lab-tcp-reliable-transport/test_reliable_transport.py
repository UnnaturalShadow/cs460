"""Deterministic packet-level checks runnable without CougarNet or root."""
import heapq
import itertools
from pathlib import Path
import random
import socket
import sys
import types
import unittest
from unittest.mock import patch

# Only CougarNet's address conversion helpers are needed by the wire headers.
try:
    import cougarnet.util
except ModuleNotFoundError:
    util = types.ModuleType('cougarnet.util')
    util.ip_str_to_binary = socket.inet_aton
    util.ip_binary_to_str = socket.inet_ntoa
    package = types.ModuleType('cougarnet')
    package.util = util
    sys.modules['cougarnet'] = package
    sys.modules['cougarnet.util'] = util

from buffer import TCPReceiveBuffer, TCPSendBuffer
from headers import IPv4Header, TCPHeader, IP_HEADER_LEN, TCPIP_HEADER_LEN
from mysocket import TCPSocket, TCP_STATE_ESTABLISHED, TCP_FLAGS_ACK


class Event:
    def __init__(self, callback):
        self.callback = callback
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


class Network:
    def __init__(self, loss=0):
        self.now = 0
        self.events = []
        self.order = itertools.count()
        self.random = random.Random(460)
        self.loss = loss
        self.sent = []
        self.peers = {}

    def call_later(self, delay, callback):
        event = Event(callback)
        heapq.heappush(self.events, (self.now + delay, next(self.order), event))
        return event

    def send(self, packet):
        header = IPv4Header.from_bytes(packet[:IP_HEADER_LEN])
        self.sent.append(packet)
        if self.random.random() >= self.loss:
            # Variable latency also exercises reordering and duplicate ACKs.
            self.call_later(self.random.uniform(.001, .02),
                    lambda: self.peers[header.dst].handle_packet(packet))

    def run(self):
        count = 0
        while self.events:
            self.now, _, event = heapq.heappop(self.events)
            if not event.cancelled:
                event.callback()
                count += 1
                if count > 200000 or self.now > 1000:
                    raise AssertionError('Transfer failed to finish')


def pair(network, **options):
    a = TCPSocket('10.0.0.1', 1234, '10.0.0.2', 4321,
            TCP_STATE_ESTABLISHED, network.send, lambda: None, **options)
    b = TCPSocket('10.0.0.2', 4321, '10.0.0.1', 1234,
            TCP_STATE_ESTABLISHED, network.send, lambda: None, **options)
    a.bypass_handshake(100, 500)
    b.bypass_handshake(500, 100)
    network.peers = {'10.0.0.1': a, '10.0.0.2': b}
    return a, b


class ReliableTransportTests(unittest.TestCase):
    def test_file_transfers(self):
        cases = [('hello.txt', 0, 10000, False, 'none'),
                 ('test.txt', 0, 10000, False, 'none'),
                 ('byu-y-mtn.jpg', 0, 10000, False, 'none'),
                 ('byu-y-mtn.jpg', 0, 50000, False, 'none'),
                 ('test.txt', .05, 10000, False, 'none'),
                 ('byu-y-mtn.jpg', .01, 50000, False, 'none'),
                 ('test.txt', .05, 10000, True, 'none'),
                 ('byu-y-mtn.jpg', .01, 50000, True, 'none'),
                 ('byu-y-mtn.jpg', 0, 1000, True, 'tahoe'),
                 ('byu-y-mtn.jpg', .001, 1000, True, 'tahoe')]
        for filename, loss, window, fast, algorithm in cases:
            with self.subTest(file=filename, loss=loss, fast=fast, algorithm=algorithm):
                network = Network(loss)
                a, b = pair(network, initial_cwnd=window,
                        fast_retransmit=fast, congestion_control=algorithm)
                original = Path(__file__).with_name(filename).read_bytes()
                with patch('mysocket.asyncio.get_event_loop', return_value=network):
                    a.send(original)
                    network.run()
                self.assertEqual(b.recv(len(original) + 1), original)
                self.assertEqual(a.send_buffer.bytes_outstanding(), 0)
                self.assertEqual(a.send_buffer.bytes_not_yet_sent(), 0)
                self.assertIsNone(a.timer)

    def test_fast_retransmit_only_on_third_duplicate(self):
        network = Network()
        a, b = pair(network, initial_cwnd=4000, fast_retransmit=True)
        with patch('mysocket.asyncio.get_event_loop', return_value=network):
            a.send(b'x' * 4000)
            ack = b.create_packet(b._local_addr, 4321, a._local_addr, 1234,
                    b.seq, a.seq, TCP_FLAGS_ACK)
            for _ in range(3):
                a.handle_ack(ack)
            self.assertEqual(len(network.sent), 4)
            a.handle_ack(ack)
            self.assertEqual(len(network.sent), 5)
            for _ in range(5):
                a.handle_ack(ack)
            self.assertEqual(len(network.sent), 5)
            a.cancel_timer()

    def test_tahoe_growth_and_loss(self):
        network = Network()
        a, b = pair(network, congestion_control='tahoe')
        with patch('mysocket.asyncio.get_event_loop', return_value=network):
            a.send(b'x' * 10000)
            ack = b.create_packet(b._local_addr, 4321, a._local_addr, 1234,
                    b.seq, a.seq + 1000, TCP_FLAGS_ACK)
            a.handle_ack(ack)
            self.assertEqual(a.cwnd, 2000)
            a.retransmit()
            self.assertEqual(a.cwnd, 1000)
            self.assertEqual(a.ssthresh, 1000)
            self.assertEqual(a.cwnd_inc, 0)
            a.cancel_timer()

    def test_partial_window_and_invalid_acks(self):
        network = Network()
        a, b = pair(network, initial_cwnd=1500)
        with patch('mysocket.asyncio.get_event_loop', return_value=network):
            a.send(b'x' * 4000)
            self.assertEqual(a.send_buffer.bytes_outstanding(), 1500)
            self.assertEqual([len(p) - TCPIP_HEADER_LEN for p in network.sent],
                    [1000, 500])
            for number in [a.seq - 1, a.send_buffer.next_seq + 1]:
                packet = b.create_packet(b._local_addr, 4321, a._local_addr,
                        1234, b.seq, number, TCP_FLAGS_ACK)
                a.handle_ack(packet)
            self.assertEqual(a.seq, 101)
            network.run()
            self.assertEqual(b.recv(5000), b'x' * 4000)

    def test_buffer_edge_cases(self):
        send = TCPSendBuffer(100)
        send.put(b'abcdef')
        send.get(2)
        self.assertEqual(send.get_for_resend(100), (b'ab', 100))
        send.slide(99)
        send.slide(103)
        self.assertEqual(send.base_seq, 100)
        receive = TCPReceiveBuffer(100)
        receive.put(b'xxabc', 98)
        receive.put(b'cdefgh', 102)
        receive.put(b'bc', 101)
        receive.put(b'', 100)
        self.assertEqual(receive.get(), (b'abcdefgh', 100))
        self.assertEqual(receive.buffer, {})


if __name__ == '__main__':
    unittest.main()
