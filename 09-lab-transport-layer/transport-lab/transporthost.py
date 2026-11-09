from cougarnet.util import \
        ip_str_to_binary, ip_binary_to_str

from headers import IPv4Header, UDPHeader, TCPHeader, ICMPHeader, \
        IP_HEADER_LEN, UDP_HEADER_LEN, TCP_HEADER_LEN, \
        TCPIP_HEADER_LEN, UDPIP_HEADER_LEN
from host import Host, IPPROTO_ICMP
from mysocket import UDPSocket, TCPSocketBase, TCPSocket, TCP_FLAGS_RST

class TransportHost(Host):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.socket_mapping_udp = {}
        self.socket_mapping_tcp = {}

    def handle_tcp(self, pkt: bytes) -> None:
        ip_hdr = IPv4Header.from_bytes(pkt[:IP_HEADER_LEN])
        tcp_hdr = TCPHeader.from_bytes(pkt[IP_HEADER_LEN:TCPIP_HEADER_LEN])
        key = (ip_hdr.dst, tcp_hdr.dport, ip_hdr.src, tcp_hdr.sport)
        sock = self.socket_mapping_tcp.get(key)
        if sock is None:
            sock = self.socket_mapping_tcp.get(
                    (ip_hdr.dst, tcp_hdr.dport, None, None))
        if sock is None:
            self.no_socket_tcp(pkt)
        else:
            sock.handle_packet(pkt)

    def handle_udp(self, pkt: bytes) -> None:
        ip_hdr = IPv4Header.from_bytes(pkt[:IP_HEADER_LEN])
        udp_hdr = UDPHeader.from_bytes(pkt[IP_HEADER_LEN:UDPIP_HEADER_LEN])
        sock = self.socket_mapping_udp.get((ip_hdr.dst, udp_hdr.dport))
        if sock is None:
            self.no_socket_udp(pkt)
        else:
            sock.handle_packet(pkt)

    def install_socket_udp(self, local_addr: str, local_port: int,
            sock: UDPSocket) -> None:
        self.socket_mapping_udp[(local_addr, local_port)] = sock

    def install_listener_tcp(self, local_addr: str, local_port: int,
            sock: TCPSocketBase) -> None:
        self.socket_mapping_tcp[(local_addr, local_port, None, None)] = sock

    def install_socket_tcp(self, local_addr: str, local_port: int,
            remote_addr: str, remote_port: int, sock: TCPSocketBase) -> None:
        self.socket_mapping_tcp[(local_addr, local_port, \
                remote_addr, remote_port)] = sock

    def no_socket_udp(self, pkt: bytes) -> None:
        ip_hdr = IPv4Header.from_bytes(pkt[:IP_HEADER_LEN])
        # Destination unreachable (3), port unreachable (3).
        payload = ICMPHeader(3, 3, 0).to_bytes() + pkt[:ip_hdr.length]
        reply = IPv4Header(IP_HEADER_LEN + len(payload), 64,
                IPPROTO_ICMP, 0, ip_hdr.dst, ip_hdr.src)
        self.send_packet(reply.to_bytes() + payload)

    def no_socket_tcp(self, pkt: bytes) -> None:
        ip_hdr = IPv4Header.from_bytes(pkt[:IP_HEADER_LEN])
        tcp_hdr = TCPHeader.from_bytes(pkt[IP_HEADER_LEN:TCPIP_HEADER_LEN])
        # Never respond to a reset with another reset.
        if tcp_hdr.flags & TCP_FLAGS_RST:
            return
        self.send_packet(TCPSocket.create_packet(ip_hdr.dst, tcp_hdr.dport,
                ip_hdr.src, tcp_hdr.sport, tcp_hdr.ack, 0, TCP_FLAGS_RST))
