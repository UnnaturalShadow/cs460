#!/usr/bin/python3

import argparse
import asyncio
import json
import os
import socket
import struct
import sys

from cougarnet.sim.host import BaseHost
from cougarnet.util import \
        mac_str_to_binary, mac_binary_to_str, \
        ip_str_to_binary, ip_binary_to_str

from prefix import *
from forwarding_table import ForwardingTable

# From /usr/include/linux/if_ether.h:
ETH_P_IP = 0x0800 # Internet Protocol packet
ETH_P_ARP = 0x0806 # Address Resolution packet

# From /usr/include/net/if_arp.h:
ARPHRD_ETHER = 1 # Ethernet 10Mbps
ARPOP_REQUEST = 1 # ARP request
ARPOP_REPLY = 2 # ARP reply

# From /usr/include/linux/in.h:
IPPROTO_ICMP = 1 # Internet Control Message Protocol
IPPROTO_TCP = 6 # Transmission Control Protocol
IPPROTO_UDP = 17 # User Datagram Protocol

class Host(BaseHost):
    def __init__(self, ip_forward: bool):
        super().__init__()

        self._ip_forward = ip_forward

        self._arp_table = {}
        self._pending_packets = []
        self._forwarding_table = ForwardingTable()
        for intf in self.physical_interfaces():
            self._forwarding_table.add_entry(self.prefix_for_int(intf), intf, None)
        for prefix, intf, next_hop in json.loads(os.environ.get('COUGARNET_ROUTES', '[]')):
            self._forwarding_table.add_entry(prefix, intf, next_hop)

    def _handle_frame(self, frame: bytes, intf: str) -> None:
        if len(frame) < 14:
            return
        local_mac = mac_str_to_binary(self.interface_info_single(intf)['address'])
        if frame[:6] not in (local_mac, b'\xff' * 6):
            self.not_my_frame(frame, intf)
            return
        ethertype = int.from_bytes(frame[12:14], 'big')
        if ethertype == ETH_P_IP:
            self.handle_ip(frame[14:], intf)
        elif ethertype == ETH_P_ARP:
            self.handle_arp(frame[14:], intf)

    def handle_ip(self, pkt: bytes, intf: str) -> None:
        if len(pkt) < 20:
            return
        destination = ip_binary_to_str(pkt[16:20])
        if destination not in self.ipv4_addresses():
            self.not_my_packet(pkt, intf)
        elif pkt[9] == IPPROTO_TCP:
            self.handle_tcp(pkt)
        elif pkt[9] == IPPROTO_UDP:
            self.handle_udp(pkt)

    def handle_tcp(self, pkt: bytes) -> None:
        pass

    def handle_udp(self, pkt: bytes) -> None:
        pass

    def handle_arp(self, pkt: bytes, intf: str) -> None:
        if len(pkt) < 28:
            return
        hardware, protocol, hlen, plen, opcode = struct.unpack('!HHBBH', pkt[:8])
        if (hardware, protocol, hlen, plen) != (ARPHRD_ETHER, ETH_P_IP, 6, 4):
            return
        if opcode == ARPOP_REQUEST:
            self.handle_arp_request(pkt, intf)
        elif opcode == ARPOP_REPLY:
            self.handle_arp_response(pkt, intf)

    def handle_arp_response(self, pkt: bytes, intf: str) -> None:
        sender_ip = ip_binary_to_str(pkt[14:18])
        self._arp_table[sender_ip] = mac_binary_to_str(pkt[8:14])
        pending = self._pending_packets
        self._pending_packets = []
        for packet, outgoing, next_hop in pending:
            if next_hop == sender_ip:
                self.send_packet_on_int(packet, outgoing, next_hop)
            else:
                self._pending_packets.append((packet, outgoing, next_hop))

    def handle_arp_request(self, pkt: bytes, intf: str) -> None:
        sender_mac = pkt[8:14]
        sender_ip = pkt[14:18]
        target_ip = pkt[24:28]
        self._arp_table[ip_binary_to_str(sender_ip)] = mac_binary_to_str(sender_mac)
        if ip_binary_to_str(target_ip) not in self.ipv4_addresses(intf):
            return
        local_mac = mac_str_to_binary(self.interface_info_single(intf)['address'])
        reply = struct.pack('!HHBBH', ARPHRD_ETHER, ETH_P_IP, 6, 4, ARPOP_REPLY)
        reply += local_mac + target_ip + sender_mac + sender_ip
        frame = sender_mac + local_mac + struct.pack('!H', ETH_P_ARP) + reply
        self.send_frame(frame, intf)

    def send_packet_on_int(self, pkt: bytes, intf: str, next_hop: str) -> None:
        local_mac = mac_str_to_binary(self.interface_info_single(intf)['address'])
        if next_hop in self._arp_table:
            destination = mac_str_to_binary(self._arp_table[next_hop])
            frame = destination + local_mac + struct.pack('!H', ETH_P_IP) + pkt
            self.send_frame(frame, intf)
            return

        self._pending_packets.append((pkt, intf, next_hop))
        local_ip = ip_str_to_binary(self.ipv4_address_info_single(intf)['address'])
        request = struct.pack('!HHBBH', ARPHRD_ETHER, ETH_P_IP, 6, 4, ARPOP_REQUEST)
        request += local_mac + local_ip + b'\x00' * 6 + ip_str_to_binary(next_hop)
        frame = b'\xff' * 6 + local_mac + struct.pack('!H', ETH_P_ARP) + request
        self.send_frame(frame, intf)

    def send_packet(self, pkt: bytes) -> None:
        if len(pkt) < 20:
            return
        destination = ip_binary_to_str(pkt[16:20])
        intf, next_hop = self._forwarding_table.get_entry(destination)
        if intf is not None:
            self.send_packet_on_int(pkt, intf, destination if next_hop is None else next_hop)

    def forward_packet(self, pkt: bytes) -> None:
        if len(pkt) < 20 or pkt[8] <= 1:
            return
        pkt = pkt[:8] + bytes([pkt[8] - 1]) + pkt[9:]
        self.send_packet(pkt)

    def not_my_frame(self, frame: bytes, intf: str) -> None:
        pass

    def not_my_packet(self, pkt: bytes, intf: str) -> None:
        if self._ip_forward:
            self.forward_packet(pkt)

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

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--router', '-r',
            action='store_const', const=True, default=False,
            help='Act as a router by forwarding IP packets')
    args = parser.parse_args(sys.argv[1:])

    Host(args.router).run()

if __name__ == '__main__':
    main()
