#!/usr/bin/env python3

import subprocess
import re

HOSTS = [
    "byu.edu",
    "stanford.edu",
    "ufl.edu",
    "uni-heidelberg.de",
]

PROPAGATION_SPEED = 2.5e8  # meters/second


def run_command(command):
    result = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print(f"Command failed: {' '.join(command)}")
        print(result.stderr)
        return None

    return result.stdout


def get_ping_results(host):
    output = run_command(["ping", "-4", "-c", "5", host])

    if not output:
        return None

    # Linux ping usually ends with something like:
    # rtt min/avg/max/mdev = 12.345/13.456/14.567/0.800 ms
    match = re.search(
        r"(?:rtt|round-trip) min/avg/max/(?:mdev|stddev) = "
        r"([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+) ms",
        output
    )

    if not match:
        print(f"Could not parse ping output for {host}")
        print(output)
        return None

    minimum_rtt_ms = float(match.group(1))

    # RTT is round-trip, so divide by 2.
    one_way_delay_seconds = (minimum_rtt_ms / 1000) / 2

    # distance = speed × time
    distance_meters = PROPAGATION_SPEED * one_way_delay_seconds
    distance_km = distance_meters / 1000

    return {
        "min_rtt_ms": minimum_rtt_ms,
        "one_way_delay_s": one_way_delay_seconds,
        "distance_km": distance_km,
    }


def get_mtr_results(host):
    output = run_command([
        "mtr",
        "-4",
        "--report-cycles", "5",
        "--report-wide",
        "--show-ips",
        host,
    ])

    if not output:
        return None

    # mtr hop lines normally begin with a hop number:
    #  1.|-- router ...
    #  2.|-- router ...
    hop_numbers = []

    for line in output.splitlines():
        match = re.match(r"\s*(\d+)\.\|", line)

        if match:
            hop_numbers.append(int(match.group(1)))

    if not hop_numbers:
        print(f"Could not determine hop count for {host}")
        print(output)
        return None

    # The highest numbered hop should be the destination.
    number_of_hops = max(hop_numbers)

    return {
        "hops": number_of_hops,
        "raw_output": output,
    }


def main():
    print("=" * 72)
    print("Network Delay / Distance / Hop Calculator")
    print("=" * 72)

    for host in HOSTS:
        print(f"\n{host}")
        print("-" * 72)

        ping = get_ping_results(host)
        mtr = get_mtr_results(host)

        if ping:
            print(f"Minimum RTT:             {ping['min_rtt_ms']:.3f} ms")
            print(f"Minimum one-way delay:   {ping['one_way_delay_s']:.6f} s")
            print(f"Farthest distance:       {ping['distance_km']:.2f} km")

        if mtr:
            print(f"Number of hops:          {mtr['hops']}")

        print()


if __name__ == "__main__":
    main()