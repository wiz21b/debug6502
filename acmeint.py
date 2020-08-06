# -*- coding: utf-8 -*-
import sys

assert sys.version_info.major == 3, "This program runs with Python 3 only!"

import os.path
import traceback
import argparse
import curses
import re
from py65emu.cpu import CPU
from py65emu.mmu import MMU
from PIL import Image

class LineInfo:
    def __init__( self, address, cycles, label, source):
        self.address, self.cycles, self.label, self.source = address, cycles, label, source
        self.cycle_mark = False

DEFAULT_PC = 0x800

REVERSED_BYTES = [ [(n//1)&1,  (n//2)&1,
                    (n//4)&1, (n//8)&1,
                    (n//16)&1, (n//32)&1,
                    (n//64)&1 ]  for n in range(256)]

def hgr_address( y, page=0x2000, format=0):
    #assert page == 0x2000 or page == 0x4000, "I'll work only for legal pages"
    assert 0 <= y < APPLE_YRES, "You're outside Apple's veritcal resolution"

    if 0 <= y < 64:
        ofs = 0
    elif 64 <= y < 128:
        ofs = 0x28
    else:
        ofs = 0x50

    i = (y % 64) // 8
    j = (y % 64) % 8

    if format == 0:
        return "${:X} + ${:X}".format( page + ofs + 0x80*i, 0x400*j)
    elif format == 1:
        return "${:X}".format( page + ofs + 0x80*i + 0x400*j)
    else:
        return page + ofs + 0x80*i + 0x400*j

APPLE_YRES = 64*3



def show_hgr(cpu, page=0x2000):

    data = []
    for y in range( APPLE_YRES):
        ofs = hgr_address( y, page, format=None)
        for b in cpu.mmu.blocks[0]['memory'][ofs:ofs+40]:
            data += REVERSED_BYTES[b]

    bdata = []
    for i in range(0,len(data),8):
        bits = data[i:i+8]
        b = bits[0]*128 + bits[1]*64 +bits[2]*32 + bits[3]*16 +bits[4]*8 + bits[5]*4 + bits[6]*2 + bits[7]*1
        bdata.append( b)

    img = Image.frombytes( "1", (280, APPLE_YRES), bytes(bdata))
    img = img.resize( (280*4,192*4), Image.NEAREST )

    img.show()




def init_cpu( mem, pc_value):

    mmu = MMU([
        (0x00, len(mem), False, mem) # readonly = False
        ])

    c = CPU(mmu, pc_value)

    return c

def flags6502( cpu):

    s = ["_"]*8
    for label, mask in cpu.r.flagBit.items():
        if cpu.r.p & mask:
            s[mask.bit_length()-1] = label[0]

    return ''.join(s)


def loop_step( cpu):
    current_pc = cpu.r.pc
    cpu.step()
    while cpu.r.pc != current_pc:
        cpu.step()


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


def parse_report_ca65( fname, map_name = ""):


    BEGIN_RE = re.compile( r"^([0-9A-F]+)r\s+([0-9]+)\s(.{12})(.*)$")
    SEGMENT_RE = re.compile( r'^\s+.segment\s+"([^"]+)".*$')
    SEGMENT = re.compile( r"^([^\s]+)\s+([0-9A-F]{6}).*$")

    segments = dict()
    with open( map_name,"r") as fin:
        lines = fin.readlines()

        ndx = 0
        while 'Segment list:' not in lines[ndx]:
            ndx += 1

        while True:

            line = lines[ndx].strip()

            m = SEGMENT.match(line)
            if m:
                seg_name, seg_address = m.groups()[0], int(m.groups()[1],16)
                #print( f"{seg_name} {seg_address:X}")

                segments[seg_name] = seg_address

            elif not line:
                break

            ndx += 1


    seg_addr = 0
    default_pc = 0
    lines_addr = dict()
    lines = []

    with open(fname,"r") as fin:
        fiter = fin.readlines()[4:]
        for real_nr, line in enumerate(fiter):
            line = line.rstrip().replace("\t"," "*8)


            m = BEGIN_RE.match(line)
            if m:

                code = m.groups()[3]
                hexa = m.groups()[2]

                m2 = SEGMENT_RE.match( code)

                if m2 and m2.groups()[0] in segments:
                    seg_name = m2.groups()[0]
                    seg_addr = segments[seg_name]
                    #print(f"{seg_name} {seg_addr}")

                line_addr = int( m.groups()[0], 16) + seg_addr

                if line_addr and not default_pc:
                    default_pc = line_addr

                #print( f"{line_addr:X} | {hexa} | {code}")

                if hexa.strip():
                    lines_addr[line_addr] = len(lines)
                else:
                    line_addr = 0

                addr_txt =""
                if line_addr:
                    addr_txt = f"{line_addr:04X}"
                else:
                    addr_txt = "   -"

                lines.append( LineInfo( line_addr, 0, None, f"{addr_txt} | {hexa} | {code}"))

    return lines, lines_addr, find_locations( lines), default_pc


def find_locations( lines):
    LABEL_RE = re.compile( r"^\s*([^\s]+):.*$")
    OPCODE_RE = re.compile( r"^.*(ADC|AND|ASL|BCC|BCS|BEQ|BIT|BMI|BNE|BPL|BRK|BVC|BVS|CLC|CLD|CLI|CLV|CMP|CPX|CPY|DEC|DEX|DEY|EOR|INC|INX|INY|JMP|JSR|LDA|LDX|LDY|LSR|NOP|ORA|PHA|PHP|PLA|PLP|ROL|ROR|RTI|RTS|SBC|SEC|SED|SEI|STA|STX|STY|TAX|TAY|TSX|TXA|TXS|TYA)\s.*$")
    cpu = CPU()

    last_label = None
    last_data_label = None

    locations = []

    for real_nr, line in enumerate( lines):

        source = line.source
        if ";" in source:
            source = source[0:source.index(";")]

        source_label = None
        cycles = None


        #print( source[22:])
        m = LABEL_RE.match( source[22:].strip())
        if m:
            source_label = last_label = m.groups()[0]
            #print( source_label)

        if ("!word" in source) or (".word" in source):
            if last_data_label != last_label:
                last_data_label = last_label
                #print(f"{last_data_label} at {addr:X}")
                locations.append( (last_data_label, line.address, 2) )

        elif ("!byte" in source) or (".byte" in source):
            if last_data_label != last_label:
                last_data_label = last_label
                #print(f"{last_data_label} at {addr:X}")
                locations.append( (last_data_label, line.address, 1) )

        # m = OPCODE_RE.match( source.upper())
        # if m:
        #     cycles = cpu.opcode_name_cycles[ m.groups()[0]]
        #     line.cycles = cycles


    return locations


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
        for real_nr, line in enumerate(fiter):
            line = line.rstrip().replace("\t"," "*8)

            line = "{: 6d}{}".format( real_nr+1, line[6:])

            source = line
            source_label = None
            cycles = None

            if ";" in line:
                line = line[0:line.index(';')]

            m = BEGIN_RE.match(line)
            addr = None

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

            lines.append( LineInfo( addr, cycles, source_label, source) )

            # def __init__( self, address, cycles, label, source):

    return lines, lines_addr, locations, default_pc


def display_source( lines, cpu, locations, pc_start):
    current_offset = 0
    max_y, max_x = stdscr.getmaxyx()

    stepped_cpu = False
    error = None

    while True:

        #assert cpu.r.pc in lines_addr, f"{cpu.r.pc:X} not in lines"

        if cpu.r.pc in lines_addr:
            highlighted = lines_addr[ cpu.r.pc]
        else:
            highlighted = 0
            # Try to find a close line
            for i in range(5):
                x = cpu.r.pc - i
                if x in lines_addr:
                    highlighted = lines_addr[ x]
                    break



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

            if len(text) >= max_x-1:
                text = text[0:max_x-1]

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
            status_line = "PC=${:04X} A:${:02X},{:03d} X:${:02X},{:03d} Y:${:02X},{:03d} Flags:{} opcode:{:02X} cycles:{}".format( pc, c.r.a, c.r.a, c.r.x, c.r.x, c.r.y, c.r.y, flags6502( cpu), opcode,cc)
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
                if y >= max_y - 2:
                    break

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
        elif k == ord('l'):
            loop_step( cpu)
            stepped_cpu = True
        elif k == ord('p'):
            smart_step( cpu, True)
            stepped_cpu = True
        elif k == ord('r'):
            cpu.reset(pc_start)
            stepped_cpu = True
        elif k == ord('q'):
            return False
        elif k == curses.KEY_F2:
            show_hgr(cpu,page=0x2000)
        elif k == curses.KEY_F4:
            show_hgr(cpu,page=0x4000)
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
--------------------------------------
6502 / ACME or CA65 source interpreter
--------------------------------------

© 2020 Stéphane Champailler. Licensed under GPLv3. Incorporating py65emu © Jeremy Neiman

Typical invocation :

   python debug6502/acmeint.py --report-ca65 build/td.txt demo2/td_map.out
        -d build/CODE 0x800 -d build/xbin_lines01  0xD000

In the program, these keys are available :

- 'space' to step one instruction (will go inside JSR calls)
- 'p' to step over
- 'r' to reset at the beginning of the simulation
- 'c' to define ranges of cycle counting. For example
  to count cycles from line 20 to 30, hit 'c' then type '20-30'
  in the status line (top of screen) then enter. Instead of line
  numbers, you can give labels' names.
  You can also give several ranges separated by ','
- 'l' run until the 6502 PC comes back to the same point (useful for executing loops)
- 'F2'/'F4' show HGR ($2000) or HGR2 ($4000) page in black and white
- 'Up/Down/PgUp/PgDn' to browse the code
- 'Esc' to quit.
- 'Ctrl-C' to quit if the emulation get stuck in a loop :-)

Watch out !

- The interpreter doesn't look at your source code at all.
- In particular, the CA65 interpreter don't understand macro's at all (it's still useful though, just step through the macros).
- It's python everywhere, so running chunks of code can be slow (for example, on my PC, clearing an HGR page takes a second)

This program is super alpha...
""", formatter_class=argparse.RawTextHelpFormatter)



parser.add_argument('--report','-r',help="ACME source report (use ACME's -r option)")
parser.add_argument('--report-ca65','-ca65',nargs=2,metavar=('source','mapfile'),help="CA65 source report and map file (see ca65 --listing and ld65 --mapfile)")
parser.add_argument('--default-pc','-l',help=f'PC value on startup (default to ${DEFAULT_PC:X})', default=DEFAULT_PC)
parser.add_argument('--load','-d',action='append',nargs='*',metavar=('path','addr'),help=f'Load binary (code or data) file with path at address addr in 6502 RAM. Address can be decimal or hexa ($ or 0x prefix)')

def hex_to_int( s):
    hexa = s.startswith("$") or s.startswith("0x")
    if hexa:
        return int( s.replace("$","").replace("0x",""), 16)
    else:
        return int( s)


if __name__ == "__main__":
    args = parser.parse_args()

    if not args.report and not args.report_ca65:
        print("For ACME, specify an ACME source report.  For CA65 specify a source report and a map file")
        exit()

    mem = bytearray(65536)

    if args.load:

        #mem_block = cpu.mmu.blocks[0]['memory'] # FIXME breaks MMU'class encapsulation :-)

        for path, addr in (args.load or []):
            if not os.path.isfile( path):
                raise Exception(f"File {path} doesn't exist")

            addr = addr.lower()

            hexa = addr.startswith("$") or addr.startswith("0x")
            if hexa:
                addr = int( addr.replace("$","").replace("0x",""), 16)
            else:
                addr = int( addr)

            with open( path, "rb") as din:
                data = din.read()
                mem[addr:addr+len(data)] = data

            print(f"Data file {path} at ${addr:04X}")


    if args.report_ca65:
        lines, lines_addr, locations, source_pc = parse_report_ca65( *args.report_ca65)
    else:
        lines, lines_addr, locations, source_pc = parse_report( args.report)

    if args.default_pc:
        pc = hex_to_int( args.default_pc)

    else:
        pc = source_pc


    print(f"PC set to ${pc:04X}")

    cpu = init_cpu( mem, pc)



    # print( f"{cpu.r.pc:X}")
    # cpu.step()
    # print( f"{cpu.r.pc:X}")
    # cpu.step()
    # print( f"{cpu.r.pc:X}")
    # cpu.step()
    # print( f"{cpu.r.pc:X}")
    # exit()

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
