#!/usr/bin/env python3

import asyncio
import json
import socket

NEIGHBOR_CHECK_INTERVAL = 3
DV_TABLE_SEND_INTERVAL = 1
DV_PORT = 5016

from cougarnet.sim.host import BaseHost

from prefix import *
from forwarding_table_native import ForwardingTableNative as ForwardingTable

class DVRouter(BaseHost):
    def __init__(self):
        super().__init__()

        self.my_dv = {}
        self.neighbor_dvs = {}

        self.forwarding_table = ForwardingTable()

        self._initialize_dv_sock()

        self.neighbor_ips = {}
        self.neighbor_timeouts = {}
        self.next_hops = {}

    def _initialize_dv_sock(self) -> None:
        '''Initialize the socket that will be used for sending and receiving DV
        communications to and from neighbors.
        '''

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock.bind(('0.0.0.0', DV_PORT))

    def init_dv(self):
        '''Set up our instance to work with the event loop, initialize our DV,
        and schedule our regular updates to be sent to neighbors.
        '''

        loop = asyncio.get_event_loop()

        # register our socket with the event loop, so we can handle datagrams
        # as they come in
        loop.add_reader(self.sock, self._handle_msg, self.sock)

        # Initialize our DV -- and optionally send our DV to our neighbors
        self.update_dv()

        # Schedule self.send_dv_next() to be called in 1 second and
        # self.update_dv_next() to be called in 0.5 seconds.
        loop.call_later(DV_TABLE_SEND_INTERVAL, self.send_dv_next)
        loop.call_later(DV_TABLE_SEND_INTERVAL - DV_TABLE_SEND_INTERVAL / 2,
                self.update_dv_next)

    def _handle_msg(self, sock: socket.socket) -> None:
        ''' Receive and handle a message received on the UDP socket that is
        being used for DV messages.
        '''

        data, addrinfo = sock.recvfrom(65536)
        self.handle_dv_message(data)

    def _send_msg(self, msg: bytes, dst: str) -> None:
        '''Send a DV message, msg, on our UDP socket to dst.'''

        self.sock.sendto(msg, (dst, DV_PORT))

    def handle_dv_message(self, msg: bytes) -> None:
        '''Remember the latest vector and restart the neighbor's keep-alive timer.'''
        obj = json.loads(msg.decode('utf-8'))
        neighbor = obj['name']
        if neighbor == self.hostname:
            return

        self.neighbor_ips[neighbor] = obj['ip']
        self.neighbor_dvs[neighbor] = obj['dv']
        previous_timeout = self.neighbor_timeouts.get(neighbor)
        if previous_timeout is not None:
            previous_timeout.cancel()
        loop = asyncio.get_event_loop()
        self.neighbor_timeouts[neighbor] = loop.call_later(
                NEIGHBOR_CHECK_INTERVAL, self.handle_down_link, neighbor)

    def send_dv_next(self):
        '''Send DV to neighbors, and schedule this method to be called again in
        1 second (DV_TABLE_SEND_INTERVAL).
        '''

        self.send_dv()
        loop = asyncio.get_event_loop()
        loop.call_later(DV_TABLE_SEND_INTERVAL, self.send_dv_next)

    def update_dv_next(self):
        '''Update DV using neighbors' DVs.  Then schedule this method to be
        called again in 1 second (DV_TABLE_SEND_INTERVAL).
        '''

        self.update_dv()
        loop = asyncio.get_event_loop()
        loop.call_later(DV_TABLE_SEND_INTERVAL, self.update_dv_next)

    def handle_down_link(self, neighbor: str):
        self.log(f'Link down: {neighbor}')
        self.neighbor_dvs.pop(neighbor, None)
        self.neighbor_ips.pop(neighbor, None)
        timeout = self.neighbor_timeouts.pop(neighbor, None)
        if timeout is not None:
            timeout.cancel()

    def resolve_neighbor_dvs(self):
        '''Return a copy of the mapping of neighbors to distance vectors, with
        IP addresses replaced by names in every neighbor DV.
        '''

        neighbor_dvs = {}
        for neighbor in self.neighbor_dvs:
            neighbor_dvs[neighbor] = self.resolve_dv(self.neighbor_dvs[neighbor])
        return neighbor_dvs

    def resolve_dv(self, dv: dict) -> dict:
        '''Return a copy of distance vector dv with IP addresses replaced by
        names.
        '''

        resolved_dv = {}
        for dst, distance in dv.items():
            if '/' not in dst:
                try:
                    dst = socket.getnameinfo((dst, 0), 0)[0]
                except:
                    pass
            resolved_dv[dst] = distance
        return resolved_dv

    def update_dv(self) -> None:
        '''Rebuild shortest distances from local prefixes and neighbors' vectors.'''
        new_dv = {self.prefix_for_int(intf): 0
                for intf in self.physical_interfaces()}
        next_hops = {}
        # Stable ordering keeps equal-cost routes from changing every update.
        for neighbor in sorted(self.neighbor_dvs):
            for prefix, distance in self.neighbor_dvs[neighbor].items():
                cost = distance + 1
                if prefix not in new_dv or cost < new_dv[prefix]:
                    new_dv[prefix] = cost
                    next_hops[prefix] = self.neighbor_ips[neighbor]

        # A changed next hop also needs installing when the distance is unchanged.
        if new_dv != self.my_dv or next_hops != self.next_hops:
            for prefix, next_hop in self.next_hops.items():
                if next_hops.get(prefix) != next_hop:
                    self.forwarding_table.remove_entry(prefix)
            for prefix, next_hop in next_hops.items():
                if self.next_hops.get(prefix) != next_hop:
                    self.forwarding_table.add_entry(prefix, None, next_hop)
            self.my_dv = new_dv
            self.next_hops = next_hops

    def prefix_for_int(self, intf: str) -> str:
        obj = self.ipv4_address_info_single(intf)
        ip_int = ip_str_to_int(obj['address'])
        ip_prefix_int = ip_prefix(ip_int, socket.AF_INET, obj['prefixlen'])
        first_addr = ip_int_to_str(ip_prefix_int, socket.AF_INET)
        return '%s/%d' % (first_addr, obj['prefixlen'])

    def bcast_for_int(self, intf: str) -> str:
        obj = self.ipv4_address_info_single(intf)
        ip_int = ip_str_to_int(obj['address'])
        ip_prefix_int = ip_prefix(ip_int, socket.AF_INET, obj['prefixlen'])
        ip_bcast_int = ip_prefix_last_address(ip_prefix_int, socket.AF_INET, obj['prefixlen'])
        bcast = ip_int_to_str(ip_bcast_int, socket.AF_INET)
        return bcast

    def send_dv(self) -> None:
        '''Broadcast our vector with the source address of each interface.'''
        for intf in self.physical_interfaces():
            obj = {'ip': self.ipv4_address_info_single(intf)['address'],
                    'name': self.hostname, 'dv': self.my_dv}
            self._send_msg(json.dumps(obj).encode('utf-8'),
                    self.bcast_for_int(intf))

def main():
    router = DVRouter()
    router.init_dv()
    router.run()

if __name__ == '__main__':
    main()
