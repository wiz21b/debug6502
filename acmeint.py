import traceback
import argparse
import curses
import re
from py65emu.cpu import CPU
from py65emu.mmu import MMU

class LineInfo:
    def __init__( self, cycles, label, source):
        self.cycles, self.label, self.source = cycles, label, source
        self.cycle_mark = False

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

    LABEL_RE = re.compile( r"^\s+([0-9]+)\s+([0-9a-f]+\s+[0-9a-f]+)?\s+([^\s]+):.*$")

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
        fiter = fin.readlines()[2:]
        for line in fiter:
            line = line.rstrip().replace("\t"," "*8)

            source = line
            source_label = None
            cycles = None

            if ";" in line:
                line = line[0:line.index(';')]

            m = BEGIN_RE.match(line)
            if m:
                line_n = m.groups()[0]
                addr = int( m.groups()[1], 16)
                lines_addr[addr] = len(lines)

            m = LABEL_RE.match(line)
            if m:
                #print("label")
                source_label = last_label = m.groups()[2]
                #print( source_label)

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
                cycles = cpu.opcode_cycles[ opcode]

            lines.append( LineInfo(cycles, source_label, source) )

    return lines, lines_addr, locations, default_pc


def display_source( lines, cpu, locations, pc_start):
    current_offset = 0
    max_y, max_x = stdscr.getmaxyx()

    stepped_cpu = False
    error = None

    while True:


        highlighted = lines_addr[ cpu.r.pc]

        if stepped_cpu:
            if highlighted < current_offset or highlighted >= current_offset + max_y - 1:
                current_offset = max(0, highlighted - max_y // 2)
            stepped_cpu = False


        stdscr.clear()

        old_cycle_mark = False
        cycles_count = 0
        for i in range(max_y-1):
            line_nr = i+current_offset

            line = lines[line_nr]

            if line.cycle_mark and not old_cycle_mark:
                old_cycle_mark = True

            if line.cycle_mark and line.cycles:
                cycles_count += line.cycles

            if line.cycle_mark:
                ctext = f"{line.cycle_mark:3d}"
            else:
                ctext = "   "
            text = "{}|{}|{}".format(line.cycles or " ", ctext, line.source[0:max_x-1])

            if not line.cycle_mark:
                old_cycle_mark = False
                cycles_count = 0

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

        if not error:
            pc = cpu.r.pc
            c = cpu
            opcode = cpu.mmu.read( pc)
            cc = cpu.opcode_cycles[opcode]
            status_line = "PC=${:04X} A:${:02X},{:03d} X:${:02X},{:03d} Y:${:02X},{:03d} Flags:{} opcode:{:X} c:{}".format( pc, c.r.a, c.r.a, c.r.x, c.r.x, c.r.y, c.r.y, flags6502( cpu), opcode,cc)
            stdscr.addstr(0,0, status_line + " " *(max_x - len(status_line)), curses.color_pair(1))
        else:
            stdscr.addstr(0,0, error + " " *(max_x - len(error)), curses.color_pair(2))
            error = None


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
        elif k == ord('c'):
            from curses.textpad import Textbox

            def locate_line( s, lines):
                if s is None:
                    return None

                try:
                    return int( s) - 1
                except ValueError as ex:
                    for i,line in enumerate(lines):
                        if line.label and s in line.label:
                            return i
                    return None


            def done_on_enter( char):
                if char in [10, 13, curses.KEY_ENTER, curses.ascii.BEL]:
                    return curses.ascii.BEL
                return char


            def split_cycles_command( s, lines):
                pairs = [p.split('-') for p in s.split(',')]

                npairs = []
                for p in pairs:
                    if len(p) == 2:
                        l,r = p[0].strip(), p[1].strip()

                        l = locate_line(l, lines)
                        r = locate_line(r, lines)

                        if l is not None and r is not None:
                            npairs.append( (l,r) )
                        else:
                            return []
                    else:
                        return []

                return npairs


            stdscr.addstr(0,0, ">" + " "*(max_x-2))
            curses.curs_set(True)
            stdscr.move(0,2)
            tb = Textbox(stdscr)
            #tb.stripspaces = True
            txt = tb.edit( done_on_enter)
            curses.curs_set(False)

            input_line = txt[2:txt.index('\n')] # Tricky curses !

            #line = "compute_line-y1_smaller"


            ranges = split_cycles_command( input_line, lines)
            total = 0
            if ranges:
                for line in lines:
                    line.cycle_mark = False

                for p in ranges:
                    for i in range( p[0], p[1]+1):
                        if lines[i].cycles:
                            total += lines[i].cycles
                        lines[i].cycle_mark = total
            else:
                error = f"Don't understand {input_line}"



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
- 'space' to step one instruction,
- 'p' to step over,
- 'r' to reset at the beginning of the simulation
- 'c' to define ranges of cycle counting. For example
  to cycle count from line 20 to 30, hit 'c' then enter
  '20-30' then enter. Instead of line numbers, you can
  give labels' names. You can also give several ranges
  separated by ','.
- ESC to quit.

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
    curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_RED)

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
