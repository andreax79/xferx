CREATE/ALLOCATE:1000 os32.dsk
INITIALIZE/os32 os32.dsk
MOUNT/os32 dsk: os32.dsk
COPY /ascii data/1.txt dsk:d1.txt/0
COPY /ascii data/2.txt dsk:d2.txt/0
COPY /type:co data/5.txt dsk:d5.txt/0
COPY /ascii data/10.txt dsk:d10.txt/10
COPY /ascii data/20.txt dsk:d20.txt/10
COPY /type:co /ascii data/50.txt dsk:d50.txt/10
COPY /ascii data/100.txt dsk:d100.txt/20
COPY /ascii data/200.txt dsk:d200.txt/20
COPY /type:co data/500.txt dsk:d500.txt/20
COPY /ascii data/1000.txt dsk:d1000.txt/30
COPY /type:co data/2000.txt dsk:d2000.txt/30
