First, assemble your code like this (the -r option is the important one) :

acme -o demo2/div2.o -r demo2/report.txt demo2/div2.s

Run the debugger with:

python acmeint.py -c demo2/div2.o -r demo2/report.txt

In the program, use :
* space to step one instruction,
* 'p' to step over
* ESC to quit.
* 'r' to reset at the beginning of the simulation
