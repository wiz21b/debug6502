import traceback
import argparse
import curses
import re
from py65emu.cpu import CPU
from py65emu.mmu import MMU

DEFAULT_PC = 0x800


def init_cpu( fname, start_address):

    code = open(fname, "rb").read()  # Open your rom

    mmu = MMU([
        (0x00, start_address, False), # Create RAM with 512 bytes
        (start_address, len(code), False, code), # Create ROM starting at 0x1000 with your program.
        (start_address+len(code), 65536-(start_address+len(code)), False)
    ])
    c = CPU(mmu, start_address)

    return c

def flags6502( cpu):

    s = ["_"]*8
    for label, mask in cpu.r.flagBit.items():
        if cpu.r.p & mask:
            s[mask.bit_length()-1] = label[0]

    return ''.join(s)

def smart_step( cpu, step_over=False):
    mmu = cpu.mmu
    pc = cpu.r.pc
    opcode = mmu.read(pc)
    if opcode == 0x20 and step_over:
        # JSR
        current_s = cpu.r.s
        cpu.step()
        while cpu.r.s != current_s:
            cpu.step()
    elif opcode == 0:
        # BRK
        pass
    else:
        cpu.step()


def parse_report( fname = "report.txt"):
    # We handle only ACME 0.96.4 reports

    # regex matching the beginning of an interesting line
    # (ie a line with some binary data attached to it)
    BEGIN_RE = re.compile( r"^\s+([0-9]+)\s+([0-9a-f]+)\s.*$")

    LABEL_RE = re.compile( r"^\s+([0-9]+)\s+([0-9a-f]+)\s+([0-9a-f]+)\s+([^\s]+):.*$")

    ZP_RE = re.compile( r"^\s+[0-9]+\s+([^\s]+)\s*=\s*(\$?[0-9A-Fa-f]+).*$")

    OPCODE_RE = re.compile( r"^\s+([0-9]+)\s+([0-9a-f]+)\s([0-9a-f]{2}).*$")
    lines_addr = dict()
    lines = []

    last_label = None
    last_data_label = None

    locations = []
    default_pc = DEFAULT_PC
    first_star = False

    cpu = CPU()

    with open(fname,"r") as fin:
        for line in fin.readlines():
            line = line.rstrip().replace("\t"," "*8)
            lines.append( line)

            m = BEGIN_RE.match(line)
            if m:
                line_n = m.groups()[0]
                addr = int( m.groups()[1], 16)
                lines_addr[addr] = len(lines)-1

            m = LABEL_RE.match(line)
            if m:
                last_label = m.groups()[3]

            if "!word" in line:
                if last_data_label != last_label:
                    last_data_label = last_label
                    #print(f"{last_data_label} at {addr:X}")
                    locations.append( (last_data_label, addr, 2) )

            if "!byte" in line:
                if last_data_label != last_label:
                    last_data_label = last_label
                    #print(f"{last_data_label} at {addr:X}")
                    locations.append( (last_data_label, addr, 1) )

            # Heuristic to find EQU's of ZeroPAge addresses
            m = ZP_RE.match(line)
            if m:
                label, value = m.groups()

                if value.startswith('$'):
                    value = int( value[1:],16)
                else:
                    value = int(value)

                if label != '*'  and value < 256:
                    locations.append( (label, value, 1) )
                elif not first_star:
                    default_pc = value
                    first_star = True

            m = OPCODE_RE.match(line)
            if m:
                opcode = int(m.groups()[2],16)
                print(line)
                print( opcode)
                cc=cpu.opcode_cycles[ opcode]
                lines[-1] = f"{cc:d} | {lines[-1]}"
            else:
                lines[-1] = f"  | {lines[-1]}"

    return lines, lines_addr, locations, default_pc


def display_source( lines, cpu, locations, pc_start):
    current_offset = 0
    max_y, max_x = stdscr.getmaxyx()

    stepped_cpu = False

    while True:


        highlighted = lines_addr[ cpu.r.pc]

        if stepped_cpu:
            if highlighted < current_offset or highlighted >= current_offset + max_y - 1:
                current_offset = max(0, highlighted - max_y // 2)
            stepped_cpu = False


        stdscr.clear()
        for i in range(max_y-1):
            line_nr = i+current_offset

            text = lines[line_nr][0:max_x-1]

            if line_nr == highlighted:
                highlight = curses.A_REVERSE
            else:
                highlight = 0

            if ';' in text:
                n = text.index(';')
                stdscr.addstr(i+1, 0, text[:n], highlight)
                stdscr.addstr(i+1, n, text[n:], curses.A_BOLD)
            else:
                stdscr.addstr(i+1, 0, text, highlight)

        pc = cpu.r.pc
        c = cpu

        opcode = cpu.mmu.read( pc)
        cc = cpu.opcode_cycles[opcode]

        status_line = "PC=${:04X} A:${:02X},{:03d} X:${:02X},{:03d} Y:${:02X},{:03d} Flags:{} opcode:{:X} c:{}".format( pc, c.r.a, c.r.a, c.r.x, c.r.x, c.r.y, c.r.y, flags6502( cpu), opcode,cc)
        stdscr.addstr(0,0, status_line + " " *(max_x - len(status_line)), curses.color_pair(1))


        if locations:
            data_lines = []
            y = 1
            for label, addr, width in locations:

                if width == 2:
                    v_int = cpu.mmu.readWord( addr)
                    v = "${:04X}".format(v_int)
                else:
                    v_int = cpu.mmu.read( addr)
                    v = "${:02X}".format(v_int)

                s = f"{label}: {v} ({v_int:d})"
                data_lines.append( s)

            longest = max( [ len(s) for s in data_lines])

            for y,s in enumerate( data_lines):
                if len(s) < longest:
                    s += " "*(longest-len(s))
                s = "|" + s
                stdscr.addstr(y+1, max_x - longest - 1, s, curses.color_pair(1))


        stdscr.refresh()
        k = stdscr.getch()

        max_y, max_x = stdscr.getmaxyx()

        step = max_y // 2

        if k == curses.KEY_NPAGE:
            current_offset += step
        elif k == curses.KEY_DOWN:
            current_offset += 1
        elif k == curses.KEY_UP:
            current_offset -= 1
        elif k == curses.KEY_PPAGE:
            current_offset -= step
        elif k == ord(' '):
            smart_step( cpu)
            stepped_cpu = True
        elif k == ord('r'):
            cpu.reset(pc_start)
            stepped_cpu = True
        elif k == ord('p'):
            smart_step( cpu, True)
            stepped_cpu = True
        elif k == ord('q'):
            return False
        elif k == 27: # Esc or Alt
            # Don't wait for another key
            # If it was Alt then curses has already sent the other key
            # otherwise -1 is sent (Escape)
            stdscr.nodelay(True)
            n = stdscr.getch()
            if n == curses.ERR:
                # Escape was pressed
                # Return to delay
                stdscr.nodelay(False)
                return False


        if current_offset < 0:
            current_offset = 0
        elif current_offset > len(lines) - max_y:
            current_offset = len(lines) - max_y



parser = argparse.ArgumentParser(description="""
------------------------------
6502 / ACME source interpreter
------------------------------

© 2020 Stéphane Champailler. Licensed under GPLv3.
Incorporating py65emu © Jeremy Neiman

In the program, use :
- space to step one instruction,
- 'p' to step over
- ESC to quit.
- 'r' to reset at the beginning of the simulation

This program is super alpha...
""", formatter_class=argparse.RawTextHelpFormatter)



parser.add_argument('--compiled','-c',help='Compiled 6502 code', required=True)
parser.add_argument('--report','-r',help="ACME source report (use ACME's -r option)", required=True)
parser.add_argument('--load-address','-l',help=f'Load address (default to ${DEFAULT_PC:X})', default=DEFAULT_PC)



if __name__ == "__main__":
    args = parser.parse_args()

    lines, lines_addr, locations, source_pc = parse_report( args.report)

    #exit()

    if source_pc != args.load_address:
        pc = source_pc
    else:
        pc = args.load_address
    cpu = init_cpu( args.compiled, pc)


    stdscr = curses.initscr()
    curses.start_color()
    curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLUE)

    curses.curs_set(False)
    curses.noecho()
    curses.cbreak()
    stdscr.keypad(True)

    stored_exception = None
    try:
        display_source( lines, cpu, locations, pc)
    except Exception as ex:
        stored_exception = traceback.format_exc()
    finally:
        curses.nocbreak()
        stdscr.keypad(False)
        curses.echo()
        curses.endwin()

    if stored_exception:
        print("Error!")
        print( stored_exception)
