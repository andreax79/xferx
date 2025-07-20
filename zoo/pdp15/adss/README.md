PDP-9/PDP-15 Advanced System Software
=====================================

A filename is a string of up to six alphanumeric characters.
Any printing character in the ASCII set can be used with the exception of a space, ":", ";", ",", "(" and ")".
The filename extension can be up to three characters long.

**Filename and extension are separated by a semicolon**, example: `TEST;SRC`.

List files
----------

Syntax:

```
D[IRECT] [<device>]
```

Example:

```
$D

 DIRECTORY LISTING
 .LOAD  BIN    37
 DDT    BIN    40
 EXECUT BIN    41
 INTEAE BIN    43
 INTNON BIN    50
 RELEAE BIN    76
 RELNON BIN    77
 .LIBR  BIN   105
 FOCAL  BIN   120
 KM9-15 SYS     0
 SKPBLK SYS    42
 IOBLK  SYS    46
 SGNBLK SYS    52
 SYSHAN SYS    56
 SYSBLK SYS    61
 .SYSLD SYS    62
 BITMAP SYS    71
 DIRECT SYS   100
 EDIT   SYS   644
 PIP    SYS   664
 MACRO  SYS   704
 F4     SYS   742
 DTCOPY SYS  1001
 DUMP   SYS  1004
 UPDATE SYS  1010
 SGEN   SYS  1020
 CHAIN  SYS  1051
 PATCH  SYS  1071
 324  FREE BLOCKS
```

### List files on the foreground/background monnitor

In the foreground monitor, the device is mandatory.

```
$D 0

DIRECTORY LISTING
     51 FREE BLKS
.F4LIB BIN  105
PIP    BIN  106
.IOLIB BIN  107
DDT    BIN  110
BFLOAD BIN  111
CDB.   019  222
FOCAL  BIN  172
EXECUT BIN  247
TIME   BIN  273
IDLE   BIN  300
TIME10 BIN  305
LP.647 BIN  344
LP.09  BIN  353
RESMON API    0
SYSBLK SYS   40
.SYSLD SYS   41
BFKM15 SYS   53
BITMAP SYS   71
DIRECT SYS  100
BFSGEN SYS  463
EDIT   SYS  514
PIP    SYS  527
MACRO  SYS  547
CHAIN  SYS  606
F4     SYS  626
MACROA SYS  660
F4A    SYS  710
DUMP   SYS  740
DTCOPY SYS  744
PATCH  SYS  747
UPDATE SYS  756
SRCCOM SYS  766

F9/15 V4A
```

System blocks
-------------

```
KM9-15 SYS     0
SKPBLK SYS    42
IOBLK  SYS    46
SGNBLK SYS    52
SYSHAN SYS    56
SYSBLK SYS    61  -> System program block
.SYSLD SYS    62
BITMAP SYS    71  -> File Bitmap Block
DIRECT SYS   100  -> Directory Block
EDIT   SYS   644 |
PIP    SYS   664 |
MACRO  SYS   704 |
F4     SYS   742 |
DTCOPY SYS  1001 |
DUMP   SYS  1004 |-> System programs
UPDATE SYS  1010 |
SGEN   SYS  1020 |
CHAIN  SYS  1051 |
PATCH  SYS  1071 |
```

System program format means that the binary is a straight core dump onto contiguous blocks.


Help
----

Show help information for commands.

```
$I

 KMS9-15 COMMANDS:
    LOG(L): USER COMMENTS TERMINATED BY ALTMODE
    SCOM(S): SYSTEM INFO
    INSTRUCT(I): LIST OF MONITOR COMMANDS
    INSTRUCT(I) ERRORS: DESCRIPTION OF ERROR CODES
    REQUEST(R), REQUEST(R) PRGNAM: .DAT SLOT USAGE
    REQUEST(R) USER: POSITIVE .DAT SLOT USAGE
    ASSIGN(A) DEVN A,B,.../ETC.: .DAT SLOT MODS
    DIRECT(D), DIRECT(D) M: DIRECTORY OF UNIT 0 OR M OF SYSTEM DEVICE
    NEWDIR(N) M: CLEAR DIRECTORY OF UNIT M OF SYSTEM DEVICE
    QDUMP(Q): SET TO SAVE CORE (^Q) ON .IOPS ERROR
    HALT(H): SET TO HALT ON .IOPS ERROR
    ^QN: SAVE CORE ON UNIT N
    GET(G) N: RESTORE CORE FROM UNIT N AND RESTART
    GET(G) N X: RESTORE CORE FROM UNIT N AND START AT X
    GET(G) N HALT(H):RESTORE CORE FROM UNIT N AND HALT
    API ON/OFF: CHANGE STATE OF API
    339 ON/OFF: DO/DONT SETUP PUSH DOWN LIST FOR 339
    VC38 ON/OFF: DO/DONT SETUP CHARACTER TABLE FOR 339
    CHANNEL 7/9: SETUP DEFAULT ASSUMPTION FOR MAGTAPE
    LA30 ON/OFF: TURN LA30 TIMING ON/OFF
    33TTY ON/OFF: TURN 33TTY TABBING ON/OFF
    ^C: RESTORE KMS9-15
    ^P: USER RESTART
 KMS9-15 PROG LOADING COMMANDS AND PROGNAM FOR REQUEST COMMAND
    LOAD: LINK LOAD AND WAIT FOR ^S
    GLOAD: LINK LOAD AND GO
    DDT: LINK LOAD WITH SYMBOLS AND GO TO DDT
    DDTNS: LINK LOAD W/O SYMBOLS AND GO TO DDT
    MACRO: SYMBOLIC MACRO ASSEMBLER
    MACROI: 8K DECTAPE I/O MACRO ASSEMBLER
    F4: FORTRAN IV COMPILER
    F4I: 8K DECTAPE I/O FORTRAN IV COMPILER
    EDIT: TEXT EDITOR
    PIP: PERIPHERAL INTERCHANGE PROG
    SGEN: SYSTEM GENERATOR
    DUMP: BULK STOR DEV DUMP                                                                                                                                                                    UPDATE: LIBR FILE UPDATE
    SRCCOM: SOURCE COMPARE
    EDITVP: SCOPE EDITOR
    PATCH: SYSTEM TAPE PATCH ROUTINE
    EXECUTE(E) FILE: LOAD AND RUN FILE XCT
    CHAIN: XCT CHAIN BUILDER
 KMS9-15: BATCH
    BATCH(B) DV: ENTER BATCH MODE WITH DV AS BATCH DEV
        DV: PR = PAPER TAPE READER
            CD = CARD READER
    $JOB: CONTROL COMMAND WHICH SEPARATES JOBS
    $DATA: BEGINNING OF DATA
    $END: END OF DATA
    $EXIT: LEAVE BATCH MODE
    ^T: SKIP TO NEXT JOB
    ^C: LEAVE BATCH MODE
```

System Information
------------------

Show system configuration information.

```
$SCOM

 SYSTEM INFO - V5B000 - 10/1/74

 77646 - BOOTSTRAP RESTART ADDR
 77636 - 1ST FREE CELL BELOW BOOTSTRAP
 2001 - 1ST FREE CELL ABOVE RESIDENT MONITOR
 141 - ADDR OF .DAT
 566 - ^Q ADDRESS FOR MANUAL DUMP
 101 - START BLOCK FOR ^Q DUMP AREA
 255 - KMS9-15 START WITH RESTART ADDRESS IN CELL 0
 SYSTEM HAS EAE
 I/O HANDLERS AVAILABLE:
 TTA  TELETYPE: I/O, ASCII MODES, ALL FUNCTIONS
 PRA  TAPE READER: INPUT, ALL MODES, ALL FUNCTIONS
 PRB  TAPE READER: INPUT, IOPS ASCII MODE, ALL FUNCTIONS
 PPA  PUNCH: OUTPUT, ALL MODES, ALL FUNCTIONS
 PPB  PUNCH: OUTPUT, ALL MODES LESS IOPS ASCII, ALL FUNCTIONS
 PPC  PUNCH: OUTPUT, IOPS BINARY MODE, ALL FUNCTIONS
 DTA  DECTAPE: 3 FILES, I/O, ALL MODES, ALL FUNCTIONS
 DTB  DECTAPE: 2 FILES, I/O, IOPS MODES, LIM FUNCTIONS
 DTC  DECTAPE: 1 FILE, INPUT, IOPS MODES, LIMITED FUNCTIONS
 DTD  DECTAPE: 1 FILE, I/O, ALL MODES, ALL FUNCTIONS
 DTE  DECTAPE: 1 FILE, I/O, ALL MODES, ALL FUNCTIONS EXCEPT .MTAPE
 DTF  DECTAPE: NON-FILE ORIENTED FOR F4 .OTS
 LPA  LINE PRINTER: OUTPUT, IOPS ASCII MODE, ALL FUNCTIONS
 SKIP CHAIN ORDER
     DTDF
     CLSF
     RSF
     PSF
     KSF
     TSF
     706601
     DTEF
     706621
     SPFAL
     MPSNE
     MPSK
     SPE
```

PIP
---

Syntax:

```
<single letter command> <destination device>:<file name>;<file extension> [switch] _ <source device>:<file name>;<file extension> [switch]
```

Commands:

* T Transfer File
* L List Directory
* D Delete File
* C Copy
* R Rename File
* V Verify File
* S Segment File
* B Block Copy
* N New Directory

Devices:

* PR Paper Tape Reader
* PP Paper Tape Punch
* TT Teletype
* LP Line Printer
* DT DECtape
* MT Magnetic Tape
* CD Card Reader
* RF Disk

Swtiches:

Switch options are enclosed in parentheses and require no delimiters to separate them from each other.
They may appear either with the destination device information or with the source device information.

* (A) IOPS ASCII
* (B) IOPS Binary
* (I) Image Alphanumeric
* (H) Image Binary
* (D) Dump

### List file using PIP.

Syntax:

```
L TT _ [<device>]
```

The "_" represent a left arrow, so `LL _ DT` means List Device DT to teletype.


```
$PIP


PIP V13E

>L TT _ DT

 DIRECTORY LISTING
  324 FREE BLKS
   11 USER FILES
  314 SYSTEM BLKS
 .LOAD  BIN    37    10
 DDT    BIN    40    13
 EXECUT BIN    41     3
 INTEAE BIN    43     1
 INTNON BIN    50     1
 RELEAE BIN    76     4
 RELNON BIN    77     4
 .LIBR  BIN   105   155
 FOCAL  BIN   120    23
 KM9-15 SYS     0
 SKPBLK SYS    42
 IOBLK  SYS    46
 SGNBLK SYS    52
 SYSHAN SYS    56
 SYSBLK SYS    61
 .SYSLD SYS    62
 BITMAP SYS    71
 DIRECT SYS   100
 EDIT   SYS   644
 PIP    SYS   664
 MACRO  SYS   704
 F4     SYS   742
 DTCOPY SYS  1001
 DUMP   SYS  1004
 UPDATE SYS  1010
 SGEN   SYS  1020
 CHAIN  SYS  1051
 PATCH  SYS  1071

PIP V13E
```

### Copy file using PIP.

Copy a file from the DECtape 2 to the DECtape 0 in binary mode.

```
>T DTA0:TEST;BIN _ DTA2:TEST;BIN (B)
```

.DAT Slot
---------

.DAT slots are used to assign devices to the programs.
Show the current .DAT slot assignments with the command:

```
R[EQUEST] [<program>]
```

Example, examine the .DAT/UFDT slots for the FORTRAN compiler.

```
$R F4

 .DAT   DEVICE  USE

  -13    DTA2   OUTPUT
  -12    LPA0   LISTING
  -11    DTA1   INPUT
  -3     TTA0   CONTROL AND ERROR MES
  -2     TTA0   COMMAND STRING
```

In order to change the .DAT slot assignments, use the command:

```
A[SSIGN] <device> <slot>
```

A change of .DAT slot assignments is effective for the current job only since
permanent assignments are restored when control is returned to the Monitor.

Example, assign the teleprinter to .DAT -12.

```
$ A TT -12
```

Fortran IV
----------

Init (format) DECtape 1 and 2.

```
$ xferx -c 'init /adss tape2.dtp' -c 'init /adss tape2.dtp'
```

Copy the source code to a file to the DECtape 1
(with the default .DAT slot assignments the Fortran compiler reads the source
code from tape 1 and write the output to tape 2).

```
$ xferx --adss tape1.dtp -c 'copy/ascii test.f dl0:test;src'
```

Check DECtape 1 for the source code file.

```
$D 1

 DIRECTORY LISTING
 TEST   SRC     1
 1067  FREE BLOCKS
 ```

Compile the source code with the Fortran IV compiler
(`B` is the command to compile the source code).

```
$F4


F4B9 V5B002
>B_TEST

END PASS1
F4B9 V5B002
>^C
```

Check the DECtape 2 for the compiled binary.

```
$D 2

 DIRECTORY LISTING
 TEST   BIN     1
 1067  FREE BLOCKS
```

Copy the compiled binary to the DECtape 0.

```
$PIP


PIP V13E

>T DTA0:TEST;BIN _ DTA2:TEST;BIN (B)
```

Execute the compiled binary.

```
$GLOAD


LOADER V5B000
>_TEST (press ESC, not enter)

       1
       2
       3
       4
       5
       6
       7
       8
       9
      10
STOP  012345
                                                                                                                                                                                            
KMS9-15 V5B000
```

References
----------

* [PDP-9 Advanced Software System Monitors](https://bitsavers.org/pdf/dec/pdp9/DEC-9A-MAD0-D.pdf)
* [PDP-9 Advanced System Software Keyboard Monitor Guide](https://bitsavers.org/pdf/dec/pdp9/DEC-9A-NGBA-D.pdf)
* [PDP-15 Advanced Monitor Software System for PDP-1S/20/30/40 Programmer's Reference Manual](https://bitsavers.org/pdf/dec/pdp15/DEC-15-MR2B-D_AdvMonPgmRef.pdf)
