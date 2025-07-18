Commercial Operating System COS 300/310
=======================================

Startup
-------

```
COS MONITOR  V 8.00 
>DATE? 
.DA 06-JAN-79
```

Directory
---------

COS 300/310 System Reference Manual, Pag 92

```
/T      Output to the terminal
```

Example:

```
.DI/T

DIRECTORY       06-JAN-79 

NAME   TYPE LN    DATE

COMP     V  14  15-NOV-78 
PIP      V  10  15-NOV-78 
MENU     V  05  15-NOV-78 
SYSGEN   V  19  15-NOV-78 
PATCH    V  05  15-NOV-78 
CREF     V  07  15-NOV-78 
BOOT     V  02  15-NOV-78 
SORT     V  15  15-NOV-78 
LINCHG   V  02  15-NOV-78 
FILEX    V  21  15-NOV-78 
DKFMT    V  02  15-NOV-78 
DYFMT    V  02  15-NOV-78 
DFU      V  07  15-NOV-78 
DAFTA    S  12  15-NOV-78 
DAFTB    S  15  15-NOV-78 
PRINT0   S  16  15-NOV-78 
PRINT1   S  15  15-NOV-78 
PRINT2   S  04  15-NOV-78 
PRINT3   S  12  15-NOV-78 
PRINT4   S  05  15-NOV-78 
PRINT5   S  15  15-NOV-78 
PRINT6   S  09  15-NOV-78 
PRINT7   S  13  15-NOV-78 
PRINT8   S  06  15-NOV-78 
PRINT9   S  09  15-NOV-78 
FLOW1    S  11  15-NOV-78 
FLOW2    S  06  15-NOV-78 
FLOW3    S  10  15-NOV-78 
FLOW4    S  11  15-NOV-78 
KRFSRT   S  01  15-NOV-78 
KREF     S  06  15-NOV-78 
TRMTST   S  05  15-NOV-78 
LPTEST   S  06  15-NOV-78 
FLOPXX   S  07  15-NOV-78 
BUILD    S  01  28-MAR-79 
CONVER   S  10  28-MAR-79 
CMDFL    S  01  28-MAR-79 
CMDFL1   S  01  28-MAR-79 
CMDFL2   S  01  28-MAR-79 
BUILD    B  01  13-AUG-79 
CONVER   B  04  13-AUG-79 
BUILDX   S  05  01-JAN-73 
BUILDY   S  02  01-JAN-73 
BLDGLZ   S  07  01-JAN-73 
INIT3    S  01  13-AUG-79 
TEST     S  01  01-NOV-79 
TEST     B  01  01-NOV-79 
CLRGLW   S  02  14-DEC-79 
CLRGLI   S  02  14-DEC-79 
CLRSRC   S  02  14-DEC-79 
CLRGLW   B  01  14-DEC-79 
CLRGLI   B  01  14-DEC-79 
CLRSRC   B  01  14-DEC-79 
CLRSFM   S  02  12-DEC-79 
CLRFSM   B  01  12-DEC-79 
CLRWRK   S  02  12-DEC-79 
CLRWRK   B  01  12-DEC-79 
CLRGLA   S  02  12-DEC-79 
CLRGLT   S  02  12-DEC-79 
DAFT     B  16  07-NOV-79 
 <0184 FREE BLOCKS> 
```

Show file
---------

The FETCH command loads the named source file into core.
The LIST command outputs the specified lines or the entire edit buffer.

Example:

```
.FE TEST
.LI
0100 START/T
0110         RECORD
0120                 COUNT,A2
0130                 NUMBER,D2,P
0140                 A,D2,00
0150 PROC
0160         DISPLAY(1,1,1)
0170 LOOP,   DISPLAY(A,A,0)
0180         COUNT=A
0190         DISPLAY(A,A,COUNT)
0200         INCR A
0210         IF(A.LE.NUMBER)GO TO LOOP
0220 END
```

Compile and Run
---------------

The RUN command executes binary (B) or system (V) files.
Source program must be compiled before it can be executed using COMP.
Use the /N option to suppress the listing of the source file to the printer.
When the program is compiler, it is stored in the working memory area.
To store on the disk, use the SAVE command.

Example:

```
.RUN COMP,TRMTST/N
.SAVE TRMTST
```

```
.FE CIAO
.R COMP
COS DIBOL     06-JAN-79   SAT     COMPILATION LISTING      V 8.00  PAGE
01
          DATA DIVISION

0100  START/T
0110          RECORD
0120          LINE, A10, 'CIAO DIBOL'
COS DIBOL     06-JAN-79   SAT     COMPILATION LISTING      V 8.00  PAGE
02
    PROCEDURE  DIVISION

0130  PROC
0140          DISPLAY(1, 1, LINE)
0150  END
COS DIBOL     06-JAN-79   SAT     STORAGE MAP LISTING      V 8.00  PAGE
03
#       NAME      TYPE       DIM    SIZE    ORIGIN

0001    LINE      ALPHA       01      10     20002
0002    ..1       DECMAL      01      01     20014                                                                                                                                                                                                          
0002 SYMBOLS                                                                                                                                                                                                                                                
NO ERRORS DETECTED.   08 K CORE REQUIRED [4075 FREE LOCS =14 BUFFERS]                                                                                                                                                                                       

COS MONITOR  V 8.00
>.SAVE CIAO
REPLACE?
Y

COS MONITOR  V 8.00
>.R CIAO
Y  CIAO DIBOL
COS MONITOR  V 8.00
>.
```

References
----------

* [COS 300 System Reference Manual, 1973](https://bitsavers.org/pdf/dec/pdp8/cos-300/DEC-08-OCOSA-E-D_COS_300_System_Reference_Manual_197303.pdf)
* [COS 300/310 System Reference Manual, 1975](https://bitsavers.org/pdf/dec/pdp8/cos-300/DEC-08-OCOSA-F_D_COS_300_310_System_Reference_Manual_Jul75.pdf)
* [COS 310 New user's Guide, 1978](https://www.pdp8online.com/pdp8cgi/query_docs/tifftopdf.pl/pdp8docs/aa-d758a-ta.pdf)
