# CS 460 Networking Reference

This is a consolidated reference for the packet structures implemented in CS 460. The diagrams describe the bytes handled by the labs, not every field that appears on a physical network.

# Table of Contents

 - [Overview](#overview)
 - [Ethernet](#ethernet)
 - [ARP packet](#arp-packet)
 - [IPv4 header](#ipv4-header)
 - [UDP header](#udp-header)
 - [TCP header](#tcp-header)
 - [ICMP header](#icmp-header)
 - [Various Notes](#various-notes)
	 - [Endianness](#endianness)
	 - [Layering Options](#layering-options)

## Overview

Each packet structure is shown separately below. The columns are bit positions within a 32-bit row; fields are labeled above the space they occupy. The Ethernet frame is simplified to simply show eight bits per column, with the row being all the bits in an Ethernet frame, rather than just 32 bits.

A table giving the **Field**, **Size**, and **Description** of each field follows. There is another column called **Example** giving example bytes for each field. Asterisks are for fields where bytes are shared between fields. In these cases, a short paragraph titled **Shared Bytes** follows the table for an explanation.

Finally, at the bottom is all the bytes from the example concatenated together, giving a complete example of a given packet structure.

## Ethernet

### Ethernet frame

<table border="1" style="border:3px solid black;">
<tr><th>00</th><th>08</th><th>16</th><th>24</th><th>32</th><th>40</th><th>48</th><th>56</th><th>64</th><th>72</th><th>80</th><th>88</th><th>96</th><th>104</th></tr>
<tr><td colspan="6">Destination MAC</td><td colspan="6">Source MAC</td><td colspan="2">EtherType</td></tr>
</table>

### 802.1Q VLAN Ethernet frame

<table border="1" style="border:3px solid black;">
<tr><th>00</th><th>08</th><th>16</th><th>24</th><th>32</th><th>40</th><th>48</th><th>56</th><th>64</th><th>72</th><th>80</th><th>88</th><th>96</th><th>104</th><th>112</th><th>120</th><th>128</th><th>136</th></tr>
<tr><td colspan="6">Destination MAC</td><td colspan="6">Source MAC</td><td colspan="4">802.1Q Header</td><td colspan="2">EtherType</td></tr>
</table>

| Field | Size | Description | Example |
| --- | ---: | --- | --- |
| Destination MAC address | 6 bytes | Intended receiver; `ff:ff:ff:ff:ff:ff` is broadcast | `01 02 03 04 05 06` |
| Source MAC address | 6 bytes | Sender on the local link | `aa bb cc dd ee ff` |
| 802.1Q header | 4 bytes | An optional tag to support VLANs | `81 00 00 19` |
| EtherType | 2 bytes | Identifies the payload protocol | `08 00` |
| *Payload* | *variable* | Usually an IPv4 datagram or ARP packet. | N/A |

For the 802.1Q header field, the most significant (left-most) 16 bits of the 802.1Q
header have the value `0x8100` to indicate that it is an 802.1Q frame.
The least significant (right-most) 12 bits of the 802.1Q header contain
the value of the VLAN ID. The 4 bits in between can be left as zero.

#### Full Example:
```text
01 02 03 04 05 06 aa bb cc dd ee ff 81 00 00 19 08 00
```

## ARP packet

<table border="1" style="border:3px solid black;">
<tr>
<th>00</th><th>01</th><th>02</th><th>03</th><th>04</th><th>05</th><th>06</th><th>07</th>
<th>08</th><th>09</th><th>10</th><th>11</th><th>12</th><th>13</th><th>14</th><th>15</th>
<th>16</th><th>17</th><th>18</th><th>19</th><th>20</th><th>21</th><th>22</th><th>23</th>
<th>24</th><th>25</th><th>26</th><th>27</th><th>28</th><th>29</th><th>30</th><th>31</th></tr>
<tr><td colspan="16">Hardware type</td><td colspan="16">Protocol type</td></tr>
<tr><td colspan="8">Hardware address length</td><td colspan="8">Protocol address length</td><td colspan="16">Opcode</td></tr>
<tr><td colspan="32">Sender hardware address (bytes 0-3)</td></tr>
<tr><td colspan="16">Sender hardware address (bytes 4-5)</td><td colspan="16">Sender protocol address (bytes 0-1)</td></tr>
<tr><td colspan="16">Sender protocol address (bytes 2-3)</td><td colspan="16">Target hardware address (bytes 0-1)</td></tr>
<tr><td colspan="32">Target hardware address (bytes 2-5)</td></tr>
<tr><td colspan="32">Target protocol address</td></tr>
<tr><td colspan="32">Data</td></tr>
</table>

| Field | Size | Description | Example |
| --- | ---: | --- | --- |
| Hardware type | 2 bytes | Ethernet: `ARPHRD_ETHER = 1` | `00 01` |
| Protocol type | 2 bytes | IPv4: `ETH_P_IP = 0x0800` | `08 00` |
| Hardware address length | 1 byte | Ethernet MAC length: `6` | `06` |
| Protocol address length | 1 byte | IPv4 address length: `4` | `04` |
| Opcode | 2 bytes | Request `ARPOP_REQUEST = 1`, reply `ARPOP_REPLY = 2` | `00 01` |
| Sender hardware address | 6 bytes | Sender MAC | `11 22 33 44 55 66` (11:22:33:44:55:66) |
| Sender protocol address | 4 bytes | Sender IPv4 address | `c0 00 02 01` (192.0.2.1) |
| Target hardware address | 6 bytes | Target MAC; may be zero in a request | `aa bb cc dd ee ff` (aa:bb:cc:dd:ee:ff) |
| Target protocol address | 4 bytes | Target IPv4 address | `c0 00 02 02` (192.0.2.1) |
| *Data* | *variable* | Not needed for the basic lab | N/A |

#### Full Example:
```text
00 01 08 00 06 04 00 01 11 22 33 44 55 66 c0 00
02 01 00 00 00 00 aa bb cc dd ee ff c0 00 02 02
```

## IPv4 header

<table border="1" style="border:3px solid black;">
<tr><th>00</th><th>01</th><th>02</th><th>03</th><th>04</th><th>05</th><th>06</th><th>07</th><th>08</th><th>09</th><th>10</th><th>11</th><th>12</th><th>13</th><th>14</th><th>15</th><th>16</th><th>17</th><th>18</th><th>19</th><th>20</th><th>21</th><th>22</th><th>23</th><th>24</th><th>25</th><th>26</th><th>27</th><th>28</th><th>29</th><th>30</th><th>31</th></tr>
<tr><td colspan="4">Version</td><td colspan="4">IHL</td><td colspan="6">DSCP</td><td colspan="2">ECN</td><td colspan="16">Total length</td></tr>
<tr><td colspan="16">Identification</td><td colspan="3">Flags</td><td colspan="13">Fragment offset</td></tr>
<tr><td colspan="8">TTL</td><td colspan="8">Protocol</td><td colspan="16">Header checksum</td></tr>
<tr><td colspan="32">Source address</td></tr>
<tr><td colspan="32">Destination address</td></tr>
</table>

| Field | Size | Notes | Example |
| --- | ---: | --- | --- |
| Version | 4 bits | IP version; set to `4` for IPv4 | `45` * |
| IHL | 4 bits | Header length in 32-bit words; `5` means 20 bytes | * |
| DSCP | 6 bits | In this class, set to `0` | `00` * |
| ECN | 2 bits | In this class, set to `0` | * |
| Total length | 2 bytes | Length of IPv4 header plus payload, in bytes | `00 21` |
| Identification | 2 bytes | Fragmentation support | `12 34` |
| Flags | 3 bits | Fragmentation control | `40 00` * |
| Fragment offset | 13 bits | Fragmentation support | * |
| TTL | 1 byte | Decremented by each router | `40` |
| Protocol | 1 byte | Identifies protocol of data contained in payload | `11` |
| Header checksum | 2 bytes | Used for error checking of IPv4 header | `00 00` |
| Source address | 4 bytes | Sender IPv4 address | `c0 00 02 01` (192.0.2.1) |
| Destination address | 4 bytes | Receiver IPv4 address | `c0 00 02 02` (192.0.2.2) |
| Options and padding | variable | Included only when IHL is greater than 5 | N/A |
| *Payload* | *variable* | UDP, TCP, ICMP, or another protocol | N/A |

**Shared Bytes:** Asterisks are for bytes that are shared between fields. Byte ``45`` is ``01000101``: the first four bits, ``0100``, contains Version ``4``, and the last four bits, ``0101``, contains IHL ``5``. Byte ``00`` is ``00000000``: the first six bits are ``0`` for DSCP, and last two bits are ``0`` for ECN. Bytes ``40 00`` are ``01000000 00000000``: the first 3 bits, ``010``, are the Flags (Reserved ``0``, Don't Fragment/DF ``1``, More Fragments/MF ``0``), and the remaining 13 bits are the Fragment Offset, ``0``.

#### Full Example:
```text
45 00 00 21 12 34 40 00 40 11 00 00 c0 00 02 01
c0 00 02 02
```

## UDP header

<table border="1" style="border:3px solid black;">
<tr><th>00</th><th>01</th><th>02</th><th>03</th><th>04</th><th>05</th><th>06</th><th>07</th><th>08</th><th>09</th><th>10</th><th>11</th><th>12</th><th>13</th><th>14</th><th>15</th><th>16</th><th>17</th><th>18</th><th>19</th><th>20</th><th>21</th><th>22</th><th>23</th><th>24</th><th>25</th><th>26</th><th>27</th><th>28</th><th>29</th><th>30</th><th>31</th></tr>
<tr><td colspan="16">Source port</td><td colspan="16">Destination port</td></tr>
<tr><td colspan="16">Length</td><td colspan="16">Checksum</td></tr>
</table>

| Field | Size | Description | Example |
| --- | ---: | --- | --- |
| Source port | 2 bytes | Sending application port | `0f a0` |
| Destination port | 2 bytes | Receiving application port | `04 d2` |
| Length | 2 bytes | UDP header plus UDP payload | `00 0d` |
| Checksum | 2 bytes | Set to zero in the transport lab | `00 00` |
| *Data* | *variable* | Application payload | `68 65 6c 6c 6f` |

#### Full Example:
```text
0f a0 04 d2 00 0d 00 00 68 65 6c 6c 6f
```

## TCP header

<table border="1">
<tr><th>00</th><th>01</th><th>02</th><th>03</th><th>04</th><th>05</th><th>06</th><th>07</th><th>08</th><th>09</th><th>10</th><th>11</th><th>12</th><th>13</th><th>14</th><th>15</th><th>16</th><th>17</th><th>18</th><th>19</th><th>20</th><th>21</th><th>22</th><th>23</th><th>24</th><th>25</th><th>26</th><th>27</th><th>28</th><th>29</th><th>30</th><th>31</th></tr>
<tr><td colspan="16">Source port</td><td colspan="16">Destination port</td></tr>
<tr><td colspan="32">Sequence number</td></tr>
<tr><td colspan="32">Acknowledgment number</td></tr>
<tr><td colspan="4">Data offset</td><td colspan="3">Reserved</td><td colspan="3">ECN</td><td colspan="6">Control bits</td><td colspan="16">Window</td></tr>
<tr><td colspan="16">Checksum</td><td colspan="16">Urgent pointer</td></tr>
<tr><td colspan="32">Options and padding</td></tr>
</table>

| Field | Size | Description | Example |
| --- | ---: | --- | --- |
| Source port | 2 bytes | Sending application port | `0f a0` |
| Destination port | 2 bytes | Receiving application port | `04 d2` |
| Sequence number | 4 bytes | Position of segment data in the byte stream | `11 22 33 44` |
| Acknowledgment number | 4 bytes | Next sequence number that the sender is expecting | `11 22 33 44` |
| Data offset | 4 bits | Header length in 4-byte words; `5` means 20 bytes | `50 12` * |
| Reserved | 3 bits | `000` in the lab; not currently used | * |
| ECN | 3 bits | `000` in the lab | * |
| Control bits | 6 bits | `URG`, `ACK`, `PSH`, `RST`, `SYN`, `FIN` | * |
| Window | 2 bytes | Advertised receive window; use `64` as a reasonable value for the labs | `00 40` |
| Checksum | 2 bytes | Set to zero in the transport lab | `00 00` |
| Urgent pointer | 2 bytes | Not used in the lab, set to zero | `00 00` |
| Options and padding | *variable* | Not used in labs. Various options and padding to make header size a multiple of 4 bytes. | N/A |
| *Data* | *variable* | Application payload | `68 65 6c 6c 6f` |

**Shared Bytes:** Asterisks are for bytes that are shared between fields. Bytes ``50 12`` are ``01010000 00010010``: The first four bits ``0101`` are the Data Offset, equaling ``5`` words (20 bytes). The next three bits ``000`` are Reserved, which is just set to ``0``. The next three bits ``000`` are for ECN, and the last six bits, ``010010``, are the Control Bits, equaling ACK + SYN (using the order URG, ACK, PSH, RST, SYN, FIN). The packed fields concatenate as ``0101 000 000 010010``.

#### Full Example:
```text
0f a0 04 d2 11 22 33 44 11 22 33 44 50 12 00 40
00 00 00 00 00 00 68 65 6c 6c 6f
```

## ICMP header

<table border="1">
<tr><th>00</th><th>01</th><th>02</th><th>03</th><th>04</th><th>05</th><th>06</th><th>07</th><th>08</th><th>09</th><th>10</th><th>11</th><th>12</th><th>13</th><th>14</th><th>15</th><th>16</th><th>17</th><th>18</th><th>19</th><th>20</th><th>21</th><th>22</th><th>23</th><th>24</th><th>25</th><th>26</th><th>27</th><th>28</th><th>29</th><th>30</th><th>31</th></tr>
<tr><td colspan="8">Type</td><td colspan="8">Code</td><td colspan="16">Checksum</td></tr>
<tr><td colspan="32">Message-specific fields and data</td></tr>
</table>

| Field | Size | Description | Example |
| --- | ---: | --- | --- |
| Type | 1 byte | Identifies the ICMP message type; set to `3` for destination unreachable | `03` |
| Code | 1 byte | Provides additional context for the message type; set to `3` for port unreachable | `03` |
| Checksum | 2 bytes | Used for error checking of the ICMP header and message data; set to zero for lab | `00 00` |
| Message-specific fields and data | 4 bytes | Depends on the ICMP message type; set to zero for lab | `00 00 00 00` |
| *Data* | *variable* | Payload data | `68 65 6c 6c 6f` |

#### Full Example:
```text
03 03 00 00 00 00 00 00 68 65 6c 6c 6f
```

## Various Notes

### Endianness

In this class, **network byte order** will be used, which is **big-endian**. You likely will not have to worry about this at all in this class, but this needs to be noted.

Examples below use the same numeric value in both byte orders. The bit order within each byte does not change; only the order of complete bytes changes.

| Value size | Numeric value | Big-endian bytes | Little-endian bytes |
| --- | --- | --- | --- |
| 1 byte | `0x12` | `12` | `12` |
| 2 bytes | `0x1234` | `12 34` | `34 12` |
| 4 bytes | `0x12345678` | `12 34 56 78` | `78 56 34 12` |

For example, the 16-bit value `0x1234` is transmitted as `12 34` in network byte order. Optional further reading: [Endianness - Wikipedia](https://en.wikipedia.org/wiki/Endianness).

### Layering Options

These are the main protocol combinations used in the labs:

```text
Ethernet Frame -> IPv4 -> UDP
Ethernet Frame -> IPv4 -> TCP
Ethernet Frame -> IPv4 -> ICMP
Ethernet Frame -> ARP
```

Note that you may not construct these full combinations. For instance, in the first lab, link-layer, you will only construct the Ethernet Frame - no payload inside it. However, it is important to remember how the OSI model behind this uses abstraction layers.
