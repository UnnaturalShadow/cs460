#!/usr/bin/env python3

import argparse
import re
import signal
import subprocess
import sys

LOG_PREFIX = r'^(?P<time>\d+\.\d+)\s+(?P<hostname>\S+)\s+'
LOG_START_RE = re.compile(LOG_PREFIX + r'START$')
LOG_STOP_RE = re.compile(LOG_PREFIX + r'STOP$')
LOG_ARP_RECV_RE = re.compile(LOG_PREFIX + \
        r'Received ARP (?P<type>REQUEST|REPLY) ' + \
        r'from (?P<src_ip>\d+\.\d+\.\d+\.\d+)/' + \
        r'(?P<src_mac>[0-9a-f]{2}(:[0-9a-f]{2}){5}) for (\d+\.\d+\.\d+\.\d+)')
LOG_ICMP_RECV_RE = re.compile(LOG_PREFIX + \
        r'Received ICMP packet from (?P<src_ip>\d+\.\d+\.\d+\.\d+)')

NEXT_ITERATION_SLACK = 0.15 # 150 ms
MAX_INTERVAL = 0.5 # 500 ms

class Lab2Tester:
    cmd = []
    expected_observations = []

    def __init__(self, verbosity: int = 0, terminal: str|None = None):
        self.verbosity = verbosity
        self.terminal = terminal

    def evaluate(self, iteration, time_seen, observations):
        if iteration >= len(self.expected_observations):
            # not evaluated
            return None

        solution = self.expected_observations[iteration]
        if solution is None:
            # not evaluated
            return None

        i = 0
        for expected_cat, expected_hostnames in solution:
            observed_hostnames = []
            num_hostnames = len(expected_hostnames)
            j = i
            for j in range(i, i + num_hostnames):
                if j >= len(observations):
                    break
                observed_cat, observed_hostname = observations[j]
                if observed_cat != expected_cat:
                    sys.stderr.write(('ERROR: Time %0.3f: ' + \
                            'Expected %d %s at %s, but observed %s at %s\n') % \
                            (time_seen, num_hostnames, expected_cat,
                                ', '.join(expected_hostnames),
                                observed_cat, observed_hostname))
                    return False
                observed_hostnames.append(observed_hostname)
            j += 1
            i = j

            expected_hostnames = sorted(expected_hostnames)
            observed_hostnames = sorted(observed_hostnames)
            if expected_hostnames != observed_hostnames:
                sys.stderr.write(('ERROR: Time %0.3f: ' + \
                        'Expected %s at %s, but observed %s at %s\n') % \
                        (time_seen, expected_cat,
                            ', '.join(expected_hostnames),
                            expected_cat, ', '.join(observed_hostnames)))
                return False

        if len(observations) > j:
            sys.stderr.write(('ERROR: Time %0.3f: ' + \
                    'Unexpected %s at %s\n') % \
                    (time_seen, observations[j][0], observations[j][1]))
            return False

        return True

    def evaluate_lines(self, lines):
        # initialize
        start_time = None
        max_time = None
        next_time = None
        iteration = None
        observations = None

        evaluated = 0
        success = 0

        for line in lines:
            m = LOG_START_RE.search(line)
            if m is not None:
                start_time = float(m.group('time')) + 1.0
                max_time = start_time + MAX_INTERVAL
                next_time = start_time + (1 - NEXT_ITERATION_SLACK)
                iteration = 0
                observations = []
                continue

            cat = ''
            m = LOG_ARP_RECV_RE.search(line)
            if m is not None:
                hostname = m.group('hostname')
                if m.group('type') == 'REQUEST':
                    cat = 'ARP_REQUEST'
                else:
                    cat = 'ARP_REPLY'
            else:
                m = LOG_ICMP_RECV_RE.search(line)
                if m is not None:
                    hostname = m.group('hostname')
                    cat = 'ICMP'

                else:
                    m = LOG_STOP_RE.search(line)
                    if m is not None:
                        hostname = ''
                        cat = ''

            if m is not None:
                mytime = float(m.group('time'))

                while mytime > max_time:
                    if not observations:
                        # if we have gone through the loop more than once, then
                        # don't reduce by NEXT_ITERATION_SLACK
                        start_time = start_time + NEXT_ITERATION_SLACK
                        next_time = next_time + NEXT_ITERATION_SLACK

                    # evaluate
                    result = self.evaluate(iteration, start_time, observations)
                    if result is not None:
                        evaluated += 1
                        if result:
                            success += 1

                    # reset
                    iteration += 1
                    start_time = next_time

                    max_time = start_time + MAX_INTERVAL
                    next_time = start_time + (1.0 - NEXT_ITERATION_SLACK)
                    observations = []

                if not observations:
                    # if this is the first host seen, then save the time
                    start_time = mytime
                    max_time = start_time + MAX_INTERVAL
                    next_time = start_time + (1.0 - NEXT_ITERATION_SLACK)

                observations.append((cat, hostname))

        # evaluate
        result = self.evaluate(iteration, start_time, observations)
        if result is not None:
            evaluated += 1
            if result:
                success += 1

        return success, evaluated

    def run(self):
        p = None
        if self.terminal is not None:
            self.cmd[3] = f"--terminal={self.terminal}"

        try:
            p = subprocess.Popen(self.cmd, stdout=subprocess.PIPE)
            p.wait()
        except KeyboardInterrupt:
            p.send_signal(signal.SIGINT)
            p.wait()
            raise

        output = p.stdout.read().decode('utf-8')
        output_lines = output.splitlines()
        eval_result = self.evaluate_lines(output_lines)
        if self.verbosity < 0:  # --quiet
            return eval_result
        if self.verbosity > 0 or eval_result[0] < eval_result[1]:
            sys.stderr.write("Your Cougarnet output:\n")
            sys.stderr.write(output.rstrip())
            sys.stderr.write("\nEnd of Cougarnet output\n")
        return eval_result

class Scenario1(Lab2Tester):
    cmd = ['cougarnet', '--stop=22', '--disable-ipv6',
            '--terminal=none', 'scenario1.cfg']

    expected_observations = [
            [('ARP_REQUEST', ['b', 'r1']),
                ('ARP_REPLY', ['a']),
                ('ICMP', ['b'])],
            None,
            [('ICMP', ['b'])],
            None,
            [('ICMP', ['a'])],
            None,
            [('ARP_REQUEST', ['b', 'r1']),
                ('ARP_REPLY', ['a']),
                ('ICMP', ['r1']),
                ('ARP_REQUEST', ['c']),
                ('ARP_REPLY', ['r1']),
                ('ICMP', ['c'])],
            ]

class Scenario2(Lab2Tester):
    cmd = ['cougarnet', '--stop=22', '--disable-ipv6',
            '--terminal=none', 'scenario2.cfg']

    expected_observations = [
            [('ICMP', ['b'])],
            [('ICMP', ['r1']),
                ('ICMP', ['g'])],
            [('ICMP', ['r1']),
                ('ICMP', ['f'])],
            [('ICMP', ['r1']),
                ('ICMP', ['c'])],
            [('ICMP', ['r1']),
                ('ICMP', ['k'])],
            [('ICMP', ['r1']),
                ('ICMP', ['j'])],
            [('ICMP', ['r1']),
                ('ICMP', ['h'])],
            [('ICMP', ['r1']),
                ('ICMP', ['d'])],
            [('ICMP', ['r1']),
                ('ICMP', ['i'])],
            [('ICMP', ['r1']),
                ('ICMP', ['e'])],
            [('ICMP', ['r1']),
                ('ICMP', ['r2']),
                ('ICMP', ['l'])],
            [('ICMP', ['r1'])],
            ]

def main():
    parser = argparse.ArgumentParser(
        description="Test and grading driver for the network layer lab."
    )
    parser.add_argument("-v", "--verbose", action="count", default=0, 
                        help="Increase verbosity level and display Cougarnet output.")
    parser.add_argument("-q", "--quiet", action="store_true", 
                        help="Only display driver output. Do not display Cougarnet output.")
    parser.add_argument("-s", "--scenario", type=int, nargs="*", choices=[1, 2],
                        help="Run the specified scenarios. If not given, then all scenarios are run.")    
    parser.add_argument('--terminal',
            action='store', type=str, default=None,
            metavar='HOSTNAMES',
            help='Specify which virtual Cougarnet hosts should launch a terminal ' + \
                    '(all|none|host1[,host2,...])')
    args = parser.parse_args(sys.argv[1:])

    if args.scenario is not None:
        scenarios = [globals()[f"Scenario{s}"] for s in list(dict.fromkeys(args.scenario))]
    else:
        scenarios = [Scenario1, Scenario2]

    try:
        for scenario in scenarios:
            print(f'Running {scenario.__name__}...')
            tester = scenario(
                verbosity=(-1 if args.quiet else args.verbose), 
                terminal=args.terminal
            )
            success, total = tester.run()
            sys.stderr.write(f'  Result: {success}/{total}\n')
    except KeyboardInterrupt:
        sys.stderr.write('Interrupted\n')

if __name__ == '__main__':
    main()
