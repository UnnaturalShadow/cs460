class TCPSendBuffer(object):
    def __init__(self, seq: int):
        self.buffer = b''
        self.base_seq = seq
        self.next_seq = self.base_seq
        self.last_seq = self.base_seq

    def bytes_not_yet_sent(self) -> int:
        return self.last_seq - self.next_seq

    def bytes_outstanding(self) -> int:
        return self.next_seq - self.base_seq

    def put(self, data: bytes) -> None:
        self.buffer += data
        self.last_seq += len(data)

    def get(self, size: int) -> tuple[bytes, int]:
        sequence = self.next_seq
        offset = sequence - self.base_seq
        data = self.buffer[offset:offset + max(0, size)]
        self.next_seq += len(data)
        return data, sequence

    def get_for_resend(self, size: int) -> tuple[bytes, int]:
        size = min(max(0, size), self.bytes_outstanding())
        return self.buffer[:size], self.base_seq

    def slide(self, sequence: int) -> None:
        if self.base_seq < sequence <= self.next_seq:
            self.buffer = self.buffer[sequence - self.base_seq:]
            self.base_seq = sequence


class TCPReceiveBuffer(object):
    def __init__(self, seq: int):
        self.buffer = {}
        self.base_seq = seq

    def put(self, data: bytes, sequence: int) -> None:
        if sequence + len(data) <= self.base_seq:
            return
        if sequence < self.base_seq:
            data = data[self.base_seq - sequence:]
            sequence = self.base_seq
        if len(data) > len(self.buffer.get(sequence, b'')):
            self.buffer[sequence] = data

        # Earlier segments own overlapping bytes; retain only unique suffixes.
        segments = {}
        end = self.base_seq
        for start, segment in sorted(self.buffer.items()):
            trim = max(0, end - start)
            if trim < len(segment):
                segments[start + trim] = segment[trim:]
                end = start + len(segment)
        self.buffer = segments

    def get(self) -> tuple[bytes, int]:
        sequence = self.base_seq
        chunks = []
        while self.base_seq in self.buffer:
            data = self.buffer.pop(self.base_seq)
            chunks.append(data)
            self.base_seq += len(data)
        return b''.join(chunks), sequence
