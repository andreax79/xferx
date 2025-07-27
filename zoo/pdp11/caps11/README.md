CAPS-11
=======

Files are referenced symbolically by a name of as many as 6 alphanumeric characters,
followed optionally by an extension of from 1 to 3 alphanumeric characters.
The first character in a filename must be alphabetic.

Run
---

The RUN command is of the form:

```
.R [Drive #:]Filename[/Options]
```

The RUN command instructs the Monitor to load and execute the file specified in the command line.

Date
----

The DATE command set the date for the system. The command is of the form:

```
.DA dd/mmm/yy
```

where dd, mmmm, and yy represent the current month, day and year.

Example:

```
.DA 06-JAN-79
```

Directory
---------

The DIR command causes a directory listing of the cassette on the drive specified
to be output on the console terminal. The command is of the form:

```
.DI [Drive #][/Options]
```

Example:
```
.DIR

 06-JAN-79

CTLOAD SYS 08-AUG-73
CAPS11 S8K 09-AUG-73
PIP    SRU 09-AUG-73
EDIT   SLG 09-AUG-73
LINK   SRU 09-AUG-73
ODT    SLG 09-AUG-73
PAL    SRU 09-AUG-73
DEMO   PAL 09-AUG-73
.DIR

.DIR 1:

 06-JAN-79

CTLOAD SYS 08-AUG-73
CAPS11 S8K 09-AUG-73
PIP    SRU 09-AUG-73
EDIT   SLG 09-AUG-73
LINK   SRU 09-AUG-73
*EMPTY     --
PAL    SRU 09-AUG-73
DEMO   PAL 09-AUG-73
```

Delete
------
The DEL command deletes a file from the directory. The command is of the form:

```
.DE [Drive #]:Filename.ext
```

Zero
----

The ZERO command is of the form:

```
.Z Drive #:Filename
```

and specifies that the sentinel file of the indicated cassette is to
be moved so that it immediately follows the file indicated in the
command line.

Version
-------

The Version command is used to find out the version number of the CAPS-8 currently in use.

```
.V

CAPS-11 V01-02
 06-JAN-79
```

References
----------

* [CAPS-11 User Guide](http://bitsavers.informatik.uni-stuttgart.de/pdf/dec/pdp11/caps-11/DEC-11-OTUGA-A-D_CAPS-11_Users_Guide_Oct73.pdf)
