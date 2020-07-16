First, assemble your code like this (the -r option is the important one) :

acme -o demo2/div2.o -r demo2/report.txt demo2/div2.s

Run the debugger with:

python acmeint.py -c demo2/div2.o -r demo2/report.txt

In the program, use :
* 'space' to step one instruction,
* 'p' to step over,
* 'r' to reset at the beginning of the simulation
* 'c' to define ranges of cycle counting. For example
  to cycle count from line 20 to 30, hit 'c' then enter
  '20-30' then enter. Instead of line numbers, you can
  give labels' names. You can also give several ranges
  separated by ','.
* ESC to quit.