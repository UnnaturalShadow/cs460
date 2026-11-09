from __future__ import annotations

import random

TCP_FLAGS_SYN = 0x02
TCP_FLAGS_RST = 0x04
TCP_FLAGS_ACK = 0x10

TCP_STATE_LISTEN = 0
TCP_STATE_SYN_SENT = 1
TCP_STATE_SYN_RECEIVED = 2
TCP_STATE_ESTABLISHED = 3
TCP_STATE_FIN_WAIT_1 = 4
TCP_STATE_FIN_WAIT_2 = 5
TCP_STATE_CLOSE_WAIT = 6
TCP_STATE_CLOSING = 7
TCP_STATE_LAST_ACK = 8
TCP_STATE_TIME_WAIT = 9
TCP_STATE_CLOSED = 10

from headers import IPv4Header, UDPHeader, TCPHeader, \
        IP_HEADER_LEN, UDP_HEADER_LEN, TCP_HEADER_LEN, \
        TCPIP_HEADER_LEN, UDPIP_HEADER_LEN


#From /usr/include/linux/in.h:
IPPROTO_TCP = 6 # Transmission Control Protocol
IPPROTO_UDP = 17 # User Datagram Protocol

class UDPSocket:
    def __init__(self, local_addr: str, local_port: int,
            send_ip_packet_func: callable,
            notify_on_data_func: callable) -> UDPSocket:

        self._local_addr = local_addr
        self._local_port = local_port
        self._send_ip_packet = send_ip_packet_func
        self._notify_on_data = notify_on_data_func

        self.buffer = []

    def handle_packet(self, pkt: bytes) -> None:
        ip_hdr = IPv4Header.from_bytes(pkt[:IP_HEADER_LEN])
        udp_hdr = UDPHeader.from_bytes(pkt[IP_HEADER_LEN:UDPIP_HEADER_LEN])
        data = pkt[UDPIP_HEADER_LEN:IP_HEADER_LEN + udp_hdr.length]
        self.buffer.append((data, ip_hdr.src, udp_hdr.sport))
        self._notify_on_data()

    @classmethod
    def create_packet(cls, src: str, sport: int, dst: str, dport: int,
            data: bytes=b'') -> bytes:
        udp_hdr = UDPHeader(sport, dport, UDP_HEADER_LEN + len(data), 0)
        ip_hdr = IPv4Header(UDPIP_HEADER_LEN + len(data), 64,
                IPPROTO_UDP, 0, src, dst)
        return ip_hdr.to_bytes() + udp_hdr.to_bytes() + data

    def send_packet(self, remote_addr: str, remote_port: int,
            data: bytes) -> None:
        pkt = self.create_packet(self._local_addr, self._local_port,
                remote_addr, remote_port, data)
        self._send_ip_packet(pkt)

    def recvfrom(self) -> tuple[bytes, str, int]:
        return self.buffer.pop(0)

    def sendto(self, data: bytes, remote_addr: str, remote_port: int) -> None:
        self.send_packet(remote_addr, remote_port, data)


class TCPSocketBase:
    def handle_packet(self, pkt: bytes) -> None:
        pass

class TCPListenerSocket(TCPSocketBase):
    def __init__(self, local_addr: str, local_port: int,
            handle_new_client_func: callable, send_ip_packet_func: callable,
            notify_on_data_func: callable) -> TCPListenerSocket:

        # These are all vars that are saved away for instantiation of TCPSocket
        # objects when new connections are created.
        self._local_addr = local_addr
        self._local_port = local_port
        self._handle_new_client = handle_new_client_func

        self._send_ip_packet_func = send_ip_packet_func
        self._notify_on_data_func = notify_on_data_func


    def handle_packet(self, pkt: bytes) -> None:
        ip_hdr = IPv4Header.from_bytes(pkt[:IP_HEADER_LEN])
        tcp_hdr = TCPHeader.from_bytes(pkt[IP_HEADER_LEN:TCPIP_HEADER_LEN])
        data = pkt[TCPIP_HEADER_LEN:]

        if tcp_hdr.flags & TCP_FLAGS_SYN:
            sock = TCPSocket(self._local_addr, self._local_port,
                    ip_hdr.src, tcp_hdr.sport,
                    TCP_STATE_LISTEN,
                    send_ip_packet_func=self._send_ip_packet_func,
                    notify_on_data_func=self._notify_on_data_func)

            self._handle_new_client(self._local_addr, self._local_port,
                    ip_hdr.src, tcp_hdr.sport, sock)

            sock.handle_packet(pkt)
        elif not tcp_hdr.flags & TCP_FLAGS_RST:
            self._send_ip_packet_func(TCPSocket.create_packet(
                    self._local_addr, self._local_port,
                    ip_hdr.src, tcp_hdr.sport, tcp_hdr.ack, 0, TCP_FLAGS_RST))


class TCPSocket(TCPSocketBase):
    def __init__(self, local_addr: str, local_port: int,
            remote_addr: str, remote_port: int, state: int,
            send_ip_packet_func: callable,
            notify_on_data_func: callable) -> TCPSocket:

        # The local/remote address/port information associated with this
        # TCPConnection
        self._local_addr = local_addr
        self._local_port = local_port
        self._remote_addr = remote_addr
        self._remote_port = remote_port

        # The current state (TCP_STATE_LISTEN, TCP_STATE_CLOSED, etc.)
        self.state = state

        # Helpful methods for helping us send IP packets and
        # notifying the application that we have received data.
        self._send_ip_packet = send_ip_packet_func
        self._notify_on_data = notify_on_data_func

        # Base sequence number
        self.base_seq_self = self.initialize_seq()

        # Base sequence number for the remote side
        self.base_seq_other = None


    @classmethod
    def connect(cls, local_addr: str, local_port: int,
            remote_addr: str, remote_port: int,
            send_ip_packet_func: callable,
            notify_on_data_func: callable) -> TCPSocket:
        sock = cls(local_addr, local_port,
                remote_addr, remote_port,
                TCP_STATE_CLOSED,
                send_ip_packet_func, notify_on_data_func)

        sock.initiate_connection()

        return sock


    def handle_packet(self, pkt: bytes) -> None:
        ip_hdr = IPv4Header.from_bytes(pkt[:IP_HEADER_LEN])
        tcp_hdr = TCPHeader.from_bytes(pkt[IP_HEADER_LEN:TCPIP_HEADER_LEN])
        data = pkt[TCPIP_HEADER_LEN:]

        if self.state != TCP_STATE_ESTABLISHED:
            self.continue_connection(pkt)

        if self.state == TCP_STATE_ESTABLISHED:
            if data:
                # handle data
                self.handle_data(pkt)
            if tcp_hdr.flags & TCP_FLAGS_ACK:
                # handle ACK
                self.handle_ack(pkt)


    def initialize_seq(self) -> int:
        return random.randint(0, 65535)


    def initiate_connection(self) -> None:
        self.state = TCP_STATE_SYN_SENT
        self.send_packet(self.base_seq_self, 0, TCP_FLAGS_SYN)

    def handle_syn(self, pkt: bytes) -> None:
        hdr = TCPHeader.from_bytes(pkt[IP_HEADER_LEN:TCPIP_HEADER_LEN])
        if not hdr.flags & TCP_FLAGS_SYN:
            if not hdr.flags & TCP_FLAGS_RST:
                self.send_packet(hdr.ack, 0, TCP_FLAGS_RST)
            return
        self.base_seq_other = hdr.seq
        self.state = TCP_STATE_SYN_RECEIVED
        self.send_packet(self.base_seq_self, (hdr.seq + 1) & 0xffffffff,
                TCP_FLAGS_SYN | TCP_FLAGS_ACK)

    def handle_synack(self, pkt: bytes) -> None:
        hdr = TCPHeader.from_bytes(pkt[IP_HEADER_LEN:TCPIP_HEADER_LEN])
        if (not hdr.flags & TCP_FLAGS_SYN or
                not hdr.flags & TCP_FLAGS_ACK or
                hdr.ack != (self.base_seq_self + 1) & 0xffffffff):
            return
        self.base_seq_other = hdr.seq
        self.state = TCP_STATE_ESTABLISHED
        self.send_packet((self.base_seq_self + 1) & 0xffffffff,
                (hdr.seq + 1) & 0xffffffff, TCP_FLAGS_ACK)

    def handle_ack_after_synack(self, pkt: bytes) -> None:
        hdr = TCPHeader.from_bytes(pkt[IP_HEADER_LEN:TCPIP_HEADER_LEN])
        if (hdr.flags & TCP_FLAGS_SYN or
                not hdr.flags & TCP_FLAGS_ACK or
                hdr.ack != (self.base_seq_self + 1) & 0xffffffff):
            return
        self.state = TCP_STATE_ESTABLISHED

    def continue_connection(self, pkt: bytes) -> None:
        if self.state == TCP_STATE_LISTEN:
            self.handle_syn(pkt)
        elif self.state == TCP_STATE_SYN_SENT:
            self.handle_synack(pkt)
        elif self.state == TCP_STATE_SYN_RECEIVED:
            self.handle_ack_after_synack(pkt)

    def send_data(self, data: bytes, flags: int=0) -> None:
        pass

    @classmethod
    def create_packet(cls, src: str, sport: int, dst: str, dport: int,
            seq: int, ack: int, flags: int, data: bytes=b'') -> bytes:
        tcp_hdr = TCPHeader(sport, dport, seq, ack, flags, 0)
        ip_hdr = IPv4Header(TCPIP_HEADER_LEN + len(data), 64,
                IPPROTO_TCP, 0, src, dst)
        return ip_hdr.to_bytes() + tcp_hdr.to_bytes() + data

    def send_packet(self, seq: int, ack: int, flags: int,
            data: bytes=b'') -> None:
        pkt = self.create_packet(self._local_addr, self._local_port,
                self._remote_addr, self._remote_port, seq, ack, flags, data)
        self._send_ip_packet(pkt)

    def handle_data(self, pkt: bytes) -> None:
        pass

    def handle_ack(self, pkt: bytes) -> None:
        pass
