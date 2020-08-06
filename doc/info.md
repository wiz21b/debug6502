# Debug6502 Documentation

# Invocation

Typical invocation for ACME code :

    python debug6502/acmeint.py --report report.txt
         -d div2.o 0x800 -d build/xbin_lines01  0xD000

If you use ACME, assemble your code like this (the -r option is the important one) :

    acme -o div2.o -r report.txt demo2/div2.s

For CA65

    python debug6502/acmeint.py --report-ca65 build/td.txt demo2/td_map.out
         -d build/CODE 0x800 -d build/xbin_lines01  0xD000


# Usage

In the program, these keys are available :

- 'Space' to step one instruction (will go inside JSR calls)
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

# Gotchas !

- The interpreter doesn't look at your source code at all.
- In particular, the CA65 interpreter don't understand macro's at all (it's still useful though, just step through the macros).
- It's python everywhere, so running chunks of code can be slow (for example, on my PC, clearing an HGR page takes a second)

This program is super alpha...
