#!/usr/bin/python3

import asyncio
from cougarnet.sim.host import BaseHost

class Switch(BaseHost):
    AGING_TIME = 8

    def __init__(self):
        super().__init__()

        # Include the VLAN so the same MAC can be learned independently on
        # different LANs. Each entry holds its interface and expiration timer.
        self.mac_table = {}

    def _handle_frame(self, frame: bytes, intf: str) -> None:
<<<<<<< Updated upstream
        print('Received frame: %s' % frame.hex(' '))
=======
        if len(frame) < 14:
            return

        if self.is_trunk_link(intf):
            if len(frame) < 18 or frame[12:14] != b'\x81\x00':
                return
            vlan = int.from_bytes(frame[14:16], 'big') & 0x0fff
            frame = frame[:12] + frame[16:]
        else:
            vlan = self.int_to_vlan[intf]

        destination = frame[:6]
        source = frame[6:12]
        key = (vlan, source)
        old_entry = self.mac_table.get(key)
        if old_entry is not None:
            old_entry[1].cancel()
        timer = asyncio.get_event_loop().call_later(
            self.AGING_TIME, self.mac_table.pop, key, None)
        self.mac_table[key] = (intf, timer)

        entry = self.mac_table.get((vlan, destination))
        if destination == b'\xff' * 6 or entry is None:
            outgoing = self.physical_interfaces()
        else:
            outgoing = [entry[0]]

        for out_intf in outgoing:
            if out_intf == intf:
                continue
            if self.is_trunk_link(out_intf):
                tag = b'\x81\x00' + vlan.to_bytes(2, 'big')
                self.send_frame(frame[:12] + tag + frame[12:], out_intf)
            elif self.int_to_vlan[out_intf] == vlan:
                self.send_frame(frame, out_intf)
>>>>>>> Stashed changes

def main():
    Switch().run()

if __name__ == '__main__':
    main()
